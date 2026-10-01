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
    subprocess.run(
        [str(binary), "setup", "--root", str(root), "--languages", "typescript"],
        check=True,
    )
    client = Client(binary, root)
    try:
        arch = client.call("get_architecture")
        assert not arch["diagnostic_samples"], arch
        assert client.call("search_symbol", query="installed")["total"] == 1
        assets = client.call("status")["provider_health"]["providers_path"]
        assert Path(assets).resolve() == (install / "providers").resolve(), assets
        assert json.loads((install / "manifest.json").read_text())["version"] == "0.5.0"
        print("Relocated native package works with adjacent provider assets")
    finally:
        client.close()
