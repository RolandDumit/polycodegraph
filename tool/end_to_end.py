"""Release MCP timing and Linux process-tree RSS, including provider processes."""

import argparse
import json
import shutil
import tempfile
import threading
import time
from pathlib import Path

from benchmark import rss_tree
from smoke import Client


def measure(binary, fixture, config):
    with tempfile.TemporaryDirectory(prefix="polycodegraph e2e spaces ") as temp:
        root = Path(temp)
        shutil.copytree(
            fixture,
            root,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(
                ".polycodegraph", "build", "target", "node_modules"
            ),
        )
        (root / "polycodegraph.json").write_text(json.dumps(config), encoding="utf-8")
        client = Client(binary, root)
        stop = threading.Event()
        peak = [0]

        def sampler():
            while not stop.wait(0.025):
                peak[0] = max(peak[0], rss_tree(client.p.pid))

        thread = threading.Thread(target=sampler, daemon=True)
        thread.start()
        try:
            start = time.perf_counter()
            arch = client.call("get_architecture")
            first_ms = (time.perf_counter() - start) * 1000
            assert not [
                d for d in arch["diagnostic_samples"] if d["severity"] == "error"
            ], arch
            target = client.call("search_symbol", query="", kind="method", limit=1)[
                "rows"
            ][0][0]
            samples = []
            start = time.perf_counter()
            while time.perf_counter() - start < 31:
                query_start = time.perf_counter()
                client.call("callers", target=target, limit=20)
                samples.append((time.perf_counter() - query_start) * 1000)
                time.sleep(0.1)
            source = root / target.split("::")[0]
            source.write_text(
                "// benchmark edit\n" + source.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            start = time.perf_counter()
            update = client.call("index_repository")
            update_ms = (time.perf_counter() - start) * 1000
            status = client.call("status")
            samples.sort()
            return {
                "binary": binary.name,
                "fixture": fixture.name,
                "first_index_ms": first_ms,
                "median_ms": samples[len(samples) // 2],
                "p95_ms": samples[len(samples) * 95 // 100],
                "samples": len(samples),
                "duration_seconds": 31,
                "update_ms": update_ms,
                "reindexed": update["reindexed_total"],
                "symbols": arch["symbols"],
                "edges": arch["edges"],
                "phases_ms": {
                    k: v
                    for k, v in status.get("metrics", {}).items()
                    if k.endswith("_ms")
                },
                "peak_tree_rss_bytes": peak[0] or None,
            }
        finally:
            stop.set()
            thread.join()
            client.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rust", type=Path, required=True)
    parser.add_argument("--dart", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    a = parser.parse_args()
    base = Path(__file__).resolve().parent.parent
    config = json.loads(a.config.read_text()) if a.config else {}
    config["providers_path"] = str(base / "providers")
    results = []
    for fixture in [base / "test/fixtures/polyglot", base / "examples/flutter_fixture"]:
        for binary in [a.dart.resolve(), a.rust.resolve()]:
            result = measure(binary, fixture, config)
            print(json.dumps(result), flush=True)
            results.append(result)
    report = {
        "results": results,
        "note": "Separate cold indexing, update and repeated MCP round trips for 31 seconds (including a 30-second reconciliation). RSS includes live provider descendants; Linux sampled peak, not allocation volume. Shared filesystem caches; no token-savings claim.",
    }
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
