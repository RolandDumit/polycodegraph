"""Real stdio intent checks on prepared native semantic fixtures; never installs providers."""

import argparse
import json
import shutil
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from smoke import Client, clean

INTENTS = [
    "rename",
    "change_signature",
    "find_tests",
    "review_change",
    "explain_symbol",
    "trace_flow",
    "move_symbol",
    "remove_symbol",
    "replace_dependency",
    "extract_symbol",
]


def collect(client, args):
    pages = []
    for _ in range(64):
        v = client.call("inspect_change", **args)
        pages.append(v)
        assert not v.get("restart_required"), v
        assert len(json.dumps(v, separators=(",", ":"), ensure_ascii=False)) <= v["budget"]["max_chars"]
        assert v["generation"] == pages[0]["generation"] and v["health_fingerprint"] == pages[0]["health_fingerprint"]
        if not v["next_cursor"]:
            return pages
        args = dict(args, cursor=v["next_cursor"])
    raise AssertionError("unbounded context pages")


def validate(binary, root, config, baseline=None, baseline_config=None):
    config_path = root / ".polycodegraph/intent-config.json"
    config_path.parent.mkdir(exist_ok=True)
    config_path.write_text(json.dumps(config), encoding="utf-8")
    client = Client(binary.resolve(), root, extra_args=("--config", str(config_path)))
    old = None
    if baseline:
        old_path = root / ".polycodegraph/intent-baseline.json"
        old_path.write_text(
            json.dumps(dict(baseline_config, cache=".polycodegraph/intent-baseline")),
            encoding="utf-8",
        )
        old = Client(baseline.resolve(), root, extra_args=("--config", str(old_path)))
    try:
        arch = client.call("get_architecture", detail="full")
        assert arch["files"] > 0 and not [d for d in arch["diagnostic_samples"] if d["severity"] == "error"], [
            d for d in arch["diagnostic_samples"] if d["severity"] == "error"
        ]
        rows = client.call("search_symbol", query="", limit=200, detail="full")["rows"]
        targets = {}
        with closing(sqlite3.connect(root / ".polycodegraph/index.sqlite")) as database:
            records = {f: json.loads(r) for f, r in database.execute("SELECT path,record FROM files")}
        for row in rows:
            suffix = Path(row[3]).suffix
            if suffix in [".h", ".mm"]:
                suffix = ".m"
            if suffix in [".cjs", ".mjs", ".jsx"]:
                suffix = ".js"
            if suffix == ".tsx":
                suffix = ".ts"
            if suffix not in targets and row[1] in ["method", "function", "field"]:
                targets[suffix] = row
        if old:
            old_arch = old.call("get_architecture", detail="full")
            assert not [d for d in old_arch["diagnostic_samples"] if d["severity"] == "error"], [
                d for d in old_arch["diagnostic_samples"] if d["severity"] == "error"
            ]
        checked = []
        for suffix, row in targets.items():
            target, file = row[0], row[3]
            reference = client.call("references", target=target, limit=200, detail="full")
            rename = collect(client, {"target": target, "intent": "rename"})
            assert sum(len(p["evidence"]["rows"]) for p in rename) >= reference["total"]
            # The optional projection must preserve every distinct semantic site
            # across real adapters, including same-line offsets and confidence.
            from efficiency_collection import fuse_pages, normalized_inventory
            from efficiency_workflow import workflow_arguments, workflow_surface
            from post08_smoke import inventory
            from post08_smoke import pages as lean_pages

            catalog = client.request("tools/list", {})["tools"]
            audit = collect(client, {"target": target, "intent": "rename", "view": "locations"})
            lean = lean_pages(client, {"target": target, "intent": "rename", "view": "locations", "format": "lean"})
            assert inventory(audit) == inventory(lean, True), (suffix, "lean rename sites")
            assert all(not p["sources"] for p in lean), (suffix, "locations source")
            assert lean[-1]["completion"]["required_inventory"]["remaining_known"] == 0
            for intent in INTENTS:
                options = {}
                t = target
                if intent == "move_symbol":
                    options = {"destination": "proposed/" + Path(file).name}
                if intent == "extract_symbol":
                    candidates = [
                        r
                        for f, r in records.items()
                        if "extraction." in f.lower()
                        and (".m" if Path(f).suffix in [".h", ".mm"] else Path(f).suffix) == suffix
                    ]
                    if not candidates:
                        candidates = [
                            r
                            for f, r in records.items()
                            if Path(f).suffix == suffix and r.get("intent", {}).get("ast", {}).get("statements")
                        ]
                    if not candidates:
                        raise AssertionError(("missing provider AST metadata", suffix))
                    record = candidates[0]
                    ast = record.get("intent", {}).get("ast", {})
                    statements = ast.get("statements", [])
                    if not statements:
                        raise AssertionError(("missing AST statements", suffix, record["file"]))
                    statement = next(
                        (v for v in statements if any(u["line"] == v["line"] for u in ast.get("uses", []))),
                        statements[0],
                    )
                    t = record["file"]
                    options = {
                        "file": t,
                        "start_line": statement["line"],
                        "end_line": statement["end"],
                    }
                if intent == "review_change":
                    t = file
                    options = {"capture_baseline": True}
                pages = collect(client, {"target": t, "intent": intent, "options": options})
                workflow = workflow_surface(catalog, intent)
                workflow_args = workflow_arguments(
                    workflow,
                    {
                        "target": t,
                        "intent": intent,
                        "options": options,
                        "format": "lean",
                        "view": "locations",
                        "budget": {"max_chars": 100000},
                    },
                )
                workflow_pages = lean_pages(client, workflow_args)
                fused = fuse_pages(workflow_pages)
                assert normalized_inventory(workflow_pages) == normalized_inventory(fused), (
                    suffix,
                    intent,
                    "fused inventory",
                )
                assert all("environment_fingerprint" in p["snapshot"] for p in workflow_pages)
                if intent == "extract_symbol":
                    assert (
                        pages[0]["outcome"] == "partial"
                        and pages[0]["facts"]["ast_region"]["exact_statement_boundaries"]
                    )
                    assert pages[0]["facts"]["suggested_signature"] is None
                    assert ast.get("bindings"), (
                        "missing local/parameter identities",
                        suffix,
                        ast.get("limitations"),
                    )
                    assert any(u.get("binding") for u in ast.get("uses", [])), (
                        "missing resolved local uses",
                        suffix,
                    )
                    if candidates and "extraction." in record["file"].lower():
                        writes = [u for u in ast.get("uses", []) if u.get("write") and u.get("binding")]
                        assert writes, ("missing mutation site", suffix)
                        mutation = next(s for s in statements if s["line"] == writes[0]["line"])
                        mutation_pages = collect(
                            client,
                            {
                                "target": t,
                                "intent": intent,
                                "options": {
                                    "file": t,
                                    "start_line": mutation["line"],
                                    "end_line": mutation["end"],
                                },
                            },
                        )
                        assert mutation_pages[0]["facts"]["external_mutations"]["total"] > 0, (
                            "missing external mutation",
                            suffix,
                        )
                        returns = [s for s in ast.get("controls", []) if "return" in s["kind"]]
                        assert returns, ("missing return boundary", suffix)
                        exit_statement = next(s for s in statements if s["line"] == returns[0]["line"])
                        exit_pages = collect(
                            client,
                            {
                                "target": t,
                                "intent": intent,
                                "options": {
                                    "file": t,
                                    "start_line": exit_statement["line"],
                                    "end_line": exit_statement["end"],
                                },
                            },
                        )
                        assert exit_pages[0]["facts"]["control_exits"]["total"] > 0
                if intent == "review_change":
                    handle = pages[0]["facts"]["baseline"]["handle"]
                    review = collect(
                        client,
                        {"target": file, "intent": intent, "options": {"baseline": handle}},
                    )
                    assert review[0]["facts"]["comparison_verified"]
                    assert not review[0]["evidence"]["total"]
                for page in pages:
                    for group in page["files"]:
                        if not group["snippets"]:
                            continue
                        text = (root / group["file"]).read_bytes().decode("utf-8").split("\n")
                        for snippet in group["snippets"]:
                            if not snippet["truncated"]:
                                assert snippet["text"] == "\n".join(
                                    text[snippet["start_line"] - 1 : snippet["end_line"]]
                                )
            if old:
                for tool in [
                    "references",
                    "callers",
                    "callees",
                    "implementations",
                    "neighbors",
                    "dependencies",
                    "blast_radius",
                    "inspect_change",
                ]:
                    args = {"target": target, "detail": "full"}
                    if tool != "inspect_change":
                        args["limit"] = 200
                    assert clean(client.call(tool, **args)) == clean(old.call(tool, **args)), (suffix, tool)
            checked.append({"extension": suffix, "intents": len(INTENTS), "fused_workflows": len(INTENTS)})
        bad = client.request(
            "tools/call",
            {
                "name": "inspect_change",
                "arguments": {
                    "target": next(iter(targets.values()))[0],
                    "intent": "rename",
                    "options": {"destination": "bad"},
                },
            },
        )
        assert bad["isError"]
        return {
            "languages": arch["languages"],
            "symbols": arch["symbols"],
            "edges": arch["edges"],
            "verified": checked,
        }
    finally:
        client.close()
        if old:
            old.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--baseline-config", type=Path)
    parser.add_argument(
        "--group",
        choices=["mixed", "flutter", "dart", "polyglot", "mobile"],
        default="mixed",
    )
    a = parser.parse_args()
    base = Path(__file__).resolve().parent.parent
    cfg = json.loads(a.config.read_text())
    cfg.setdefault("providers_path", str(base / "providers"))
    oldcfg = json.loads(a.baseline_config.read_text()) if a.baseline_config else cfg
    with tempfile.TemporaryDirectory(prefix="pcg intent all languages spaces ") as temp:
        root = Path(temp)
        fixtures = {
            "mixed": [
                base / "test/fixtures/dart_app",
                base / "test/fixtures/polyglot",
                base / "test/fixtures/semantic",
                base / "test/fixtures/mobile",
            ],
            "flutter": [base / "examples/flutter_fixture"],
            "dart": [base / "test/fixtures/dart_app"],
            "polyglot": [
                base / "test/fixtures/polyglot",
                base / "test/fixtures/semantic",
            ],
            "mobile": [base / "test/fixtures/mobile"],
        }[a.group]
        for fixture in fixtures:
            shutil.copytree(
                fixture,
                root / fixture.name,
                ignore=shutil.ignore_patterns(".polycodegraph", "build", "target"),
            )
        result = validate(a.binary, root, cfg, a.baseline, oldcfg)
        assert len(result["verified"]) == {"mixed": 10, "polyglot": 6, "mobile": 3, "dart": 1, "flutter": 1}[a.group], (
            result
        )
        print(json.dumps(result), flush=True)
