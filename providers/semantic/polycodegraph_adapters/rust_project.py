"""Build read-only rust-analyzer crate models without Cargo or build execution."""

from __future__ import annotations

import json
import platform
import sys
import tomllib
from pathlib import Path
from typing import Any

from polycodegraph_adapters.model import Graph, Json


def read_toml(path: Path, root: Path) -> Json:
    """Accept local regular manifests only, including workspace inheritance."""
    if path.is_symlink() or not path.resolve().is_relative_to(root) or path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError(f"Unsafe or oversized Rust manifest: {path}")
    with path.open("rb") as stream:
        return tomllib.load(stream)


def _workspace(manifest: Path, root: Path) -> tuple[Path, Json]:
    directory = manifest.parent
    while directory.is_relative_to(root):
        candidate = directory / "Cargo.toml"
        if candidate.is_file():
            data = read_toml(candidate, root)
            if "workspace" in data:
                return directory, data["workspace"]
        if directory == root:
            break
        directory = directory.parent
    return manifest.parent, {}


def _host_cfg() -> list[str]:
    operating_system = "windows" if sys.platform == "win32" else "macos" if sys.platform == "darwin" else "linux"
    machine = platform.machine().lower()
    architecture = (
        "aarch64" if machine in {"arm64", "aarch64"} else "x86_64" if machine in {"amd64", "x86_64"} else machine
    )
    family = "windows" if sys.platform == "win32" else "unix"
    return [
        family,
        f'target_family="{family}"',
        f'target_os="{operating_system}"',
        f'target_arch="{architecture}"',
        f'target_pointer_width="{64 if sys.maxsize > 2**32 else 32}"',
        "debug_assertions",
    ]


def _sanitize_project(data: Json, directory: Path, graph: Graph, options: Json) -> Json:
    crates: list[Json] = []
    for raw in data.get("crates", []):
        module = (directory / raw["root_module"]).resolve()
        # External crate sources may be explicitly described by the project;
        # their declarations never enter repository graph records.
        crates.append(
            {
                "root_module": str(module),
                "edition": raw.get("edition", "2021"),
                "display_name": raw.get("display_name", module.stem),
                "deps": raw.get("deps", []),
                "cfg": raw.get("cfg", []) + options.get("rust_cfg", []),
                "env": {},
                "is_workspace_member": module in graph.by_path,
            }
        )
    if not crates:
        raise ValueError("No crates in rust-project.json")
    result: Json = {"crates": crates}
    if options.get("rust_sysroot_src"):
        result["sysroot_src"] = options["rust_sysroot_src"]
    return result


def project_model(graph: Graph, options: Json) -> Json:
    """Map local Cargo packages/path dependencies, or sanitize rust-project.json.

    Cargo scripts, toolchain overrides, proc-macro libraries, runnables, project
    commands and build hooks are never passed to the language server.
    """
    explicit = graph.root / "rust-project.json"
    if explicit.is_file():
        if explicit.is_symlink() or explicit.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("Unsafe rust-project.json")
        return _sanitize_project(json.loads(explicit.read_text(encoding="utf-8")), graph.root, graph, options)
    manifests: dict[Path, Json] = {}
    standalone: list[Path] = []
    for source in graph.sources.values():
        directory = source.path.parent
        while directory.is_relative_to(graph.root):
            manifest = directory / "Cargo.toml"
            if manifest.is_file():
                manifests[manifest] = read_toml(manifest, graph.root)
                break
            if directory == graph.root:
                standalone.append(source.path)
                break
            directory = directory.parent
    crates: list[Json] = []
    package_crates: dict[Path, int] = {}
    for manifest, data in sorted(manifests.items()):
        if "package" not in data:
            continue
        package = data["package"]
        _, workspace = _workspace(manifest, graph.root)
        edition = package.get("edition", "2021")
        if isinstance(edition, dict):
            edition = workspace.get("package", {}).get("edition", "2021")
        cfg = _host_cfg() + options.get("rust_cfg", [])
        features = data.get("features", {})
        active = ["default"] if "default" in features else []
        seen: set[str] = set()
        while active:
            feature = active.pop()
            if feature in seen or "/" in feature or feature.startswith("dep:"):
                continue
            seen.add(feature)
            cfg.append(f'feature="{feature}"')
            active.extend(features.get(feature, []))
        library = manifest.parent / data.get("lib", {}).get("path", "src/lib.rs")
        targets = [library, manifest.parent / "src/main.rs"]
        targets.extend(
            manifest.parent / target.get("path", f"src/bin/{target['name']}.rs") for target in data.get("bin", [])
        )
        targets.extend(path for path in graph.by_path if path.parent == manifest.parent / "src/bin")
        for target in dict.fromkeys(targets):
            if target.resolve() not in graph.by_path:
                continue
            index = len(crates)
            if target == library or manifest.parent not in package_crates:
                package_crates[manifest.parent] = index
            crates.append(
                {
                    "root_module": str(target),
                    "edition": str(edition),
                    "display_name": package["name"].replace("-", "_"),
                    "deps": [],
                    "cfg": sorted(set(cfg)),
                    "env": {},
                    "is_workspace_member": True,
                }
            )
    for path in standalone:
        # Standalone files are explicitly separate crates. A file attached by a
        # mod declaration can also share the VFS, but IDs remain file-scoped.
        crates.append(
            {
                "root_module": str(path),
                "edition": "2021",
                "display_name": path.stem,
                "deps": [],
                "cfg": _host_cfg() + options.get("rust_cfg", []),
                "env": {},
            }
        )
    for manifest, data in sorted(manifests.items()):
        workspace_root, workspace = _workspace(manifest, graph.root)
        dependencies: dict[str, Any] = dict(data.get("dependencies", {}))
        for target in data.get("target", {}).values():
            dependencies.update(target.get("dependencies", {}))
        local_dependencies: list[Json] = []
        external: list[str] = []
        for name, specification in dependencies.items():
            base = manifest.parent
            if isinstance(specification, dict) and specification.get("workspace"):
                specification = workspace.get("dependencies", {}).get(name, {})
                base = workspace_root
            dependency_path = (
                (base / specification["path"]).resolve()
                if isinstance(specification, dict) and "path" in specification
                else None
            )
            if dependency_path is not None and dependency_path in package_crates:
                local_dependencies.append({"crate": package_crates[dependency_path], "name": name.replace("-", "_")})
            else:
                external.append(name)
        for crate in crates:
            if Path(crate["root_module"]).is_relative_to(manifest.parent):
                crate["deps"] = list(local_dependencies)
                own_library = package_crates.get(manifest.parent)
                if own_library is not None and crate is not crates[own_library]:
                    crate["deps"].append({"crate": own_library, "name": crates[own_library]["display_name"]})
        if external:
            for source in graph.sources.values():
                if source.path.is_relative_to(manifest.parent):
                    source.diagnostic(
                        "external_crates",
                        "External/unindexed crates are not loaded automatically: " + ", ".join(sorted(external)),
                    )
    result: Json = {"crates": crates}
    if options.get("rust_sysroot_src"):
        result["sysroot_src"] = options["rust_sysroot_src"]
    if not crates:
        raise ValueError("No indexed crate roots; include src/lib.rs/src/main.rs or provide rust-project.json")
    return result
