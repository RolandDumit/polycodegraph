"""Compare release engines with the same deterministic graph and source corpus."""

import argparse
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path


def rss_tree(pid):
    try:
        text = Path(f"/proc/{pid}/status").read_text()
        memory = next(
            int(line.split()[1]) * 1024
            for line in text.splitlines()
            if line.startswith("VmRSS:")
        )
        # Include provider subprocesses, avoiding thread-level duplicate RSS.
        children = set()
        for task in Path(f"/proc/{pid}/task").iterdir():
            children.update(map(int, (task / "children").read_text().split()))
        return memory + sum(rss_tree(child) for child in children)
    except (OSError, StopIteration):
        return 0


def measured(command):
    p = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    peak = 0
    while p.poll() is None:
        peak = max(peak, rss_tree(p.pid))
        time.sleep(0.025)
    out, err = p.communicate()
    assert p.returncode == 0, err
    result = json.loads(out)
    result["peak_tree_rss_bytes"] = peak or None
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rust", required=True, type=Path)
    parser.add_argument("--dart", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    a = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="poly graph benchmark ") as temp:
        root = Path(temp)
        (root / "bench.dart").write_text("// corpus\n" + " " * 1048576)
        results = [
            measured([str(a.dart.resolve()), temp]),
            measured([str(a.rust.resolve()), temp]),
        ]
        persistence = [
            measured([str(a.dart.resolve()), temp, "--storage"]),
            measured([str(a.rust.resolve()), temp, "--storage"]),
        ]
    ratio = results[0]["median_ms"] / results[1]["median_ms"]
    report = {
        "results": results,
        "persistence": persistence,
        "machine": __import__("platform").platform(),
        "cpu": next(
            (
                line.split(":", 1)[1].strip()
                for line in Path("/proc/cpuinfo").read_text().splitlines()
                if line.startswith("model name")
            ),
            "unknown",
        )
        if Path("/proc/cpuinfo").exists()
        else "unavailable",
        "median_speedup": ratio,
        "criterion_met": ratio >= 2,
        "platform": os.name,
        "note": "Synthetic graph workload; not a token-savings or end-to-end provider benchmark. RSS sampling is Linux-only.",
    }
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    assert ratio >= 2, report


if __name__ == "__main__":
    main()
