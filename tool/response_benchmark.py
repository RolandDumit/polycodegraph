"""Replay real MCP traces on original isolated sources; reports bytes, never AI tokens.

Inputs/raw responses stay local. Only aggregated output is suitable for version control.
The same requested limits/depth are used in both modes; replay is not an agent run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from smoke import Client, clean


def size(value):
    # Match the observed broker: structuredContent OR parsed text, default JSON
    # spaces and one newline. Do not count the two MCP representations twice.
    return len((json.dumps(value, ensure_ascii=False) + "\n").encode())


def check_manifest(snapshot, manifest):
    for name, expected in manifest.items():
        path = (snapshot / name).resolve()
        assert path.is_relative_to(snapshot.resolve()), "manifest escapes snapshot"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, name


def edits(root, args):
    changes = json.loads(args[0])
    if isinstance(changes, dict):
        changes = [changes]
    staged = {}
    for edit in changes:
        path = (root / edit["file"]).resolve()
        assert path.is_relative_to(root.resolve()), "edit escapes copy"
        before = staged.get(path, path.read_text(encoding="utf-8"))
        count = before.count(edit["old"])
        assert count and count == edit.get("count", count)
        staged[path] = before.replace(edit["old"], edit["new"])
    for path, content in staged.items():
        path.write_text(content, encoding="utf-8")


def parity(tool, original, compact):
    def generations(value):
        if isinstance(value, dict):
            for key, nested in value.items():
                if key == "generation":
                    yield nested
                else:
                    yield from generations(nested)
        elif isinstance(value, list):
            for nested in value:
                yield from generations(nested)
    for value in (original, compact):
        assert set(generations(value)) == {value["generation"]}, "mixed response generations"
    if tool in ("status", "index_repository"):
        # 0.6 hashes effective graph configuration rather than raw YAML bytes.
        # Generation changes are allowed; identities/semantics are not normalized.
        if tool == "status":
            for key in ("files", "symbols", "edges"):
                assert original[key] == compact["counts"][key]
            for key in ("unresolved_calls", "dropped_edges"):
                assert original[key] == compact["coverage"][key]
            assert original["skipped_total"] == compact["coverage"]["skipped"]
            for severity in ("error", "warning", "info"):
                assert original["diagnostics"].get(severity, 0) == compact["diagnostics"]["counts"][severity]
        else:
            for key in ("changed", "deleted", "reindexed"):
                assert original[key + "_total"] == compact["update"][key]
            assert original["full"] == compact["update"]["full"]
    else:
        for key, value in original.items():
            if key == "generation":
                continue
            assert clean(compact.get(key)) == clean(value), (tool, key)


def replay(args):
    manifest = json.loads(args.manifest.read_text())
    check_manifest(args.snapshot, manifest)
    config = json.loads(args.config.read_text())
    config.pop("response_profile", None)
    aggregate = {"measurement": "UTF-8 bytes of one tool-result JSON representation in observed broker formatting (default JSON spaces + newline); not model tokens", "snapshot_verified_files": len(manifest), "replays": []}
    for trace in args.trace:
        records = [json.loads(line) for line in trace.read_text().splitlines()]
        with tempfile.TemporaryDirectory(prefix="pcg efficiency replay ") as temp:
            # Use the identical root/config for sequential executions; reset to original
            # between conditions so generation can be compared without normalizing it.
            root = Path(temp) / "project"
            results = []
            schema_bytes = []
            for binary, mode in ((args.baseline, "legacy"), (args.binary, "compact")):
                if root.exists():
                    shutil.rmtree(root)
                shutil.copytree(args.snapshot, root, symlinks=True)
                (root / "polycodegraph.json").write_text(json.dumps(config), encoding="utf-8")
                client = Client(binary.resolve(), root, extra_args=() if mode == "legacy" else ("--response-profile", "compact"))
                try:
                    schema_bytes.append(size(client.request("tools/list", {})))
                    client.call("index_repository")  # Preparation is outside replay counts.
                    responses = []
                    for record in records:
                        if record["action"] == "edit":
                            edits(root, record["args"])
                        elif record["action"] == "mcp":
                            name, arguments = record["args"]
                            responses.append((name, client.call(name, **json.loads(arguments))))
                    results.append(responses)
                finally:
                    client.close()
            tools = {}
            for (name, original), (other, compact) in zip(*results, strict=True):
                assert name == other
                # 0.5 invalid-prefix empty results acquire an explicit warning.
                parity(name, original, compact)
                row = tools.setdefault(name, {"calls": 0, "legacy_bytes": 0, "compact_bytes": 0})
                row["calls"] += 1
                row["legacy_bytes"] += size(original)
                row["compact_bytes"] += size(compact)
            original_bytes = sum(r["legacy_bytes"] for r in tools.values())
            compact_bytes = sum(r["compact_bytes"] for r in tools.values())
            aggregate["replays"].append({"case": trace.stem.split("-")[0], "tools": tools, "legacy_bytes": original_bytes, "compact_bytes": compact_bytes, "reduction_percent": round(100 * (1 - compact_bytes / original_bytes), 2), "tools_list_bytes": dict(zip(("legacy", "compact"), schema_bytes)), "parity": "passed; original fields/sites/counts checked; generation normalized for effective-config hashing"})
        print(f"replayed {trace.stem}", flush=True)
    check_manifest(args.snapshot, manifest)
    args.output.write_text(json.dumps(aggregate, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("binary", "baseline", "snapshot", "manifest", "config", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--trace", type=Path, action="append", required=True)
    replay(parser.parse_args())
