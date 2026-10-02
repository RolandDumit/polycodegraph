"""Objective-C/Objective-C++ graph from libclang canonical cursor targets."""

from __future__ import annotations

import ctypes
from pathlib import Path
from typing import Any

from clang import cindex

from .mobile_common import byte_offset, path, projects
from .model import Graph, Json, Source
from .objc_context import objc_context

KINDS = {
    "OBJC_INTERFACE_DECL": "class",
    "OBJC_PROTOCOL_DECL": "interface",
    "OBJC_IMPLEMENTATION_DECL": "extension",
    "OBJC_CATEGORY_DECL": "extension",
    "OBJC_CATEGORY_IMPL_DECL": "extension",
    "OBJC_INSTANCE_METHOD_DECL": "method",
    "OBJC_CLASS_METHOD_DECL": "method",
    "OBJC_PROPERTY_DECL": "field",
    "OBJC_IVAR_DECL": "field",
    "FUNCTION_DECL": "function",
    "VAR_DECL": "variable",
    "ENUM_DECL": "enum",
    "ENUM_CONSTANT_DECL": "enumConstant",
    "TYPEDEF_DECL": "typedef",
    "STRUCT_DECL": "class",
    "CLASS_DECL": "class",
    "CXX_METHOD": "method",
    "CONSTRUCTOR": "constructor",
    "FIELD_DECL": "field",
}


def cursor_kind(cursor: Any) -> str:
    """Bindings can omit new attribute kinds in the bundled Clang library."""
    try:
        return str(cursor.kind.name)
    except ValueError:
        return "UNEXPOSED_CURSOR"


