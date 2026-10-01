"""Python AST declarations with Jedi-backed static reference and call targets."""

from __future__ import annotations

import ast
import sysconfig
from pathlib import Path
from typing import Any

import jedi

from polycodegraph_adapters.model import Graph, Json, Source


class PythonGraph:
    """Index source without importing modules or running indexed Python code."""

    def __init__(self, graph: Graph, options: Json | None = None) -> None:
        self.graph = graph
        self.definitions: dict[tuple[Path, int, int], str] = {}
        self.ast_nodes: dict[ast.AST, Json] = {}
        self.trees: dict[str, ast.Module] = {}
        self.scripts: dict[str, Any] = {}
        self.bases: dict[str, list[str]] = {}
        # Each index uses a fresh single-threaded process; disable dynamic
        # call-site/parameter inference. Only
        # source types/imports and explicit assignments are semantic evidence.
        jedi.settings.fast_parser = True
        jedi.settings.dynamic_params = False
        project = jedi.Project(
            path=graph.root,
            sys_path=[
                str(graph.root),
                str(graph.root / "src"),
                sysconfig.get_paths()["stdlib"],
                sysconfig.get_paths()["purelib"],
                *((options or {}).get("python_search_paths", [])),
            ],
            smart_sys_path=False,
            load_unsafe_extensions=False,
        )
        for source in graph.sources.values():
            try:
                tree = ast.parse(source.text, filename=str(source.path), type_comments=True)
            except SyntaxError as error:
                source.diagnostic("syntax_error", str(error), error.lineno or 1, "error")
                continue
            self.trees[source.file] = tree
            self.scripts[source.file] = jedi.Script(code=source.text, path=source.path, project=project)
            self._declare(source, tree, None, "")

    def _span(self, source: Source, node: ast.expr | ast.stmt) -> tuple[int, int]:
        assert node.end_lineno is not None and node.end_col_offset is not None
        return (
            source.byte_column(node.lineno - 1, node.col_offset),
            source.byte_column(node.end_lineno - 1, node.end_col_offset),
        )

    def _binding(self, source: Source, name: str, line: int, column: int, identifier: str) -> None:
        self.definitions[(source.path.resolve(), line, column)] = identifier

    def _declare(self, source: Source, node: ast.AST, parent: Json | None, scope: str) -> None:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            start, end = self._span(source, node)
            name = node.name
            kind = (
                "class"
                if isinstance(node, ast.ClassDef)
                else (
                    "constructor"
                    if parent and parent["kind"] == "class" and name == "__init__"
                    else "method"
                    if parent and parent["kind"] == "class"
                    else "function"
                )
            )
            tags = ["async"] if isinstance(node, ast.AsyncFunctionDef) else []
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                tags += ["property"] if any(ast.unparse(d).endswith("property") for d in node.decorator_list) else []
                tags += (
                    ["abstract"] if any(ast.unparse(d).endswith("abstractmethod") for d in node.decorator_list) else []
                )
            qualified = f"{scope}.{name}" if scope else name
            declaration = self.graph.declare(
                source, name, qualified, kind, start, end, parent["id"] if parent else None, tags
            )
            self.ast_nodes[node] = declaration
            column = source.lines[node.lineno - 1].index(
                name,
                start
                - source.starts[node.lineno - 1]
                + (6 if isinstance(node, ast.ClassDef) else 10 if isinstance(node, ast.AsyncFunctionDef) else 4),
            )
            self._binding(source, name, node.lineno, column, declaration["id"])
            for child in node.body:
                self._declare(source, child, declaration, qualified)
            return
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                binding_name: str | None = None
                container = parent
                if isinstance(target, ast.Name) and (parent is None or parent["kind"] == "class"):
                    binding_name = target.id
                elif (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id in {"self", "cls"}
                    and parent
                    and parent.get("parent")
                ):
                    container = self.graph.nodes[parent["parent"]]
                    if container["kind"] == "class":
                        binding_name = target.attr
                if binding_name:
                    start, end = self._span(source, target)
                    qualified = f"{container['q']}.{binding_name}" if container else binding_name
                    kind = "field" if container else "variable"
                    identifier = f"{source.file}::{qualified}#{kind}"
                    declaration = self.graph.nodes.get(identifier) or self.graph.declare(
                        source, binding_name, qualified, kind, start, end, container["id"] if container else None
                    )
                    column = len(source.lines[target.lineno - 1].encode("utf-8")[: target.col_offset].decode("utf-8"))
                    if isinstance(target, ast.Attribute):
                        assert target.end_lineno is not None and target.end_col_offset is not None
                        column = len(
                            source.lines[target.end_lineno - 1].encode("utf-8")[: target.end_col_offset].decode("utf-8")
                        ) - len(binding_name)
                    self._binding(source, binding_name, target.lineno, column, declaration["id"])
        for child_node in ast.iter_child_nodes(node):
            self._declare(source, child_node, parent, scope)

    def _point(self, source: Source, node: ast.expr) -> tuple[int, int]:
        if isinstance(node, ast.Attribute):
            assert node.end_lineno is not None and node.end_col_offset is not None
            line = node.end_lineno - 1
            column = len(source.lines[line].encode("utf-8")[: node.end_col_offset].decode("utf-8")) - len(node.attr)
            return line + 1, column
        start, _ = self._span(source, node)
        return node.lineno, start - source.starts[node.lineno - 1]

    def _names(self, source: Source, node: ast.expr, infer: bool = False) -> list[Any]:
        line, column = self._point(source, node)
        script = self.scripts[source.file]
        if infer:
            return list(script.infer(line=line, column=column))
        return list(script.goto(line=line, column=column, follow_imports=True, follow_builtin_imports=False))

    def _target(self, name: Any) -> str | None:
        if name.module_path is None:
            return None
        path = Path(name.module_path).resolve()
        source = self.graph.by_path.get(path)
        if source is None:
            return None
        if name.type == "module":
            return source.file_id
        return self.definitions.get((path, name.line, name.column))

    def _targets(self, names: list[Any]) -> set[str]:
        return {target for name in names if (target := self._target(name)) is not None}

    def _imports(self, source: Source, node: ast.Import | ast.ImportFrom) -> None:
        script = self.scripts[source.file]
        for alias in node.names:
            if alias.name == "*":
                source.diagnostic(
                    "star_import", "Wildcard import coverage relies on Jedi's static export resolution.", node.lineno
                )
                continue
            assert alias.end_lineno is not None and alias.end_col_offset is not None
            if alias.asname:
                offset = source.byte_column(alias.end_lineno - 1, alias.end_col_offset) - len(alias.asname)
            else:
                offset = source.byte_column(alias.lineno - 1, alias.col_offset)
            line = source.text[:offset].count("\n")
            column = offset - source.starts[line]
            names = list(script.goto(line=line + 1, column=column, follow_imports=True))
            for target in self._targets(names):
                self.graph.edge(source, source.file_id, target, "references", offset)
                self.graph.edge(source, source.file_id, f"{self.graph.nodes[target]['file']}::file", "imports", offset)
            if not names:
                source.diagnostic(
                    "unresolved_import", f"Import cannot be resolved statically: {alias.name}", node.lineno
                )

    def _inheritance(self, source: Source, node: ast.ClassDef) -> None:
        declaration = self.ast_nodes[node]
        targets: list[str] = []
        for base in node.bases:
            expression = base.value if isinstance(base, ast.Subscript) else base
            if not isinstance(expression, (ast.Name, ast.Attribute)):
                continue
            names = self._names(source, expression, infer=True)
            for name in names:
                if name.full_name in {"abc.ABC", "typing.Protocol", "typing_extensions.Protocol"}:
                    declaration.setdefault("tags", []).append("abstract" if name.full_name == "abc.ABC" else "protocol")
            for target in sorted(self._targets(names)):
                if self.graph.nodes[target]["kind"] == "class":
                    targets.append(target)
                    self.graph.edge(source, declaration["id"], target, "extends", declaration["offset"])
        self.bases[declaration["id"]] = targets

    def extract(self) -> list[Json]:
        """Resolve aliases, typed receiver calls, inheritance and references."""
        for file, tree in self.trees.items():
            source = self.graph.sources[file]
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    self._inheritance(source, node)
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    self._imports(source, node)
                elif isinstance(node, ast.Call):
                    if not isinstance(node.func, (ast.Name, ast.Attribute)):
                        source.record["unresolvedCalls"] += 1
                        continue
                    names = self._names(source, node.func, infer=True)
                    targets = self._targets(names)
                    if len(targets) == 1 and len(names) == 1:
                        target = next(iter(targets))
                        if self.graph.nodes[target]["kind"] == "class":
                            constructor = next(
                                (
                                    item["id"]
                                    for item in self.graph.nodes.values()
                                    if item.get("parent") == target and item["kind"] == "constructor"
                                ),
                                None,
                            )
                            target = constructor or target
                        if self.graph.nodes[target]["kind"] in {"class", "constructor", "function", "method"}:
                            start, _ = self._span(source, node)
                            self.graph.edge(source, self.graph.owner(source, start), target, "calls", start)
                    elif not names or len(names) > 1:
                        source.record["unresolvedCalls"] += 1
                elif isinstance(node, (ast.Name, ast.Attribute)) and isinstance(node.ctx, ast.Load):
                    start, _ = self._span(source, node)
                    for target in self._targets(self._names(source, node)):
                        self.graph.edge(source, self.graph.owner(source, start), target, "references", start)
        members = {
            (node.get("parent"), node["name"]): node
            for node in self.graph.nodes.values()
            if node["kind"] in {"method", "constructor"}
        }
        for child, bases in self.bases.items():
            source = self.graph.sources[self.graph.nodes[child]["file"]]
            ancestors = list(bases)
            seen: set[str] = set()
            while ancestors:
                base = ancestors.pop(0)
                if base in seen:
                    continue
                seen.add(base)
                ancestors.extend(self.bases.get(base, []))
                for (parent, name), method in members.items():
                    if parent == child and (overridden := members.get((base, name))):
                        self.graph.edge(source, method["id"], overridden["id"], "overrides", method["offset"])
        for source in self.graph.sources.values():
            if source.record["unresolvedCalls"]:
                source.diagnostic(
                    "unresolved_calls", "Dynamic or ambiguous call targets are omitted; no name matching is used."
                )
        return self.graph.results()
