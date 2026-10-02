"""Compiler/AST-bound region metadata; no code execution or guessed refactoring."""

from __future__ import annotations

import ast
import symtable
from pathlib import Path
from typing import Any

from .model import Json, Source


def python_context(source: Source, tree: ast.AST, script: Any, declarations: dict[ast.AST, Json]) -> Json:
    parents: dict[ast.AST, tuple[ast.AST, str]] = {}
    for node in ast.walk(tree):
        for field, value in ast.iter_fields(node):
            for child in value if isinstance(value, list) else [value]:
                if isinstance(child, ast.AST):
                    parents[child] = (node, field)

    def scope(node: ast.AST) -> str:
        cursor: ast.AST | None = node
        while cursor is not None:
            if isinstance(cursor, (ast.FunctionDef, ast.AsyncFunctionDef)) and cursor in declarations:
                return str(declarations[cursor]["id"])
            cursor = parents[cursor][0] if cursor in parents else None
        return source.file_id

    tables = {}

    def collect_tables(table: Any) -> None:
        for child in table.get_children():
            tables[child.get_lineno(), child.get_name()] = child
            collect_tables(child)

    collect_tables(symtable.symtable(source.text, str(source.path), "exec"))
    namespaces = {
        str(declaration["id"]): tables.get((node.lineno, node.name))
        for node, declaration in declarations.items()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    def site(node: Any) -> Json:
        line = int(node.lineno)
        end_line = int(getattr(node, "end_lineno", line))
        start = source.byte_column(line - 1, int(node.col_offset))
        end = source.byte_column(end_line - 1, int(getattr(node, "end_col_offset", node.col_offset)))
        return {"line": line, "end": end_line, "offset": start, "end_offset": end, "scope": scope(node)}

    result: Json = {
        "version": 1,
        "offset_unit": "unicode",
        "statements": [],
        "bindings": [],
        "uses": [],
        "controls": [],
        "limitations": [
            "CPython lexical namespaces + Jedi definition locations; dynamic rebinding, globals/dynamic namespaces, decorators, aliases, callback execution and hypothetical type-check remain unverified"
        ],
    }
    bound: dict[tuple[int, int], Json] = {}
    canonical: dict[tuple[str, str], Json] = {}
    for node in sorted(ast.walk(tree), key=lambda n: (getattr(n, "lineno", 0), getattr(n, "col_offset", 0))):
        if scope(node) == source.file_id:
            continue
        if isinstance(node, ast.arg) or isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            name = node.arg if isinstance(node, ast.arg) else node.id
            point = site(node)
            column = point["offset"] - source.starts[node.lineno - 1]
            table = namespaces.get(point["scope"])
            if table is None or name not in table.get_identifiers():
                continue
            symbol = table.lookup(name)
            if not symbol.is_local():
                continue
            binding = {
                **point,
                "id": f"{source.file}@{point['offset']}",
                "name": name,
                "kind": "parameter" if isinstance(node, ast.arg) else "local",
                "type": "unknown",
            }
            key = (point["scope"], name)
            if key not in canonical:
                canonical[key] = binding
                result["bindings"].append(binding)
            bound[(node.lineno, column)] = canonical[key]
    for node in ast.walk(tree):
        if isinstance(node, ast.stmt):
            parent, field = parents.get(node, (tree, "body"))
            if field in {"body", "orelse", "finalbody"}:
                result["statements"].append({**site(node), "block": f"{getattr(parent, 'lineno', 0)}:{field}"})
        control = (
            "return"
            if isinstance(node, ast.Return)
            else "break"
            if isinstance(node, ast.Break)
            else "continue"
            if isinstance(node, ast.Continue)
            else "await"
            if isinstance(node, ast.Await)
            else "throw"
            if isinstance(node, ast.Raise)
            else "yield"
            if isinstance(node, (ast.Yield, ast.YieldFrom))
            else None
        )
        if control:
            result["controls"].append({**site(node), "kind": control})
        if isinstance(node, ast.Name):
            point = site(node)
            column = point["offset"] - source.starts[node.lineno - 1]
            targets = script.goto(line=node.lineno, column=column, follow_imports=False)
            matches = [
                bound[(n.line, n.column)]
                for n in targets
                if n.module_path is not None
                and Path(n.module_path).resolve() == source.path.resolve()
                and (n.line, n.column) in bound
            ]
            matches = list({b["id"]: b for b in matches}.values())
            if len(matches) == 1:
                binding = matches[0]
                if binding["offset"] == point["offset"]:
                    continue
                use_parent = parents.get(node, (None, ""))[0]
                write = isinstance(node.ctx, ast.Store)
                result["uses"].append(
                    {
                        **point,
                        "binding": binding["id"],
                        "read": not write or isinstance(use_parent, ast.AugAssign),
                        "write": write,
                    }
                )
    return result