class ObjcGraph:
    """Keep header contracts and implementations distinct, connected by USR."""

    def __init__(self, graph: Graph, options: Json) -> None:
        self.graph, self.options = graph, options
        self.symbols: dict[str, Json] = {}
        self.locations: dict[tuple[str, int, str], Json] = {}
        self.units: list[Any] = []
        if options.get("libclang_path"):
            cindex.Config.set_library_file(options["libclang_path"])

    def source(self, cursor: Any) -> Source | None:
        file = cursor.location.file
        return self.graph.by_path.get(Path(file.name).resolve()) if file else None

    def extract(self) -> list[Json]:
        index = cindex.Index.create()
        self.overrides = cindex.conf.lib.clang_getOverriddenCursors
        self.overrides.argtypes = [
            cindex.Cursor,
            ctypes.POINTER(ctypes.POINTER(cindex.Cursor)),
            ctypes.POINTER(ctypes.c_uint),
        ]
        self.overrides.restype = None
        self.dispose_overrides = cindex.conf.lib.clang_disposeOverriddenCursors
        self.dispose_overrides.argtypes = [ctypes.POINTER(cindex.Cursor)]
        self.dispose_overrides.restype = None
        unsaved = [(str(source.path), source.text) for source in self.graph.sources.values()]
        for module in projects(self.graph, self.options, "objectivec"):
            for file in module["files"]:
                source = self.graph.sources[file]
                args = [
                    "-x",
                    "objective-c++" if file.endswith(".mm") else "objective-c",
                    "-fsyntax-only",
                    "-fblocks",
                    "-fobjc-runtime=macosx-10.12",
                    "-I",
                    str(self.graph.root),
                ]
                if module.get("arc"):
                    args.append("-fobjc-arc")
                if module.get("target"):
                    args += ["-target", module["target"]]
                if module.get("sdk"):
                    args += ["-isysroot", path(self.graph, module["sdk"])]
                if module.get("resource_dir"):
                    args += ["-resource-dir", path(self.graph, module["resource_dir"])]
                for key, flag in (("include_paths", "-I"), ("framework_paths", "-F"), ("defines", "-D")):
                    for value in module.get(key, []):
                        args += [flag, path(self.graph, value) if key != "defines" else value]
                unit = index.parse(
                    str(source.path),
                    args=args,
                    unsaved_files=unsaved,
                    options=cindex.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD,
                )
                self.units.append(unit)
                for diagnostic in unit.diagnostics:
                    diagnostic_source = self.source(diagnostic) or source
                    if diagnostic.severity >= cindex.Diagnostic.Warning:
                        diagnostic_source.diagnostic(
                            "objc_compiler",
                            str(diagnostic),
                            max(1, diagnostic.location.line),
                            "error" if diagnostic.severity >= cindex.Diagnostic.Error else "warning",
                        )
                self.declare(unit.cursor, None, "")
        for unit in self.units:
            self.relations(unit.cursor)
            objc_context(self.graph, unit.cursor)
        for source in self.graph.sources.values():
            source.diagnostic(
                "objc_static_dispatch",
                "Message edges use declared receiver/selector targets; runtime dispatch, forwarding and swizzling are not expanded.",
            )
        for source in self.graph.sources.values():
            source.record["edges"] = list({tuple(edge.values()): edge for edge in source.record["edges"]}.values())
        return self.graph.results()

    def declare(self, cursor: Any, parent: str | None, scope: str) -> None:
        source = self.source(cursor)
        kind = KINDS.get(cursor_kind(cursor))
        if cursor_kind(cursor) == "NAMESPACE":
            scope += cursor.spelling + "."
        if source and kind and cursor.spelling:
            key = (source.file, cursor.location.offset, cursor_kind(cursor))
            node = self.locations.get(key)
            if node is None:
                name = cursor.spelling
                if cursor_kind(cursor) in {"CXX_METHOD", "CONSTRUCTOR", "FUNCTION_DECL"} and cursor.type.spelling:
                    signature = ",".join(argument.type.spelling for argument in cursor.get_arguments())
                else:
                    signature = None
                prefix = (
                    "+"
                    if cursor_kind(cursor) == "OBJC_CLASS_METHOD_DECL"
                    else "-"
                    if cursor_kind(cursor) == "OBJC_INSTANCE_METHOD_DECL"
                    else ""
                )
                qualified = scope + prefix + name
                if signature is not None:
                    qualified += "(" + signature + ")"
                if cursor_kind(cursor) == "OBJC_IMPLEMENTATION_DECL":
                    qualified += ".implementation"
                if cursor_kind(cursor) in {"OBJC_CATEGORY_DECL", "OBJC_CATEGORY_IMPL_DECL"}:
                    qualified += ".category<" + cursor.get_usr() + ">"
                start, end = (
                    byte_offset(source, cursor.extent.start.offset),
                    byte_offset(source, cursor.extent.end.offset),
                )
                tags = [cursor_kind(cursor).lower()]
                if name.endswith("ViewController"):
                    tags.append("view_controller")
                node = self.graph.declare(source, name, qualified, kind, start, end, parent, tags)
                self.locations[key] = node
                usr = cursor.get_usr()
                canonical = self.symbols.get(usr)
                if usr and (canonical is None or source.file.endswith(".h")):
                    self.symbols[usr] = node
            parent, scope = node["id"], node["q"] + "."
        if source or cursor_kind(cursor) == "TRANSLATION_UNIT":
            for child in cursor.get_children():
                self.declare(child, parent, scope)

    def relations(self, cursor: Any) -> None:
        source = self.source(cursor)
        if source:
            start = byte_offset(source, cursor.location.offset)
            owner = self.graph.owner(source, start)
            reference = cursor.referenced
            target = self.symbols.get(reference.get_usr()) if reference else None
            if target and cursor_kind(cursor) not in KINDS:
                kind = (
                    "calls"
                    if cursor_kind(cursor) in {"OBJC_MESSAGE_EXPR", "CALL_EXPR"}
                    else "extends"
                    if cursor_kind(cursor) == "OBJC_SUPER_CLASS_REF"
                    else "implements"
                    if cursor_kind(cursor) == "OBJC_PROTOCOL_REF"
                    else "references"
                )
                if kind == "implements" and self.graph.nodes[owner]["kind"] not in {"class", "interface", "extension"}:
                    kind = "references"
                self.graph.edge(source, owner, target["id"], kind, start)
            elif cursor_kind(cursor) in {"OBJC_MESSAGE_EXPR", "CALL_EXPR"} and not reference:
                source.record["unresolvedCalls"] += 1
            if cursor_kind(cursor) in {
                "OBJC_IMPLEMENTATION_DECL",
                "OBJC_INSTANCE_METHOD_DECL",
                "OBJC_CLASS_METHOD_DECL",
            }:
                node = self.locations.get((source.file, cursor.location.offset, cursor_kind(cursor)))
                canonical = self.symbols.get(cursor.get_usr())
                if node and canonical and node["id"] != canonical["id"]:
                    self.graph.edge(
                        source,
                        node["id"],
                        canonical["id"],
                        "implements" if node["kind"] == "extension" else "overrides",
                        start,
                    )
            for inclusion in [cursor] if cursor_kind(cursor) == "INCLUSION_DIRECTIVE" else []:
                included = inclusion.get_included_file()
                dependency = self.graph.by_path.get(Path(included.name).resolve()) if included else None
                if dependency:
                    self.graph.edge(source, source.file_id, dependency.file_id, "imports", start)
        if source or cursor_kind(cursor) == "TRANSLATION_UNIT":
            for child in cursor.get_children():
                self.relations(child)
