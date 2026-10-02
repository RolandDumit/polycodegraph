"""Relocate distribution, prepare assets there, and exercise the installed binary."""

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from smoke import Client

parser = argparse.ArgumentParser()
parser.add_argument("--package", type=Path, default=Path("dist/polycodegraph"))
a = parser.parse_args()
with tempfile.TemporaryDirectory(prefix="installed package spaces ") as temp:
    install = Path(temp) / "tools"
    shutil.copytree(a.package, install)
    binary = install / ("polycodegraph.exe" if os.name == "nt" else "polycodegraph")
    root = Path(temp) / "application"
    root.mkdir()
    (root / "entry.ts").write_text(
        "export function installed() { return 42; }\n", encoding="utf-8"
    )
    (root / "bundled.dart").write_text("int dartBundled() => 42;\n", encoding="utf-8")
    go = root / "go module"
    go.mkdir()
    (go / "go.mod").write_text(
        "module example.com/installed\n\ngo 1.25\n", encoding="utf-8"
    )
    (go / "service.go").write_text(
        "package installed\nfunc GoBundled() int { return 42 }\n", encoding="utf-8"
    )
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
            assert (
                client.call("search_symbol", query=symbol, language=language)["total"]
                == 1
            )
        assets = client.call("status")["provider_health"]["providers_path"]
        assert Path(assets).resolve() == (install / "providers").resolve(), assets
        manifest_version = json.loads((install / "manifest.json").read_text())["version"]
        cli_version = subprocess.check_output([str(binary), "--version"], text=True).strip().split()[-1]
        assert manifest_version == cli_version, (manifest_version, cli_version)
        assert client.initialization["serverInfo"]["version"] == manifest_version
        print(
            "Relocated native package works with adjacent TypeScript, compiled Dart and compiled Go providers"
        )
    finally:
        client.close()
