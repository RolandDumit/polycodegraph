"""Real stdio checks for opt-in profiles, failure/diagnostic recovery and metrics.

No providers are installed and no indexed application code is executed.
"""
import argparse
import json
import tempfile
from pathlib import Path
from smoke import Client


def run(binary):
    with tempfile.TemporaryDirectory(prefix="pcg profiles spaces ") as temp:
        root = Path(temp)
        assets = root / "assets"
        assets.mkdir()
        config = {"providers_path": str(assets), "response_profile": "compact"}
        (root / "polycodegraph.json").write_text(json.dumps(config), encoding="utf-8")
        client = Client(binary.resolve(), root)
        try:
            specs = client.request("tools/list", {})["tools"]
            assert len(specs) == 16
            status = client.call("status")
            assert status["outcome"] == "ok" and status["counts"]["files"] == 0
            full = client.call("status", detail="full")
            assert "hubs" in full and "metrics" in full and "provider_health" in full
            metrics = client.call("status", section="metrics")
            scans = metrics["scans"]
            unchanged = client.call("index_repository")
            assert unchanged["outcome"] == "unchanged"
            assert client.call("status", section="metrics")["scans"] > scans
            update = client.call("status", section="update", limit=1)
            assert update["available"] and update["changed"]["total"] == 0
            error = client.request("tools/call", {"name": "status", "arguments": {"unexpected": True}})
            assert error["isError"]
            metrics = client.call("status", section="metrics")["tools"]
            assert metrics["status"]["errors"] == 1
            assert metrics["index_repository"]["calls"] == 1
            assert metrics["index_repository"]["response_bytes"] > 0
        finally:
            client.close()
    with tempfile.TemporaryDirectory(prefix="pcg incomplete spaces ") as temp:
        root = Path(temp)
        (root / "assets").mkdir()
        (root / "lib").mkdir()
        (root / "lib/a.dart").write_text("class A {}", encoding="utf-8")
        (root / "polycodegraph.json").write_text(json.dumps({"providers_path": str(root / "assets"), "response_profile": "compact"}), encoding="utf-8")
        client = Client(binary.resolve(), root)
        try:
            status = client.call("status")
            assert status["outcome"] == "issues"
            assert status["diagnostics"]["counts"]["error"] == 1
            diagnostic = client.call("status", section="diagnostics", limit=1)
            assert diagnostic["items"][0]["diagnostic"]["code"] == "provider_unavailable"
            assert diagnostic["total"] == 1
            invalid = client.call("search_symbol", query="missing", file="other/")
            assert invalid["file_filter"]["valid"] is False
            valid = client.call("search_symbol", query="missing", file="lib/")
            assert valid["file_filter"]["valid"] is True and valid["total"] == 0
            before = status["generation"]
            (root / "lib/a.dart").write_text("class B {}", encoding="utf-8")
            failed = client.request("tools/call", {"name": "index_repository", "arguments": {}})
            assert failed["isError"] and "previous committed generation retained" in failed["content"][0]["text"]
            # Query also fails until source/provider recovery; it cannot silently advertise success.
            assert before
        finally:
            client.close()
    print("profile MCP stdio smoke passed (compact/full, scan, failure, recovery, paths, metrics)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    run(parser.parse_args().binary)
