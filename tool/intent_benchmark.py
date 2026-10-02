"""Deterministic pre-edit rename replay: tool-result characters, not AI token usage.
Inputs and raw responses stay local; the optional output contains aggregate counts only.
"""

from __future__ import annotations
import argparse
from collections import Counter
import json
from contextlib import closing
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time
from smoke import Client
from response_benchmark import check_manifest


def size(value):
    return len(json.dumps(value, ensure_ascii=False))


def edges(root, cache, target):
    with closing(sqlite3.connect(root / cache / "index.sqlite")) as db:
        return Counter(
            tuple(
                json.loads(r)[k]
                for k in (
                    "source",
                    "target",
                    "kind",
                    "file",
                    "line",
                    "offset",
                    "confidence",
                )
            )
            for (r,) in db.execute(
                "SELECT record FROM edges WHERE target=? AND kind='references'",
                (target,),
            )
        )


def byte_size(value):
    return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))


def replay(a):
    manifest = json.loads(a.manifest.read_text())
    check_manifest(a.snapshot, manifest)
    records = [json.loads(line) for line in a.trace.read_text().splitlines()]
    result = {
        "measurement": "Unicode characters and UTF-8 bytes of one tool-result JSON representation, broker default spaces, no protocol/text duplication; not tokens",
        "original_files": len(manifest),
        "model_runs": 0,
    }
    with tempfile.TemporaryDirectory(prefix="pcg intent replay ") as temp:
        root = Path(temp)
        shutil.copytree(a.snapshot, root, dirs_exist_ok=True)
        for version, config in [("old", a.baseline_config), ("new", a.config)]:
            cfg = json.loads(config.read_text())
            cfg.update(cache=f".polycodegraph/{version}", response_profile="compact")
            path = root / f".polycodegraph/{version}.json"
            path.parent.mkdir(exist_ok=True)
            path.write_text(json.dumps(cfg), encoding="utf-8")
        old = Client(
            a.baseline.resolve(),
            root,
            extra_args=("--config", str(root / ".polycodegraph/old.json")),
        )
        primitive = []
        excluded = Counter()
        schema_old_result = old.request("tools/list", {})
        schema_old = size(schema_old_result)
        try:
            old.call("index_repository")
            for row in records:
                if row["action"] == "edit":
                    break
                if row["action"] != "mcp":
                    continue
                tool, arg = row["args"]
                args = json.loads(arg)
                if tool in ["inspect_change", "references", "snippet"]:
                    primitive.append((tool, args, old.call(tool, **args)))
                else:
                    excluded[tool] += 1
            original = edges(root, ".polycodegraph/old", a.target)
        finally:
            old.close()
        new = Client(
            a.binary.resolve(),
            root,
            extra_args=("--config", str(root / ".polycodegraph/new.json")),
        )
        try:
            schema_new_result = new.request("tools/list", {})
            schema_new = size(schema_new_result)
            new.call("index_repository")
            before = new.call("status", detail="full")["metrics"]
            args = {
                "target": a.target,
                "intent": "rename",
                "options": {"new_name": a.new_name},
                "detail": "compact",
            }
            pages = []
            durations = []
            for _ in range(64):
                start = time.perf_counter()
                page = new.call("inspect_change", **args)
                durations.append((time.perf_counter() - start) * 1000)
                pages.append(page)
                assert (
                    page["generation"] == pages[0]["generation"]
                    and page["health_fingerprint"] == pages[0]["health_fingerprint"]
                    and not page.get("restart_required")
                )
                assert not page["evidence"]["exploration_limited"]
                if not page["next_cursor"]:
                    break
                args["cursor"] = page["next_cursor"]
            else:
                raise AssertionError("unbounded pagination")
            after = new.call("status", detail="full")["metrics"]
            expansions = []
            # Preserve explicitly marked wire/DTO windows, without treating homonyms as rename sites.
            for tool, args, _ in primitive:
                if tool == "snippet" and (
                    "dto" in str(args).lower() or "wire" in str(args).lower()
                ):
                    expansions.append(new.call(tool, **args))
            emitted = Counter()
            snippet_text = []
            for page in pages:
                symbols = page["symbols"]["rows"]
                files = page["files"]
                columns = page["evidence"]["columns"]
                for row in page["evidence"]["rows"]:
                    e = dict(zip(columns, row))
                    if (
                        e["relation"] == "references"
                        and e["target"] is not None
                        and symbols[e["target"]][0] == a.target
                    ):
                        emitted[
                            (
                                symbols[e["source"]][0],
                                a.target,
                                "references",
                                files[e["site_file"]]["file"],
                                e["site_line"],
                                e["offset"],
                                e["confidence"],
                            )
                        ] += 1
                snippet_text.extend(s["text"] for f in files for s in f["snippets"])
            snippet_text.extend(v["text"] for v in expansions if "text" in v)
            assert not original - emitted, "resolved reference evidence lost"
            assert original == edges(root, ".polycodegraph/new", a.target), (
                "primitive edge parity lost"
            )
            expected_matches = None
            if a.oracle:
                oracle = json.loads(a.oracle.read_text())
                missing = []
                total = 0
                windows = [
                    (group["file"], snippet)
                    for page in pages
                    for group in page["files"]
                    for snippet in group["snippets"]
                ]
                windows.extend((v["file"], v) for v in expansions if "text" in v)
                for file, edits in oracle["changes"].items():
                    file = str(Path(a.oracle_prefix) / file).replace("\\", "/")
                    for line, pattern, _ in edits:
                        total += 1
                        matched = False
                        for window_file, window in windows:
                            if (
                                window_file == file
                                and window["start_line"] <= line <= window["end_line"]
                            ):
                                content = window["text"].split("\n")
                                position = line - window["start_line"]
                                if (
                                    position < len(content)
                                    and pattern in content[position]
                                ):
                                    matched = True
                        if not matched:
                            missing.append((file, line))
                assert not missing, "oracle context not covered by snippets"
                expected_matches = total
            old_chars = sum(size(v) for _, _, v in primitive)
            new_chars = sum(size(v) for v in [*pages, *expansions])
            calls = len(pages) + len(expansions)
            reduction = 1 - new_chars / old_chars
            result.update(
                baseline={"collection_calls": len(primitive), "characters": old_chars, "utf8_bytes": sum(byte_size(v) for _, _, v in primitive)},
                intent={
                    "pages": len(pages),
                    "expansion_calls": len(expansions),
                    "collection_calls": calls,
                    "characters": new_chars,
                    "utf8_bytes": sum(byte_size(v) for v in [*pages, *expansions]),
                    "evidence": sum(len(p["evidence"]["rows"]) for p in pages),
                    "reference_edges_preserved": sum(original.values()),
                    "oracle_line_patterns": expected_matches,
                    "query_ms": durations,
                    "warm_scan_delta": after["scans"] - before["scans"],
                    "warm_extraction_delta": after["extractions"]
                    - before["extractions"],
                    "warm_graph_build_delta": after["graph_builds"]
                    - before["graph_builds"],
                },
                schema={
                    "baseline_characters": schema_old,
                    "intent_characters": schema_new,
                    "added_characters": schema_new - schema_old,
                    "baseline_utf8_bytes": byte_size(schema_old_result),
                    "intent_utf8_bytes": byte_size(schema_new_result),
                },
                excluded_startup_calls=dict(excluded),
                character_reduction_percent=100 * reduction,
                gate_passed=calls <= 3 and reduction >= 0.25,
            )
        finally:
            new.close()
    check_manifest(a.snapshot, manifest)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in [
        "binary",
        "baseline",
        "snapshot",
        "manifest",
        "config",
        "baseline-config",
        "trace",
    ]:
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--target", required=True)
    p.add_argument("--new-name", required=True)
    p.add_argument("--oracle", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--oracle-prefix", default="")
    a = p.parse_args()
    result = replay(a)
    text = json.dumps(result, indent=2)
    if a.output:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(text + "\n", encoding="utf-8")
    print(text)
