"""Native static-profile/collector MCP preflight; zero model calls or inferred usage."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

from efficiency_collection import normalized_inventory, source_windows
from smoke import Client


def surface_metrics(tools: list[dict], initialization: dict) -> dict:
    """Measure only the actually offered MCP catalog/guide, never model tokens."""
    schema = json.dumps(tools, ensure_ascii=False, separators=(",", ":"))
    guide = initialization.get("instructions", "")
    return {
        "schema_chars": len(schema),
        "schema_bytes": len(schema.encode()),
        "schema_sha256": hashlib.sha256(schema.encode()).hexdigest(),
        "guide_chars": len(guide),
        "guide_sha256": hashlib.sha256(guide.encode()).hexdigest(),
    }


def source_inventory(pages: list[dict]) -> dict:
    """Compare exact visible lines and provenance before/after complete-window merging."""
    inventory = {}
    for page in pages:
        for source in page.get("sources", []):
            for window in source["windows"]:
                assert not window.get("truncated"), "fixture must have complete source windows"
                for offset, text in enumerate(window["text"].split("\n")):
                    key = (
                        source["file"],
                        source["source_hash"],
                        source.get("phase", window.get("phase", "current")),
                        window.get("view"),
                        window["start_line"] + offset,
                    )
                    assert key not in inventory or inventory[key] == text
                    inventory[key] = text
    return inventory


def run(binary: Path, config: Path | None, bridge: Path, output: Path | None = None, adjacent=False) -> dict:
    """Exercise the shipped stdio entrypoint against the native TypeScript compiler fixture."""
    with tempfile.TemporaryDirectory(prefix="pcg workflow spaces ") as temp:
        root = Path(temp)
        (root / "sample.ts").write_text(
            "export function target(x: number) { return x; }\nexport function caller() {\n"
            + "target(1); target(2);\n" * 100
            + "}\n",
            encoding="utf-8",
        )
        raw = Client(binary.resolve(), root, extra_args=("--config", str(config.resolve())) if config else ())

        def client(profile: str, *extra: str) -> Client:
            command = [sys.executable, "-I", str(bridge.resolve()), "--root", str(root), "--profile", profile]
            # -I does not add script directory to sys.path; launch via a trusted
            # loader that adds only the shipped clients directory, then run main.
            command = [
                sys.executable,
                "-I",
                "-c",
                (
                    "import sys,runpy; sys.path.insert(0,sys.argv[1]); "
                    "sys.argv=sys.argv[2:]; runpy.run_path(sys.argv[0],run_name='__main__')"
                ),
                str(bridge.resolve().parent),
                *command[3:],
            ]
            command.insert(5, str(bridge.resolve()))
            if not adjacent:
                command.extend(["--binary", str(binary.resolve())])
            if config:
                command.extend(["--config", str(config.resolve())])
            command.extend(extra)
            return Client(binary, root, command=command)

        result = {
            "model_runs": 0,
            "provider_usage": None,
            "provider_prompt_insertion": None,
            "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
            "bridge_sha256": hashlib.sha256(bridge.read_bytes()).hexdigest(),
            "python_version": sys.version.split()[0],
            "client_modules_sha256": {
                name: hashlib.sha256((bridge.parent / name).read_bytes()).hexdigest()
                for name in (
                    "efficiency_client.py",
                    "efficiency_collection.py",
                    "efficiency_ledger.py",
                    "efficiency_workflow.py",
                    "efficiency_binding.py",
                    "efficiency_transport.py",
                    "efficiency_mcp.py",
                )
            },
        }
        try:
            catalog = raw.request("tools/list", {})["tools"]
            local = client("local", "--binary", str(root / "does-not-exist"))
            try:
                assert local.request("tools/list", {})["tools"] == []
                assert not local.initialization.get("instructions")
                result["local"] = {"tools": 0, "instructions": 0, "native_binary_required": False}
            finally:
                local.close()
            for profile, count in (("full", len(catalog)), ("agent", 5)):
                ordinary = client(profile)
                try:
                    tools = ordinary.request("tools/list", {})["tools"]
                    names = {t["name"] for t in tools}
                    assert len(names) == count
                    status = ordinary.request("tools/call", {"name": "status", "arguments": {}})
                    assert "structuredContent" in status
                    assert ordinary.initialization["instructions"] == raw.initialization["instructions"]
                    result[profile] = {
                        "tools": count,
                        "direct_result_preserved": True,
                        "original_guide": True,
                        **surface_metrics(tools, ordinary.initialization),
                    }
                finally:
                    ordinary.close()
            receipt = root / "private-receipt.json"
            focused = client("rename", "--discovery", "--max-pages", "32", "--telemetry", str(receipt))
            try:
                tools = focused.request("tools/list", {"_meta": {"progressToken": "probe"}})["tools"]
                assert [t["name"] for t in tools] == ["search_symbol", "inspect_change"]
                search = focused.request("tools/call", {"name": "search_symbol", "arguments": {"query": "target"}})
                target = search["structuredContent"]["rows"][0][0]
                arguments = {
                    "target": target,
                    "intent": "rename",
                    "format": "lean",
                    "view": "edit_context",
                    "budget": {"max_items": 20},
                }
                values = []
                next_args = dict(arguments)
                while True:
                    page = raw.call("inspect_change", **next_args)
                    values.append(page)
                    if not page["next_cursor"]:
                        break
                    next_args["cursor"] = page["next_cursor"]
                transformed = focused.request(
                    "tools/call",
                    {"name": "inspect_change", "arguments": arguments, "_meta": {"progressToken": "collect"}},
                )
                assert not transformed["isError"] and "structuredContent" not in transformed
                assert len(transformed["content"]) == 1
                selected = json.loads(transformed["content"][0]["text"])
                assert selected["collection"]["complete"], selected["collection"]
                assert normalized_inventory(values) == normalized_inventory(selected)
                selected_pages = selected["pages"] if selected["format"] == "pcg-lean-collection-1" else [selected]
                assert source_inventory(values) == source_inventory(selected_pages)
                result["rename"] = {
                    **surface_metrics(tools, focused.initialization),
                    "advertised_tools": len(tools),
                    "raw_pages": len(values),
                    "selected_format": selected["format"],
                    "one_text": True,
                    "inventory_equal": True,
                    "source_equal": True,
                    "selected_source_windows": len(source_windows(selected)),
                }
                invalid = focused.request(
                    "tools/call",
                    {"name": "inspect_change", "arguments": {**arguments, "options": {"destination": "other.ts"}}},
                )
                assert invalid["isError"]
                # Every schema projection is from the native catalog; strictness
                # and actual collection are exercised through the bridge here.
                result["rename"]["foreign_options_rejected"] = True
            finally:
                focused.close()
            telemetry = json.loads(receipt.read_text())
            assert telemetry["summary"]["observer"]["injected_chars"] == 0
            assert telemetry["summary"]["provider_prompt_insertion"] is None
            assert not any(e["kind"] == "insertion" for e in telemetry["events"])
            assert telemetry["summary"]["observer"]["errors"] == 1
            result["telemetry"] = {
                "private_hashed_receipt": True,
                "mcp_calls": telemetry["summary"]["observer"]["mcp_calls"],
                "prompt_insertion_claimed": False,
                "rejected_workflow_error_counted": True,
            }
            for intent, options in (("move_symbol", {"destination": "proposed/sample.ts"}), ("trace_flow", {})):
                advanced = client(intent, "--max-pages", "32")
                try:
                    tools = advanced.request("tools/list", {})["tools"]
                    assert len(tools) == 1 and tools[0]["name"] == "inspect_change"
                    response = advanced.request(
                        "tools/call",
                        {
                            "name": "inspect_change",
                            "arguments": {
                                "target": target,
                                "intent": intent,
                                "format": "lean",
                                "options": options,
                                "view": "locations",
                            },
                        },
                    )
                    assert not response["isError"], response
                    selected = json.loads(response["content"][0]["text"])
                    assert selected["collection"]["complete"]
                    result[intent] = {
                        **surface_metrics(tools, advanced.initialization),
                        "canonical_tool": True,
                        "typed_workflow": True,
                        "complete": True,
                        "selected_format": selected["format"],
                    }
                finally:
                    advanced.close()
            resume = client("rename", "--max-pages", "1")
            try:
                limited = resume.request("tools/call", {"name": "inspect_change", "arguments": arguments})
                value = json.loads(limited["content"][0]["text"])
                assert not value["collection"]["complete"] and value["collection"]["limit"] == "collector_page_budget"
                cursor = (
                    value["pages"][-1]["next_cursor"]
                    if value["format"] == "pcg-lean-collection-1"
                    else value["next_cursor"]
                )
                continuation = resume.request(
                    "tools/call", {"name": "inspect_change", "arguments": {**arguments, "cursor": cursor}}
                )
                page = json.loads(continuation["content"][0]["text"])
                assert page["format"] == "pcg-lean-1" and page["page"]["offset"] == 20
                assert normalized_inventory([page]) == normalized_inventory([values[1]])
                result["continuation"] = {
                    "limit_visible": True,
                    "canonical_cursor_recovery": True,
                    "page_offset": page["page"]["offset"],
                    "inventory_equal": True,
                }
            finally:
                resume.close()
            review = client("review_change")
            try:
                args = {
                    "target": "sample.ts",
                    "intent": "review_change",
                    "format": "lean",
                    "view": "locations",
                    "options": {"capture_baseline": True},
                }
                captured = review.request("tools/call", {"name": "inspect_change", "arguments": args})
                assert not captured["isError"]
                value = json.loads(captured["content"][0]["text"])
                facts = value["pages"][0]["facts"] if value["format"] == "pcg-lean-collection-1" else value["facts"]
                handle = facts["baseline"]["handle"]
                source = root / "sample.ts"
                source.write_text("// relocated\n" + source.read_text(), encoding="utf-8")
                args["options"] = {"baseline": handle}
                response = review.request("tools/call", {"name": "inspect_change", "arguments": args})
                assert not response["isError"]
                value = json.loads(response["content"][0]["text"])
                assert value["collection"]["complete"]
                assert normalized_inventory(value)
                result["review_change"] = {
                    "baseline_reused_same_session": True,
                    "source_edit_observed": True,
                    "complete": True,
                    "selected_format": value["format"],
                }
            finally:
                review.close()
        finally:
            raw.close()
        if output:
            output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--bridge", type=Path, default=Path(__file__).with_name("efficiency_mcp.py"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.binary, args.config, args.bridge, args.output)))
