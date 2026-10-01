"""Read-only mobile project models and bounded compiler execution."""

from __future__ import annotations

import fnmatch
import json
import subprocess
import threading
from pathlib import Path
from typing import Any

from .model import Graph, Json, Source


def byte_offset(source: Source, offset: int) -> int:
    """Clang/Swift retain original UTF-8 bytes, including CRLF."""
    return len(source.text.encode("utf-8")[: max(0, offset)].decode("utf-8"))


def utf16_offset(source: Source, offset: int) -> int:
    """Kotlin IR uses original UTF-16 offsets."""
    return len(source.text.encode("utf-16-le")[: max(0, offset) * 2].decode("utf-16-le"))


def run(
    arguments: list[str], directory: Path, timeout: float, environment: dict[str, str] | None = None
) -> tuple[int, str, str]:
    """Drain bounded streams and terminate the compiler on timeout/overflow."""
    process = subprocess.Popen(
        arguments, cwd=directory, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    output, errors = bytearray(), bytearray()
    overflow = threading.Event()

    def read(stream: Any, buffer: bytearray, limit: int, fatal: bool) -> None:
        while data := stream.read(65536):
            if fatal and len(buffer) + len(data) > limit:
                overflow.set()
                process.kill()
            buffer.extend(data[: max(0, limit - len(buffer))])

    threads = [
        threading.Thread(target=read, args=(process.stdout, output, 64 * 1024 * 1024, True), daemon=True),
        threading.Thread(target=read, args=(process.stderr, errors, 8192, False), daemon=True),
    ]
    for thread in threads:
        thread.start()
    try:
        code = process.wait(timeout=timeout)
        for thread in threads:
            thread.join(timeout=3)
        if overflow.is_set():
            raise ValueError("Compiler output exceeds 64 MiB")
        return code, output.decode("utf-8"), errors.decode("utf-8", errors="replace")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)
        for stream in (process.stdout, process.stderr):
            if stream:
                stream.close()


def projects(graph: Graph, options: Json, language: str) -> list[Json]:
    """Accept data only: explicit modules/SDK paths, never executable arguments."""
    model_path = graph.root / options.get("mobile_project_path", "polycodegraph.mobile.json")
    if model_path.is_symlink() or not model_path.resolve().is_relative_to(graph.root):
        raise ValueError("Mobile project model escapes repository")
    if model_path.exists():
        if model_path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("Mobile project model exceeds size budget")
        raw = json.loads(model_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or set(raw) - {"swift", "kotlin", "objectivec"}:
            raise ValueError("Expected mobile project object with swift/kotlin/objectivec entries")
        modules = raw.get(language, [])
        if not isinstance(modules, list):
            raise ValueError("Language project entries must be arrays")
    else:
        modules = [{"name": "PolyCodeGraph", "files": list(graph.sources)}]
    allowed = {
        "name",
        "files",
        "sdk",
        "resource_dir",
        "target",
        "import_paths",
        "framework_paths",
        "include_paths",
        "defines",
        "classpath",
        "bridging_header",
        "arc",
    }
    result: list[Json] = []
    assigned: set[str] = set()
    for module in modules:
        if not isinstance(module, dict) or set(module) - allowed:
            raise ValueError("Unknown mobile module key (raw compiler arguments/plugins are unsupported)")
        for key in ("name", "sdk", "target", "bridging_header", "resource_dir"):
            if key in module and not isinstance(module[key], str):
                raise ValueError(f"{key} must be a string")
        for key in ("files", "import_paths", "framework_paths", "include_paths", "defines", "classpath"):
            value = module.get(key, [])
            if not isinstance(value, list) or any(not isinstance(item, str) or item.startswith("-") for item in value):
                raise ValueError(f"{key} must be an array of data strings")
        if "arc" in module and not isinstance(module["arc"], bool):
            raise ValueError("arc must be boolean")
        files = [
            file
            for file in graph.sources
            if any(fnmatch.fnmatchcase(file, pattern) for pattern in module.get("files", []))
        ]
        if assigned.intersection(files):
            raise ValueError("A source cannot belong to multiple mobile modules")
        assigned.update(files)
        result.append({**module, "files": files, "name": module.get("name", "PolyCodeGraph")})
    for file in graph.sources.keys() - assigned:
        graph.sources[file].diagnostic("mobile_unassigned_source", "Source is not assigned to a configured module")
    return result


def path(graph: Graph, value: str) -> str:
    """Resolve prepared SDK/source paths relative to the indexed root."""
    return str((graph.root / value).resolve())


def compiler_diagnostics(sources: list[Source], errors: str, failed: bool) -> None:
    """Missing SDK/module/type errors remain visible to the coding agent."""
    if errors.strip():
        for source in sources:
            source.diagnostic("mobile_compiler", errors.strip(), severity="error" if failed else "warning")
