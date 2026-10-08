"""Zero-AI native policy/retention checks on controlled source, never executed."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import tempfile
import time
from pathlib import Path

from efficiency_binding import AsyncLeanBinding
from efficiency_client import Observer
from efficiency_collection import (
    compact,
    normalized_inventory,
    select_collection,
    source_windows,
)
from efficiency_gate_corpus import build_tasks
from efficiency_retention import RetainedContext
from efficiency_workflow import workflow_surface
from smoke import Client


def collect(client: Client, arguments: dict) -> list[dict]:
    pages = []
    for _ in range(64):
        page = client.call("inspect_change", **arguments)
        assert not page.get("restart_required"), page
        pages.append(page)
        if not page["next_cursor"]:
            return pages
        arguments = dict(arguments, cursor=page["next_cursor"])
    raise AssertionError("native page budget exceeded")


async def retention_probe(client: Client, catalog: list[dict], target: str) -> dict:
    retention = RetainedContext()
    observer = Observer()

    async def call(name, args):
        # Trusted smoke client only; production uses the async NativeTransport.
        return await asyncio.to_thread(client.request, "tools/call", {"name": name, "arguments": args})

    binding = AsyncLeanBinding(call, observer, workflow_surface(catalog, "explain_symbol"), retention=retention)
    args = {"target": target, "intent": "explain_symbol", "format": "lean", "view": "full_evidence"}
    inserted = []
    first = await binding.collect(args, inserted.append)
    first_value = json.loads(first["text"])
    retention.acknowledge(retention.epoch, first_value["retention"]["offered_windows"])
    repeated = await binding.collect(args, inserted.append)
    repeated_value = json.loads(repeated["text"])
    assert normalized_inventory(first_value) == normalized_inventory(repeated_value)
    assert repeated_value["retention"]["referenced_windows"] > 0
    binding.compaction()
    rehydrated = await binding.collect(args, inserted.append)
    rehydrated_value = json.loads(rehydrated["text"])
    assert normalized_inventory(first_value) == normalized_inventory(rehydrated_value)
    assert all("text" in w for w in source_windows(rehydrated_value))
    return {
        "first_insertion_chars": len(first["text"]),
        "repeated_insertion_chars": len(repeated["text"]),
        "rehydrated_insertion_chars": len(rehydrated["text"]),
        "all_three_insertion_chars": sum(map(len, inserted)),
        "inventory_equal": True,
        "referenced_windows": repeated_value["retention"]["referenced_windows"],
        "compaction_rehydrated": True,
        "compiler_or_tests_executed": False,
    }


def run(binary: Path, config: dict) -> dict:
    results = []
    with tempfile.TemporaryDirectory(prefix="pcg dev2 policy fixtures ") as temp:
        base = Path(temp)
        for task in build_tasks():
            if task.profile == "local":
                continue
            root = base / task.name
            root.mkdir()
            for file, text in task.sources.items():
                path = root / file
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            (root / "polycodegraph.json").write_text(json.dumps(dict(config, watch=False, include=["src/**/*.ts"])))
            client = Client(binary.resolve(), root)
            try:
                catalog = client.request("tools/list", {})["tools"]
                surface = workflow_surface(catalog, task.profile)
                args = {"target": task.target, "intent": task.profile, "format": "lean"}
                variants = {}
                reference = None
                for label, extra in (
                    ("legacy_lean", {}),
                    ("full_evidence", {"view": "full_evidence"}),
                    ("intent_policy", {"source_policy": "intent"}),
                    ("source_budget_0", {"source_policy": "intent", "budget": {"max_source_chars": 0}}),
                ):
                    arguments = dict(args, **extra)
                    started = time.perf_counter()
                    pages = collect(client, arguments)
                    milliseconds = (time.perf_counter() - started) * 1000
                    inventory = normalized_inventory(pages)
                    if reference is None:
                        reference = inventory
                    assert inventory == reference, (task.name, label, "inventory changed")
                    projected = select_collection(pages, {"complete": True}, arguments)
                    variants[label] = {
                        "pages": len(pages),
                        "native_result_chars": sum(len(compact(p)) for p in pages),
                        "selected_collection_chars": len(compact(projected)),
                        "source_text_chars": sum(len(w.get("text", "")) for w in source_windows(projected)),
                        "inventory_sites": sum(inventory.values()),
                        "inventory_equal": True,
                        "observed_ms": milliseconds,
                    }
                results.append(
                    {
                        "task": task.name,
                        "profile": task.profile,
                        "variants": variants,
                        "schema_chars": len(compact(surface["tools"])),
                        "guide_chars": len(surface["instructions"]),
                    }
                )
            finally:
                client.close()
        root = base / "retention"
        root.mkdir()
        (root / "source.ts").write_text(
            "export function retained(x: number) {\n"
            + "".join(f"  x += {i}; // retained statement {i}\n" for i in range(60))
            + "  return x;\n}\n"
        )
        (root / "polycodegraph.json").write_text(json.dumps(dict(config, watch=False, include=["*.ts"])))
        client = Client(binary.resolve(), root)
        try:
            catalog = client.request("tools/list", {})["tools"]
            retention = asyncio.run(retention_probe(client, catalog, "retained"))
        finally:
            client.close()
    return {
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "model_runs": 0,
        "measurement": "Unicode characters of actual native results and selected text; not model tokens",
        "limitations": "Known controlled TypeScript fixtures, shared warmed OS cache; current review context, not a new AI campaign or runtime correctness proof",
        "source_policy_cases": results,
        "retention": retention,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.binary, json.loads(args.config.read_text()))
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {"policy_cases": len(result["source_policy_cases"]), "retention": result["retention"], "model_runs": 0}
        )
    )
