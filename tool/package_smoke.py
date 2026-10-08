"""Relocate distribution, prepare assets there, and exercise the installed binary."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from smoke import Client
from workflow_smoke import run as workflow_preflight

parser = argparse.ArgumentParser()
parser.add_argument("--package", type=Path, default=Path("dist/polycodegraph"))
a = parser.parse_args()
with tempfile.TemporaryDirectory(prefix="installed package spaces ") as temp:
    # Keep the relocated package and its application under one canonical root,
    # including macOS's /var alias. Provider records use canonical source roots.
    temporary_root = Path(temp).resolve(strict=True)
    install = temporary_root / "tools"
    shutil.copytree(a.package, install)
    binary = install / ("polycodegraph.exe" if os.name == "nt" else "polycodegraph")
    root = temporary_root / "application"
    root.mkdir()
    (root / "entry.ts").write_text("export function installed() { return 42; }\n", encoding="utf-8")
    (root / "bundled.dart").write_text("int dartBundled() => 42;\n", encoding="utf-8")
    go = root / "go module"
    go.mkdir()
    (go / "go.mod").write_text("module example.com/installed\n\ngo 1.25\n", encoding="utf-8")
    (go / "service.go").write_text("package installed\nfunc GoBundled() int { return 42 }\n", encoding="utf-8")
    subprocess.run(
        [str(binary), "setup", "--root", str(root), "--languages", "typescript"],
        check=True,
    )
    client = Client(binary, root)
    try:
        arch = client.call("get_architecture")
        assert not arch["diagnostic_samples"], arch
        assert client.call("search_symbol", query="installed")["total"] == 1
        for language, symbol in [("dart", "dartBundled"), ("go", "GoBundled")]:
            assert client.call("search_symbol", query=symbol, language=language)["total"] == 1
        assets = client.call("status")["provider_health"]["providers_path"]
        assert Path(assets).resolve() == (install / "providers").resolve(), assets
        manifest_version = json.loads((install / "manifest.json").read_text())["version"]
        cli_version = subprocess.check_output([str(binary), "--version"], text=True).strip().split()[-1]
        assert manifest_version == cli_version, (manifest_version, cli_version)
        assert client.initialization["serverInfo"]["version"] == manifest_version
        subprocess.run(
            [
                sys.executable,
                "-I",
                "-c",
                (
                    "import sys; sys.path.insert(0, sys.argv[1]); "
                    "from efficiency_client import LeanAdapter, Observer; "
                    "from efficiency_binding import AsyncLeanBinding; "
                    "from efficiency_collection import fuse_pages; "
                    "from efficiency_workflow import workflow_surface; "
                    "from efficiency_mcp import WorkflowRelay; "
                    "from efficiency_transport import NativeTransport; "
                    "from efficiency_retention import RetainedContext; "
                    "assert LeanAdapter and Observer and AsyncLeanBinding and fuse_pages and workflow_surface"
                    " and WorkflowRelay and NativeTransport and RetainedContext"
                ),
                str(install / "clients"),
            ],
            cwd=install,
            check=True,
        )
        target = client.call("search_symbol", query="installed")["rows"][0][0]
        lean = client.call("inspect_change", target=target, intent="rename", format="lean", view="locations")
        assert lean["format"] == "pcg-lean-1" and not lean["sources"]
        print("Relocated native package works with adjacent TypeScript, compiled Dart and compiled Go providers")
    finally:
        client.close()
    workflow_preflight(binary, None, install / "clients/efficiency_mcp.py", adjacent=True)
    print("Relocated workflow MCP entrypoint works with its adjacent native binary")
