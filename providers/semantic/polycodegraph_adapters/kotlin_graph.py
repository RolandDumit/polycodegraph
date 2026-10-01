"""Kotlin K2 resolved IR extraction using only the trusted bundled plugin."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

from .mobile_common import compiler_diagnostics, path, projects, run, utf16_offset
from .model import Graph, Json


class KotlinGraph:
    """Consume symbol identities, superclass types and override links from IR."""

    def __init__(self, graph: Graph, options: Json) -> None:
        self.graph, self.options = graph, options

    def extract(self) -> list[Json]:
        directory = Path(self.options["adapter_directory"]).parent / "kotlin"
        libraries = directory / ".tools" / "kotlinc" / "lib"
        plugin = directory / ".tools" / "graph-plugin.jar"
        compiler = libraries / "kotlin-compiler.jar"
        if not compiler.is_file() or not plugin.is_file():
            raise ValueError("Prepare Kotlin with dart run tool/setup_providers.dart --kotlin")
        deadline = time.monotonic() + max(1.0, float(self.options.get("timeout", 120)) - 8)
        for module in projects(self.graph, self.options, "kotlin"):
            sources = [self.graph.sources[file] for file in module["files"]]
            if not sources:
                continue
            with tempfile.TemporaryDirectory(prefix="polycodegraph-kotlin-") as temporary:
                output = Path(temporary) / "graph.json"
                classpath = [str(libraries / "kotlin-stdlib.jar"), str(libraries / "annotations-13.0.jar")]
                classpath += [path(self.graph, value) for value in module.get("classpath", [])]
                args = [
                    self.options.get("java_path", "java"),
                    "-Dfile.encoding=UTF-8",
                    "-cp",
                    str(libraries / "*"),
                    "org.jetbrains.kotlin.cli.jvm.K2JVMCompiler",
                    "-no-stdlib",
                    "-no-reflect",
                    "-module-name",
                    module["name"],
                    "-classpath",
                    os.pathsep.join(classpath),
                    "-Xplugin=" + str(plugin),
                    "-d",
                    str(Path(temporary) / "classes"),
                ]
                args += [str(source.path) for source in sources]
                env = {**os.environ, "POLYCODEGRAPH_KOTLIN_OUTPUT": str(output)}
                code, _, errors = run(args, directory, max(0.1, deadline - time.monotonic()), env)
                compiler_diagnostics(sources, errors, code != 0)
                if not output.exists():
                    for failed_source in sources:
                        failed_source.diagnostic(
                            "kotlin_no_ir",
                            "K2 could not resolve this module; prepare its classpath/SDK or fix diagnostics",
                            severity="error",
                        )
                    continue
                if output.stat().st_size > 64 * 1024 * 1024:
                    raise ValueError("Kotlin graph exceeds size budget")
                raw = json.loads(output.read_text(encoding="utf-8"))
                symbols: dict[str, Json] = {}
                for row in raw["nodes"]:
                    source = self.graph.by_path.get(Path(row["file"]).resolve())
                    if not source:
                        continue
                    start, end = utf16_offset(source, row["start"]), utf16_offset(source, row["end"])
                    parent = symbols.get(row["parent"])
                    node = self.graph.declare(
                        source,
                        row["name"],
                        row["qualified"],
                        row["kind"],
                        start,
                        max(start, end),
                        parent["id"] if parent else None,
                        row["tags"],
                    )
                    symbols[row["key"]] = node
                for row in raw["edges"]:
                    source = self.graph.by_path.get(Path(row["file"]).resolve())
                    if source and row["kind"] == "dynamicCall":
                        source.record["unresolvedCalls"] += 1
                        continue
                    origin, target = symbols.get(row["source"]), symbols.get(row["target"])
                    if source and origin and target:
                        kind = row["kind"]
                        if kind == "inherits":
                            kind = "implements" if target["kind"] == "interface" else "extends"
                        self.graph.edge(source, origin["id"], target["id"], kind, utf16_offset(source, row["start"]))
                        if target["file"] != source.file:
                            self.graph.edge(source, source.file_id, target["file"] + "::file", "imports", 0)
                for module_source in sources:
                    module_source.diagnostic(
                        "kotlin_precision",
                        "K2 static targets; Gradle/KAPT/KSP/Compose and project compiler plugins are not run. Provide prepared JAR classpaths; dynamic callbacks and Java cross-language graph targets are omitted.",
                    )
        return self.graph.results()
