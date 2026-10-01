"""Native MCP integration and differential checks; never edit a source fixture."""

from __future__ import annotations

import argparse
import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path


class Client:
    def __init__(self, binary: Path, root: Path, env=None):
        self.p = subprocess.Popen(
            [str(binary), "serve", "--root", str(root)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env=env,
        )
        self.q = queue.Queue()
        self.errors = []
        self.i = 0
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(
            target=lambda: self.errors.extend(self.p.stderr.readlines()), daemon=True
        ).start()
        self.request(
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "native-validation", "version": "0.5.0"},
            },
        )
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _read(self):
        for line in self.p.stdout:
            try:
                self.q.put(json.loads(line))
            except Exception:
                self.q.put({"bad_frame": line})
        self.q.put({"process_ended": True})

    def send(self, v):
        self.p.stdin.write(json.dumps(v) + "\n")
        self.p.stdin.flush()

    def request(self, method, params):
        self.i += 1
        self.send({"jsonrpc": "2.0", "id": self.i, "method": method, "params": params})
        result = self.q.get(timeout=180)
        assert result.get("id") == self.i, result
        assert "error" not in result, result
        return result["result"]

    def call(self, name, **args):
        r = self.request("tools/call", {"name": name, "arguments": args})
        assert not r.get("isError"), r
        assert json.loads(r["content"][0]["text"]) == r["structuredContent"]
        return r["structuredContent"]

    def close(self):
        self.p.stdin.close()
        self.p.wait(timeout=15)
        assert self.p.returncode == 0, "".join(self.errors)


def clean(v):
    if isinstance(v, dict):
        return {k: clean(x) for k, x in v.items() if k not in ("generation",)}
    if isinstance(v, list):
        return [clean(x) for x in v]
    return v


def validate(binary: Path, fixture: Path, config: dict, baseline: Path | None = None):
    with tempfile.TemporaryDirectory(prefix="polycodegraph native spaces ") as temp:
        root = Path(temp)
        shutil.copytree(
            fixture,
            root,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(
                ".polycodegraph", "build", "node_modules", "target"
            ),
        )
        (root / "polycodegraph.json").write_text(json.dumps(config), encoding="utf-8")
        new = Client(binary, root)
        old = Client(baseline, root) if baseline else None
        try:
            arch = new.call("get_architecture")
            assert arch["files"] > 0, arch
            errors = [
                d
                for d in arch["diagnostic_samples"]
                if d["code"] == "provider_unavailable" or d["severity"] == "error"
            ]
            assert not errors, errors
            rows = new.call("search_symbol", query="", limit=200)["rows"]
            assert rows, arch
            if old:
                reference = old.call("get_architecture")
                assert clean(arch) == clean(reference), {
                    "architecture": (arch, reference)
                }
                assert clean(new.call("search_symbol", query="", limit=200)) == clean(
                    old.call("search_symbol", query="", limit=200)
                )
            # Compare graph relationships and source windows for every fixture symbol.
            for row in rows:
                target = row[0]
                for tool in [
                    "callers",
                    "callees",
                    "references",
                    "implementations",
                    "neighbors",
                    "dependencies",
                    "blast_radius",
                    "affected_by_change",
                ]:
                    result = new.call(tool, target=target, limit=200)
                    if old:
                        reference = old.call(tool, target=target, limit=200)
                        assert clean(result) == clean(reference), (
                            tool,
                            target,
                            result,
                            reference,
                        )
                result = new.call("snippet", target=target, context=1)
                if old:
                    assert clean(result) == clean(
                        old.call("snippet", target=target, context=1)
                    ), ("snippet", target)
                inspect = new.call("inspect_change", target=target, limit=1)
                assert all(
                    inspect[k]["generation"] == inspect["generation"]
                    for k in ["callers", "implementations", "impact"]
                )
            # Warm query invariant, and a real edit through the configured watcher.
            before = new.call("status")["metrics"]
            new.call("search_symbol", query="")
            after = new.call("status")["metrics"]
            if config.get("watch", True):
                assert (
                    before["scans"] == after["scans"]
                    and before["graph_builds"] == after["graph_builds"]
                ), (before, after)
            source = root / rows[0][3]
            text = source.read_text(encoding="utf-8")
            comment = "# edit\n" if source.suffix in (".py", ".pyi") else "// edit\n"
            source.write_text(comment + text, encoding="utf-8")
            time.sleep(0.3)
            changed = new.call("index_repository")
            assert rows[0][3] in changed["changed"], changed
            assert (
                new.call("search_symbol", query="")["generation"] != arch["generation"]
            )
            return {
                "fixture": fixture.name,
                "languages": arch["languages"],
                "symbols": arch["symbols"],
                "edges": arch["edges"],
                "differential": bool(old),
            }
        finally:
            new.close()
            if old:
                old.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--binary",
        type=Path,
        default=Path(
            "target/release/polycodegraph.exe"
            if os.name == "nt"
            else "target/release/polycodegraph"
        ),
    )
    parser.add_argument("--baseline", type=Path)
    parser.add_argument(
        "--group",
        choices=["dart", "polyglot", "mobile", "flutter", "mixed"],
        required=True,
    )
    parser.add_argument("--config", type=Path)
    a = parser.parse_args()
    base = Path(__file__).resolve().parent.parent
    config = json.loads(a.config.read_text()) if a.config else {}
    config["providers_path"] = str(base / "providers")
    fixtures = {
        "dart": [base / "test/fixtures/dart_app"],
        "polyglot": [base / "test/fixtures/polyglot", base / "test/fixtures/semantic"],
        "mobile": [base / "test/fixtures/mobile"],
        "flutter": [base / "examples/flutter_fixture"],
    }
    if a.group == "mixed":
        with tempfile.TemporaryDirectory(
            prefix="polycodegraph ten languages "
        ) as mixed:
            mixed_root = Path(mixed)
            for fixture in [
                base / "test/fixtures/dart_app",
                base / "test/fixtures/polyglot",
                base / "test/fixtures/semantic",
                base / "test/fixtures/mobile",
            ]:
                shutil.copytree(fixture, mixed_root / fixture.name)
            result = validate(
                a.binary.resolve(),
                mixed_root,
                config,
                a.baseline.resolve() if a.baseline else None,
            )
            assert len(result["languages"]) == 10, result
            print(json.dumps(result), flush=True)
        return
    for fixture in fixtures[a.group]:
        print(
            json.dumps(
                validate(
                    a.binary.resolve(),
                    fixture,
                    config,
                    a.baseline.resolve() if a.baseline else None,
                )
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
