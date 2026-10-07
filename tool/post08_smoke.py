"""Native post-0.8 regressions and response volumes. No model calls or usage estimates."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import time
from pathlib import Path

from efficiency_client import LeanAdapter, Observer
from efficiency_collection import (
    compact,
    fuse_pages,
    normalized_inventory,
    select_collection,
)
from efficiency_workflow import workflow_surface
from smoke import Client


def pages(client, arguments):
    result = []
    for _ in range(64):
        page = client.call("inspect_change", **arguments)
        assert not page.get("restart_required"), page
        result.append(page)
        if page["next_cursor"] is None:
            return result
        arguments = dict(arguments, cursor=page["next_cursor"])
    raise AssertionError("page budget exhausted")


def measure(values):
    texts = [json.dumps(p, ensure_ascii=False, separators=(",", ":")) for p in values]
    return {
        "pages": len(values),
        "unicode_characters": sum(map(len, texts)),
        "utf8_bytes": sum(len(t.encode()) for t in texts),
        "records": sum(p.get("page", {}).get("records", len(p.get("evidence", {}).get("rows", []))) for p in values),
    }


def inventory(values, lean=False):
    sites = []
    for p in values:
        if lean:
            for r in p["records"]:
                for s in r["sites"]:
                    sites.append(
                        (r["source"], r["target"], r["relation"], r["file"], s[0], s[1], r["confidence"], r["phase"])
                    )
        else:
            for r in p["evidence"]["rows"]:
                sites.append(
                    (
                        p["symbols"]["rows"][r[1]][0],
                        p["symbols"]["rows"][r[2]][0],
                        r[3],
                        p["files"][r[4]]["file"],
                        r[5],
                        r[6],
                        r[7],
                        r[10],
                    )
                )
    return sorted(sites)


def run(binary, config):
    with tempfile.TemporaryDirectory(prefix="pcg post08 native ") as temp:
        root = Path(temp)
        text = (
            "function target(x: number) { return x; }\r\nfunction caller() {\r\n"
            + "".join(f"  target({i});\r\n" for i in range(100))
            + "}\r\n"
        )
        source = root / "sample.ts"
        source.write_bytes(text.encode())
        (root / "polycodegraph.json").write_text(json.dumps(dict(config, watch=False)))
        client = Client(binary.resolve(), root)
        try:
            schema = client.request("tools/list", {})
            spec = next(t for t in schema["tools"] if t["name"] == "inspect_change")
            experimental = "format" in spec["inputSchema"]["properties"]
            capture = client.call(
                "inspect_change",
                target="sample.ts",
                intent="review_change",
                options=dict(
                    capture_baseline=True, capture_mode="minimal", **({"strict_scope": True} if experimental else {})
                ),
            )
            before = client.call("references", target="target", limit=200)
            source.write_bytes(("// 🦀 moved, unchanged sites\r\n\r\n" + text).encode())
            arguments = {
                "target": "sample.ts",
                "intent": "review_change",
                "view": "locations",
                "options": dict(
                    baseline=capture["facts"]["baseline"]["handle"], **({"strict_scope": True} if experimental else {})
                ),
            }
            started = time.monotonic()
            values = pages(client, arguments)
            duration = (time.monotonic() - started) * 1000
            counts = {
                section: values[0]["sections"].get(section, {}).get("total", 0)
                for section in ["removed_relations", "added_relations", "source_changes"]
            }
            after = client.call("references", target="target", limit=200)
            assert before["total"] == after["total"] == 100
            result = {
                "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
                "model_runs": 0,
                "provider": "TypeScript compiler API",
                "measurement": "one compact JSON result representation; not provider tokens or model input",
                "relocation": {
                    "before_reference_sites": 100,
                    "after_reference_sites": 100,
                    "sections": counts,
                    "response": measure(values),
                    "query_ms": duration,
                },
                "schema_unicode_characters": len(json.dumps(schema, ensure_ascii=False)),
            }
            result["schema_sha256"] = hashlib.sha256(
                json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            if experimental:
                assert counts["removed_relations"] == counts["added_relations"] == 0, counts
                assert counts["source_changes"] == 1
                result["relocation"]["classification"] = values[0]["facts"]["relation_changes"]
                raw = client.request(
                    "tools/call",
                    {
                        "name": "inspect_change",
                        "arguments": {
                            "target": "typo/sample.ts",
                            "intent": "review_change",
                            "options": {"capture_baseline": True, "strict_scope": True},
                        },
                    },
                )
                assert raw["isError"]
                result["strict_scope"] = {"typo_rejected": True}
                tests = {}
                for intent in ["rename", "change_signature", "explain_symbol", "trace_flow"]:
                    args = {
                        "target": "target",
                        "intent": intent,
                        "view": "locations",
                        "budget": {"max_items": 200, "max_chars": 100000},
                    }
                    audit = pages(client, args)
                    lean = pages(client, dict(args, format="lean"))
                    assert inventory(audit) == inventory(lean, True), intent
                    tests[intent] = {
                        "audit": measure(audit),
                        "lean": measure(lean),
                        "same_sites_confidence_and_multiplicity": True,
                        "completion": lean[-1]["completion"],
                    }
                result["projection"] = tests
                lean_review = pages(client, dict(arguments, format="lean"))
                result["relocation"]["lean_response"] = measure(lean_review)
                observer = Observer()
                adapter = LeanAdapter(
                    lambda name, args: client.request("tools/call", {"name": name, "arguments": args}), observer
                )
                inserted = adapter.collect({"target": "target", "intent": "rename", "budget": {"max_items": 20}})
                assert inserted["complete"]
                assert "structuredContent" not in inserted["text"]
                assert "symbols" not in inserted["text"]
                result["adapter"] = {
                    "client": "efficiency_client.LeanAdapter/1, native stdio client; no model attached",
                    "complete": inserted["complete"],
                    "boundary": observer.summary(),
                    "automatic_pages": observer.pages,
                    "codex_client_insertion": "not_run",
                }
                corpus = {}
                for intent in ["rename", "change_signature", "explain_symbol", "trace_flow"]:
                    request = {
                        "target": "target",
                        "intent": intent,
                        "format": "lean",
                        "view": "edit_context",
                        "budget": {"max_items": 20},
                    }
                    values = pages(client, request)
                    selected = select_collection(values, {}, request)
                    assert normalized_inventory(values) == normalized_inventory(selected)
                    fused = fuse_pages(values)
                    corpus[intent] = {
                        "raw_pages": len(values),
                        "collection_1_chars": len(
                            compact({"format": "pcg-lean-collection-1", "pages": values, "collection": {}})
                        ),
                        "selected_chars": len(compact(selected)),
                        "selected_format": selected["format"],
                        "inventory_equal": True,
                        "raw_windows": sum(len(s["windows"]) for p in values for s in p["sources"]),
                        "merged_windows": sum(len(s["windows"]) for s in fused["sources"]),
                    }
                observer = Observer()
                adapter = LeanAdapter(
                    None, observer, collection_format="pcg-lean-collection-2", deadline_call=client.deadline_call
                )
                inserted = adapter.collect({"target": "target", "intent": "rename", "budget": {"max_items": 20}})
                assert inserted["complete"]
                result["fused_collection"] = {
                    "corpus": corpus,
                    "native_deadline": True,
                    "boundary": observer.summary(),
                    "provider_insertion": "unknown",
                    "model_runs": 0,
                }
                result["workflow_surfaces"] = {
                    profile: {
                        "tools": len(workflow_surface(schema["tools"], profile)["tools"]),
                        "schema_chars": len(compact(workflow_surface(schema["tools"], profile)["tools"])),
                        "instructions_chars": len(workflow_surface(schema["tools"], profile)["instructions"]),
                    }
                    for profile in ["local", "full", "agent", "rename", "change_signature", "review_change"]
                }
                target_id = client.call("search_symbol", query="target")["rows"][0][0]
                signature_capture = client.call(
                    "inspect_change",
                    target="sample.ts",
                    intent="review_change",
                    format="lean",
                    options={"capture_baseline": True, "capture_mode": "minimal"},
                )
                current = source.read_bytes().decode()
                source.write_bytes(current.replace("target(x: number)", "target(x: number, extra?: number)").encode())
                assert client.call("search_symbol", query="target")["rows"][0][0] == target_id
                changed = client.call(
                    "inspect_change",
                    target="sample.ts",
                    intent="review_change",
                    format="lean",
                    options={"baseline": signature_capture["facts"]["baseline"]["handle"]},
                )
                assert changed["facts"]["localization"][0]["kind"] == "contract_or_initializer"
                assert any("source_changes" in r["sections"] for r in changed["records"])
                result["signature_review"] = {
                    "same_symbol_id": True,
                    "contract_classification_retained": True,
                    "source_change_visible": True,
                    "classification": changed["facts"]["localization"][0]["kind"],
                }
                agent = Client(binary.resolve(), root, extra_args=("--tool-profile", "agent"))
                try:
                    initialized = agent.initialization
                    advertised = agent.request("tools/list", {})
                    names = [t["name"] for t in advertised["tools"]]
                    assert len(names) == 5 and "inspect_change" in names
                    advanced = agent.request(
                        "tools/call",
                        {
                            "name": "inspect_change",
                            "arguments": {"intent": "change_signature", "target": "target", "format": "lean"},
                            "_meta": {"progressToken": "post08"},
                        },
                    )
                    assert not advanced.get("isError") and advanced["structuredContent"]["format"] == "pcg-lean-1"
                    agent.i += 1
                    agent.send(
                        {
                            "jsonrpc": "2.0",
                            "id": agent.i,
                            "method": "tools/call",
                            "params": {"name": "unknown_post08_tool", "arguments": {}},
                        }
                    )
                    unknown = agent.q.get(timeout=10)
                    assert unknown.get("id") == agent.i and unknown["error"]["code"] == -32602
                    assert (
                        agent.call("inspect_change", intent="explain_symbol", target="target", format="lean")["format"]
                        == "pcg-lean-1"
                    )
                    result["agent_surface"] = {
                        "advertised_tools": names,
                        "advanced_intent_invoked": True,
                        "metadata_accepted": True,
                        "error_recovery": True,
                        "schema_sha256": hashlib.sha256(
                            json.dumps(advertised, sort_keys=True, separators=(",", ":")).encode()
                        ).hexdigest(),
                        "schema_unicode_characters": len(json.dumps(advertised, ensure_ascii=False)),
                        "initialization_instructions_sha256": hashlib.sha256(
                            initialized.get("instructions", "").encode()
                        ).hexdigest(),
                        "native_reconnect": True,
                        "codex_tool_registration": "not_run",
                    }
                finally:
                    agent.close()
            return result
        finally:
            client.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ["binary", "config", "output"]:
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    a.output.write_text(json.dumps(run(a.binary, json.loads(a.config.read_text())), indent=2) + "\n")
