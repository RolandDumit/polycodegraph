"""Swift 6.2+ semantic JSON AST extraction; SwiftPM/build hooks never run."""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .mobile_common import byte_offset, compiler_diagnostics, path, projects, run
from .model import Graph, Json, Source

KINDS = {
    "class_decl": "class",
    "struct_decl": "class",
    "protocol": "interface",
    "enum_decl": "enum",
    "extension_decl": "extension",
    "func_decl": "function",
    "constructor_decl": "constructor",
    "destructor_decl": "method",
    "var_decl": "field",
    "typealias": "typedef",
    "enum_element_decl": "enumConstant",
    "accessor_decl": "accessor",
}


def dictionaries(value: Any) -> Iterator[Json]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from dictionaries(child)
    elif isinstance(value, list):
        for child in value:
            yield from dictionaries(child)


def decl_usr(value: Any) -> str:
    """Only compiler-emitted USRs can bind a reference; textual dumps cannot."""
    return str(value.get("decl_usr", "")) if isinstance(value, dict) else ""


class SwiftGraph:
    """Use compiler USRs exclusively to bind targets and conformances."""

    def __init__(self, graph: Graph, options: Json) -> None:
        self.graph, self.options = graph, options
        self.symbols: dict[str, Json] = {}
        self.declarations: list[tuple[Source, Json, Json]] = []

    def extract(self) -> list[Json]:
        deadline = time.monotonic() + max(1.0, float(self.options.get("timeout", 120)) - 8)
        all_trees: list[tuple[Source, Json]] = []
        for module in projects(self.graph, self.options, "swift"):
            sources = [self.graph.sources[file] for file in module["files"] if Path(file).name != "Package.swift"]
            for file in module["files"]:
                if Path(file).name == "Package.swift":
                    self.graph.sources[file].diagnostic(
                        "swift_manifest", "Executable SwiftPM manifest is not analyzed or run"
                    )
            if not sources:
                continue
            with tempfile.TemporaryDirectory(prefix="polycodegraph-swift-") as temporary:
                args = [
                    self.options.get("swiftc_path", "swiftc"),
                    "-frontend",
                    "-dump-ast",
                    "-dump-ast-format",
                    "json",
                    "-module-name",
                    module["name"],
                    "-parse-as-library",
                    "-module-cache-path",
                    temporary,
                ]
                module = dict(module)
                if not module.get("sdk"):
                    sdk = os.environ.get("SDKROOT", "")
                    if not sdk and sys.platform == "darwin":
                        sdk_code, sdk_output, _ = run(
                            ["/usr/bin/xcrun", "--sdk", "macosx", "--show-sdk-path"],
                            self.graph.root,
                            max(0.1, deadline - time.monotonic()),
                        )
                        if sdk_code == 0:
                            sdk = sdk_output.strip()
                    if sdk:
                        module["sdk"] = sdk
                driver_args = [self.options.get("swiftc_path", "swiftc"), "-print-target-info"]
                for key, flag in (("sdk", "-sdk"), ("target", "-target")):
                    if module.get(key):
                        driver_args += [flag, path(self.graph, module[key]) if key == "sdk" else module[key]]
                info_code, info_output, info_errors = run(
                    driver_args, self.graph.root, max(0.1, deadline - time.monotonic())
                )
                if info_code != 0:
                    raise ValueError("Cannot discover Swift runtime paths: " + info_errors)
                runtime = json.loads(info_output).get("paths", {})
                if runtime.get("runtimeResourcePath"):
                    args += ["-resource-dir", runtime["runtimeResourcePath"]]
                for directory in runtime.get("runtimeLibraryImportPaths", []):
                    args += ["-I", directory]
                for key, flag in (("sdk", "-sdk"), ("target", "-target"), ("bridging_header", "-import-objc-header")):
                    if module.get(key):
                        args += [flag, path(self.graph, module[key]) if key != "target" else module[key]]
                for key, flag in (("import_paths", "-I"), ("framework_paths", "-F"), ("defines", "-D")):
                    for value in module.get(key, []):
                        args += [flag, path(self.graph, value) if key != "defines" else value]
                trees: list[tuple[Source, Json]] = []
                for primary in sources:
                    command = (
                        args
                        + ["-primary-file", str(primary.path)]
                        + [str(other.path) for other in sources if other is not primary]
                    )
                    code, output, errors = run(command, self.graph.root, max(0.1, deadline - time.monotonic()))
                    compiler_diagnostics([primary], errors, code != 0)
                    decoder = json.JSONDecoder()
                    remaining = output.strip()
                    while remaining:
                        tree, end = decoder.raw_decode(remaining)
                        remaining = remaining[end:].strip()
                        if not isinstance(tree, dict) or tree.get("_kind") != "source_file":
                            raise ValueError("Unsupported Swift JSON AST format; Swift 6.2+ required")
                        source = self.graph.by_path.get(Path(tree["filename"]).resolve())
                        if source:
                            trees.append((source, tree))
                            self.declare(source, tree, None, "")
                if not trees:
                    for source in sources:
                        source.diagnostic(
                            "swift_no_ast",
                            "Compiler produced no semantic AST; verify Swift version and SDK",
                            severity="error",
                        )
                all_trees.extend(trees)
        for source, tree in all_trees:
            self.relations(source, tree)
        return self.graph.results()

    def declare(self, source: Source, value: Any, parent: str | None, scope: str) -> None:
        if isinstance(value, list):
            for child in value:
                self.declare(source, child, parent, scope)
            return
        if not isinstance(value, dict):
            return
        kind = KINDS.get(value.get("_kind", ""))
        usr = value.get("usr")
        if kind and usr and "range" in value and not value.get("implicit"):
            if usr in self.symbols:
                return
            base = value.get("name", {}).get("base_name", {})
            name = base.get("name", base.get("special", "extension"))
            if kind == "extension":
                name = "extension<" + value.get("extended_type", "unknown") + ">"
            qualified = scope + name
            if kind in {"function", "constructor", "method"}:
                params = value.get("params", {}).get("params", [])
                signature = ",".join(p.get("apiName", "_") + ":" + p.get("interface_type", "?") for p in params)
                qualified += "(" + signature + ")"
                if kind == "function" and parent:
                    kind = "method"
            start = byte_offset(source, value["range"]["start"])
            end = byte_offset(source, value["range"]["end"])
            token = re.match(r"\w+|.", source.text[end:])
            end = min(len(source.text), end + (len(token[0]) if token else 0))
            tags = [value["_kind"]]
            for flag in ("async", "actor", "static"):
                if value.get(flag):
                    tags.append(flag)
            node = self.graph.declare(source, name, qualified, kind, start, max(start, end), parent, tags)
            self.symbols[usr] = node
            self.declarations.append((source, value, node))
            parent, scope = node["id"], qualified + "."
        for key, child in value.items():
            if key not in {"name", "range", "decl", "inherits"}:
                self.declare(source, child, parent, scope)

    def relations(self, source: Source, tree: Json) -> None:
        for value in dictionaries(tree):
            location = value.get("range", {})
            start = byte_offset(source, location.get("start", 0))
            owner = self.graph.owner(source, start)
            decl = value.get("decl", {})
            target = self.symbols.get(decl_usr(decl))
            if target and location and not value.get("implicit"):
                self.graph.edge(source, owner, target["id"], "references", start)
            if value.get("_kind") == "call_expr" and location:
                callee = value.get("fn", {})
                while isinstance(callee, dict) and "fn" in callee:
                    callee = callee["fn"]
                usr = decl_usr(callee.get("decl")) if isinstance(callee, dict) else ""
                called = self.symbols.get(usr)
                if called:
                    self.graph.edge(source, owner, called["id"], "calls", start)
                elif not usr:
                    source.record["unresolvedCalls"] += 1
        for origin, value, node in self.declarations:
            if origin is not source:
                continue
            inherited = value.get("inherits", {})
            targets = [(usr, "extends") for usr in inherited.get("protocols", [])]
            targets += [(entry.get("protocol", ""), "implements") for entry in inherited.get("conformances", [])]
            targets += [(inherited.get("superclass_decl_usr", ""), "extends")]
            extended = value.get("extended_type", "")
            if extended.startswith("$s") and extended.endswith("D"):
                targets.append(("s:" + extended[2:-1], "extends"))
            for usr, kind in targets:
                target = self.symbols.get(usr)
                if target:
                    self.graph.edge(source, node["id"], target["id"], kind, node["offset"])
            for override in value.get("override", []):
                usr = override.get("decl_usr", "") if isinstance(override, dict) else override
                target = self.symbols.get(usr)
                if target:
                    self.graph.edge(source, node["id"], target["id"], "overrides", node["offset"])
        source.diagnostic(
            "swift_precision",
            "Static compiler USRs; protocol witness methods and runtime dispatch are not expanded. Custom macros/build plugins are not loaded.",
        )
