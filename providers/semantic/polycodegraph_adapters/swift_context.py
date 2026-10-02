"""Swift AST regions with SourceKit declaration-offset bindings where available."""

from __future__ import annotations

import ctypes
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from .mobile_common import byte_offset
from .model import Graph, Json, Source


class SourceKit:
    """Use the SDK's trusted SourceKit; project plugins and build tools are absent."""

    def __init__(self, swiftc: str, resource_path: str | None = None, runtime_paths: list[str] | None = None) -> None:
        executable = Path(shutil.which(swiftc) or swiftc).resolve()
        directories = [executable.parent.parent / "lib"]
        if resource_path:
            # The driver resolves Xcode shims and installed platform SDK layouts.
            directories.insert(0, Path(resource_path).resolve().parent)
        library = next(
            (
                p
                for directory in directories
                for p in (
                    directory / "libsourcekitdInProc.so",
                    directory / "libsourcekitdInProc.dylib",
                    directory / "sourcekitd.framework" / "sourcekitd",
                    directory / "sourcekitd.framework" / "Versions" / "A" / "sourcekitd",
                    directory / "sourcekitdInProc.dll",
                    directory.parent / "bin" / "sourcekitdInProc.dll",
                )
                if p.is_file()
            ),
            None,
        )
        if library is None:
            raise ValueError("SourceKit library unavailable")

        class Variant(ctypes.Structure):
            _fields_ = [("data", ctypes.c_uint64 * 3)]

        if sys.platform == "win32":
            dll_directories = {library.parent, executable.parent}
            dll_directories.update(directory.parent / "bin" for directory in directories)
            dll_directories.update(Path(p).resolve() for p in (runtime_paths or []))
            # Swift installs runtime DLLs separately from compiler DLLs. Python
            # 3.8+ does not use PATH for dependent DLL lookup; admit only paths
            # inside the selected toolchain's Swift installation, never the CWD.
            installation = next((p.parent for p in executable.parents if p.name == "Toolchains"), None)
            if installation:
                for entry in os.environ.get("PATH", "").split(os.pathsep):
                    if entry:
                        directory = Path(entry).resolve()
                        if directory.is_relative_to(installation):
                            dll_directories.add(directory)
            self.dll_handles = [os.add_dll_directory(str(p)) for p in sorted(dll_directories) if p.is_dir()]
            try:
                self.lib = ctypes.CDLL(str(library))
            except OSError:
                for handle in self.dll_handles:
                    handle.close()
                raise
        else:
            self.lib = ctypes.CDLL(str(library))
        signatures = {
            "sourcekitd_request_create_from_yaml": (
                ctypes.c_void_p,
                [ctypes.c_char_p, ctypes.POINTER(ctypes.c_char_p)],
            ),
            "sourcekitd_send_request_sync": (ctypes.c_void_p, [ctypes.c_void_p]),
            "sourcekitd_response_get_value": (Variant, [ctypes.c_void_p]),
            "sourcekitd_variant_json_description_copy": (ctypes.c_void_p, [Variant]),
            "sourcekitd_request_release": (None, [ctypes.c_void_p]),
            "sourcekitd_response_dispose": (None, [ctypes.c_void_p]),
        }
        for name, (restype, argtypes) in signatures.items():
            f = getattr(self.lib, name)
            f.restype = restype
            f.argtypes = argtypes
        self.lib.sourcekitd_initialize()
        self.free = ctypes.CDLL("ucrtbase" if os.name == "nt" else None).free
        self.free.argtypes = [ctypes.c_void_p]

    def cursor(self, source: Source, offset: int, args: list[str]) -> Json:
        request = f"key.request: source.request.cursorinfo\nkey.sourcefile: {json.dumps(str(source.path))}\nkey.offset: {offset}\nkey.compilerargs: {json.dumps(args)}\n"
        error = ctypes.c_char_p()
        obj = self.lib.sourcekitd_request_create_from_yaml(request.encode(), ctypes.byref(error))
        if not obj:
            if error:
                self.free(ctypes.cast(error, ctypes.c_void_p))
            return {}
        response = self.lib.sourcekitd_send_request_sync(obj)
        try:
            raw = self.lib.sourcekitd_variant_json_description_copy(self.lib.sourcekitd_response_get_value(response))
            if not raw:
                return {}
            try:
                value = json.loads(ctypes.string_at(raw))
                return value if isinstance(value, dict) else {}
            finally:
                self.free(raw)
        finally:
            self.lib.sourcekitd_response_dispose(response)
            self.lib.sourcekitd_request_release(obj)


