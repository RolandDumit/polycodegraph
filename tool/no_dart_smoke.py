"""Exercise TypeScript with PATH containing no Dart SDK or launch wrapper."""

import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path

from smoke import Client

parser = argparse.ArgumentParser()
parser.add_argument("--binary", required=True, type=Path)
parser.add_argument("--providers", type=Path)
a = parser.parse_args()
node = shutil.which("node")
assert node, "Prepare the TypeScript provider first"
assets = a.providers.resolve() if a.providers else Path(__file__).resolve().parent.parent / "providers"
with tempfile.TemporaryDirectory(prefix="no Dart SDK ") as temp:
    root = Path(temp)
    (root / "example.ts").write_text(
        "export function answer(): number { return 42; }\n", encoding="utf-8"
    )
    (root / "polycodegraph.json").write_text(
        json.dumps(
            {
                "node_path": str(Path(node).resolve()),
                "providers_path": str(assets),
                "include": ["**/*.ts"],
            }
        ),
        encoding="utf-8",
    )
    env = dict(os.environ, PATH=temp)
    client = Client(a.binary.resolve(), root, env)
    try:
        arch = client.call("get_architecture")
        assert not arch["diagnostic_samples"], arch
        assert client.call("search_symbol", query="answer")["total"] == 1
        assert client.call("status")["provider_health"]["dart"]["available"] is False
        assert client.call("inspect_change", target="answer", intent="explain_symbol")["intent"] == "explain_symbol"
        print("TypeScript MCP and intents work with no Dart SDK on PATH")
    finally:
        client.close()
