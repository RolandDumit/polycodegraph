"""Rust HIR targets and syntax from rust-analyzer over standard LSP."""

from __future__ import annotations

import json
from typing import Any

from polycodegraph_adapters.lsp import LspClient
from polycodegraph_adapters.model import Graph, Json, Source
from polycodegraph_adapters.rust_project import project_model


class RustGraph:
    """Build a graph without Cargo, rustc wrappers, build scripts or proc macros."""

    def __init__(self, graph: Graph, options: Json) -> None:
        self.graph = graph
        self.options = options
        self.selections: dict[tuple[str, int], str] = {}
        self.symbols: dict[str, tuple[Source, Json]] = {}
        self.client = LspClient(
            options["rust_analyzer_path"], options["adapter_directory"], max(5, options.get("timeout", 120) - 5)
        )

    def _params(self, source: Source, offset: int) -> Json:
        return {"textDocument": {"uri": source.path.as_uri()}, "position": source.lsp_position(offset)}

    def _locations(self, result: Any) -> list[Json]:
        return result if isinstance(result, list) else [result] if isinstance(result, dict) else []

    def _target(self, location: Json) -> str | None:
        source = self.graph.uri_source(str(location.get("targetUri", location.get("uri", ""))))
        if source is None:
            return None
        selected = location.get("targetSelectionRange") or location.get("selectionRange") or location.get("range") or {}
        position = selected.get("start")
        if position is None:
            return None
        offset = source.lsp_offset(position)
        return self.selections.get((source.file, offset), source.file_id if offset == 0 else None)

    def _declare(self, source: Source, symbol: Json, parent: Json | None = None) -> None:
        name = symbol["name"]
        kind = {
            2: "module",
            3: "module",
            5: "class",
            6: "method",
            7: "field",
            8: "field",
            9: "constructor",
            10: "enum",
            11: "interface",
            12: "function",
            13: "variable",
            14: "field",
            19: "implementation",
            22: "field",
            23: "struct",
            26: "typedef",
        }.get(symbol["kind"], "symbol")
        # rust-analyzer reports type aliases as SymbolKind.TypeParameter.
        qualified = f"{parent['q']}.{name}" if parent else name
        start = source.lsp_offset(symbol["range"]["start"])
        end = source.lsp_offset(symbol["range"]["end"])
        node = self.graph.declare(source, name, qualified, kind, start, end, parent["id"] if parent else None)
        selection = source.lsp_offset(symbol["selectionRange"]["start"])
        self.selections[(source.file, selection)] = node["id"]
        self.symbols[node["id"]] = (source, symbol)
        for child in symbol.get("children", []):
            self._declare(source, child, node)

    def _implementation(self, source: Source, identifier: str, symbol: Json) -> None:
        node = self.graph.nodes[identifier]
        if node["kind"] not in {"interface", "method"}:
            return
        offset = source.lsp_offset(symbol["selectionRange"]["start"])
        result = self.client.request("textDocument/implementation", self._params(source, offset))
        for location in self._locations(result):
            target = self._target(location)
            if not target or target == identifier:
                continue
            if node["kind"] == "interface" and self.graph.nodes[target]["kind"] == "implementation":
                implementation_source, implementation = self.symbols[target]
                selection = implementation_source.lsp_offset(implementation["selectionRange"]["start"])
                definitions = self._locations(
                    self.client.request("textDocument/definition", self._params(implementation_source, selection))
                )
                resolved = {item for value in definitions if (item := self._target(value)) and item != target}
                # A definition at an impl self type resolves to its declaration.
                if len(resolved) == 1:
                    self.graph.edge(implementation_source, next(iter(resolved)), identifier, "implements", selection)
                else:
                    self.graph.edge(implementation_source, target, identifier, "implements", selection)
            elif node["kind"] == "method":
                target_source = self.graph.sources[self.graph.nodes[target]["file"]]
                self.graph.edge(target_source, target, identifier, "overrides", self.graph.nodes[target]["offset"])

    def _syntax(self, source: Source, tree: Json) -> None:
        calls: dict[int, int] = {}
        references: list[Json] = []

        def name_refs(node: Json) -> list[Json]:
            if node["kind"] == "NAME_REF":
                return [node]
            return [reference for child in node.get("children", []) for reference in name_refs(child)]

        def walk(node: Json, ancestors: list[str]) -> None:
            children = node.get("children", [])
            kind = node["kind"]
            if kind == "NAME_REF":
                references.append({**node, "ancestors": ancestors})
            if kind == "METHOD_CALL_EXPR":
                method = next((child for child in children if child["kind"] == "NAME_REF"), None)
                if method:
                    calls[method["start"][0]] = node["start"][0]
            elif kind == "CALL_EXPR":
                callee = next((child for child in children if child["type"] == "Node"), None)
                names = name_refs(callee) if callee else []
                if names:
                    calls[names[-1]["start"][0]] = node["start"][0]
                else:
                    source.record["unresolvedCalls"] += 1
            elif kind == "MACRO_CALL":
                source.diagnostic(
                    "macro_coverage",
                    "Macro expansion call graphs are not expanded; procedural macros are disabled.",
                    node["start"][1] + 1,
                )
            for child in children:
                walk(child, ancestors + [kind])

        walk(tree, [])
        for reference in references:
            offset = source.byte_offset(reference["start"][0])
            locations = self._locations(self.client.request("textDocument/definition", self._params(source, offset)))
            targets = {target for location in locations if (target := self._target(location))}
            owner = self.graph.owner(source, offset)
            for target in targets:
                self.graph.edge(source, owner, target, "references", offset)
                if "USE" in reference["ancestors"]:
                    self.graph.edge(
                        source, source.file_id, f"{self.graph.nodes[target]['file']}::file", "imports", offset
                    )
            if reference["start"][0] in calls:
                if len(targets) == 1 and len(locations) == 1:
                    target = next(iter(targets))
                    if self.graph.nodes[target]["kind"] in {"function", "method", "constructor", "struct", "enum"}:
                        self.graph.edge(
                            source, owner, target, "calls", source.byte_offset(calls[reference["start"][0]])
                        )
                elif not locations or len(locations) > 1:
                    source.record["unresolvedCalls"] += 1
        # Out-of-line modules are NAME declarations, not NAME_REF syntax. Ask
        # the resolver for their source target; never join module names by text.
        for identifier, (symbol_source, symbol) in self.symbols.items():
            if symbol_source is source and self.graph.nodes[identifier]["kind"] == "module":
                offset = source.lsp_offset(symbol["selectionRange"]["start"])
                for location in self._locations(
                    self.client.request("textDocument/definition", self._params(source, offset))
                ):
                    target = self._target(location)
                    if target and self.graph.nodes[target]["file"] != source.file:
                        self.graph.edge(
                            source, source.file_id, f"{self.graph.nodes[target]['file']}::file", "imports", offset
                        )

    def extract(self) -> list[Json]:
        """Resolve declarations, modules, references, static calls and trait impls."""
        try:
            model = project_model(self.graph, self.options)
            self.client.request(
                "initialize",
                {
                    "processId": None,
                    "rootUri": self.graph.root.as_uri(),
                    "capabilities": {
                        "general": {"positionEncodings": ["utf-16"]},
                        "textDocument": {
                            "documentSymbol": {"hierarchicalDocumentSymbolSupport": True},
                            "definition": {"linkSupport": True},
                        },
                        "experimental": {"serverStatusNotification": True},
                    },
                    "initializationOptions": {
                        "linkedProjects": [model],
                        "cargo": {"sysroot": None, "buildScripts": {"enable": False}},
                        "procMacro": {"enable": False},
                        "checkOnSave": False,
                        "files": {"watcher": "client"},
                        "diagnostics": {"enable": True},
                        "numThreads": 2,
                    },
                },
            )
            self.client.notify("initialized", {})
            self.client.ready()
            for source in self.graph.sources.values():
                self.client.notify(
                    "textDocument/didOpen",
                    {
                        "textDocument": {
                            "uri": source.path.as_uri(),
                            "languageId": "rust",
                            "version": 1,
                            "text": source.text,
                        }
                    },
                )
            for source in self.graph.sources.values():
                result = self.client.request(
                    "textDocument/documentSymbol", {"textDocument": {"uri": source.path.as_uri()}}
                )
                for symbol in result or []:
                    self._declare(source, symbol)
            for identifier, (source, symbol) in list(self.symbols.items()):
                self._implementation(source, identifier, symbol)
            for source in self.graph.sources.values():
                result = self.client.request(
                    "rust-analyzer/viewSyntaxTree", {"textDocument": {"uri": source.path.as_uri()}}
                )
                self._syntax(source, json.loads(result) if isinstance(result, str) else result)
                diagnostics = self.client.request(
                    "textDocument/diagnostic", {"textDocument": {"uri": source.path.as_uri()}}
                )
                for diagnostic in (diagnostics or {}).get("items", []):
                    source.diagnostic(
                        str(diagnostic.get("code", "rust_analyzer")),
                        diagnostic["message"],
                        diagnostic["range"]["start"]["line"] + 1,
                        "error" if diagnostic.get("severity") == 1 else "warning",
                    )
                if source.record["unresolvedCalls"]:
                    source.diagnostic("unresolved_calls", "Calls without a unique HIR target are omitted.")
            return self.graph.results()
        finally:
            self.client.close()