def swift_context(graph: Graph, source: Source, tree: Json, resolver: SourceKit | None, args: list[str]) -> Json:
    rows: list[tuple[Json, list[Json]]] = []

    def walk(v: Any, parents: list[Json]) -> None:
        if isinstance(v, dict):
            rows.append((v, parents))
            for key, child in v.items():
                if key not in {"original_init", "decl", "range", "name"}:
                    walk(child, [*parents, v])
        elif isinstance(v, list):
            for child in v:
                walk(child, parents)

    walk(tree, [])

    def site(n: Json) -> Json:
        r = n.get("range", {})
        start = byte_offset(source, r.get("start", 0))
        end = byte_offset(source, r.get("end", 0))
        token = re.match(r"\w+|.", source.text[end:])
        end += len(token[0]) if token else 0
        return {
            "line": source.text[:start].count("\n") + 1,
            "end": source.text[: max(start, end - 1)].count("\n") + 1,
            "offset": start,
            "end_offset": end,
            "scope": graph.owner(source, start),
        }

    result: Json = {
        "version": 1,
        "offset_unit": "unicode",
        "statements": [],
        "bindings": [],
        "uses": [],
        "controls": [],
        "limitations": [
            "SourceKit declaration offsets required for local bindings; no actor/alias/lifetime, callback or hypothetical type-check proof"
        ],
    }
    bindings: dict[str, Json] = {}
    for n, parents in rows:
        kind = n.get("_kind", "")
        if "range" not in n or n.get("implicit"):
            continue
        s = site(n)
        if parents and parents[-1].get("_kind") == "brace_stmt" and kind not in {"var_decl", "brace_stmt"}:
            result["statements"].append({**s, "block": parents[-1].get("range", {}).get("start", 0)})
        if kind in {"return_stmt", "break_stmt", "continue_stmt", "throw_stmt", "await_expr", "try_expr", "defer_stmt"}:
            result["controls"].append({**s, "kind": kind})
        if kind != "declref_expr":
            continue
        resolved = resolver.cursor(source, n["range"]["start"], args) if resolver else {}
        local = resolved.get("key.kind") in {
            "source.lang.swift.decl.var.local",
            "source.lang.swift.decl.var.parameter",
            "source.lang.swift.ref.var.local",
            "source.lang.swift.ref.var.parameter",
        }
        if (
            local
            and Path(resolved.get("key.filepath", "")).resolve() == source.path.resolve()
            and isinstance(resolved.get("key.offset"), int)
        ):
            offset = byte_offset(source, resolved["key.offset"])
            identifier = f"{source.file}@{offset}"
            bindings[identifier] = {
                "id": identifier,
                "name": resolved.get("key.name", "unknown"),
                "kind": "parameter" if resolved["key.kind"].endswith("parameter") else "local",
                "type": resolved.get("key.typename", "unknown"),
                "line": source.text[:offset].count("\n") + 1,
                "end": source.text[:offset].count("\n") + 1,
                "offset": offset,
                "scope": s["scope"],
            }
            write = any(p.get("_kind") == "inout_expr" for p in parents[-3:]) or bool(
                parents and parents[-1].get("dest") is n
            )
            result["uses"].append({**s, "binding": identifier, "read": not write, "write": write})
        elif not n.get("decl", {}).get("decl_usr"):
            result["uses"].append({**s, "binding": None, "read": True, "write": False})
    result["bindings"] = list(bindings.values())
    if resolver is None:
        result["limitations"].append("SourceKit unavailable: local binding coverage is incomplete")
    return result
