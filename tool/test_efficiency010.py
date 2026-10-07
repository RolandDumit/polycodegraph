"""Deterministic 0.10 gates; synthetic receipts are never provider measurements."""

from __future__ import annotations

import asyncio
import copy
import json
import queue
import tempfile
import time
import unittest
from pathlib import Path

from efficiency_benchmark import evaluate, validate_manifest
from efficiency_binding import AsyncLeanBinding
from efficiency_client import Observer
from efficiency_collection import (
    CollectionConflict,
    compact,
    expand_records,
    fuse_pages,
    intern_records,
    merge_windows,
    normalized_inventory,
    select_collection,
    source_windows,
)
from efficiency_comparison import cells, normalize_attempt
from efficiency_ledger import ContextLedger
from efficiency_usage import requests, verify
from efficiency_workflow import workflow_arguments, workflow_surface
from smoke import Client
from test_comparison import manifest, record
from test_token_usage import event as cumulative_event

CATALOG = json.loads((Path(__file__).resolve().parent.parent / "crates/core/src/tools.json").read_text())


def page(offset=0, remaining=0, sites=None, text="a\nb", start=1, phase="current"):
    sites = sites if sites is not None else [[4, offset + 10, f"handle-{offset}"]]
    return {
        "format": "pcg-lean-1",
        "intent": "rename",
        "target": {"id": "path.ts::target#function"},
        "snapshot": {"root_id": "root", "generation": "g", "health_fingerprint": "h", "environment_fingerprint": "e"},
        "source_role": "untrusted_code",
        "freshness": {"mode": "hash_scan"},
        "completion": {
            "required_inventory": {
                "state": "incomplete" if remaining else "complete",
                "known_count": 2,
                "remaining_known": remaining,
                "provider_incomplete": False,
                "exploration_incomplete": False,
            },
            "optional_context": "not_requested",
            "verification": {"compiler": "not_run", "tests": "not_run"},
        },
        "page": {"offset": offset, "records": len(sites)},
        "records": [
            {
                "source": "long/path.ts::caller#function",
                "target": "long/path.ts::target#function",
                "file": "long/path.ts",
                "relation": "calls",
                "confidence": "resolved",
                "required": True,
                "phase": phase,
                "reason": "semantic caller",
                "sections": ["static_uses"],
                "sites": sites,
            }
        ],
        "sources": [
            {
                "file": "long/path.ts",
                "source_hash": "sourcehash",
                "windows": [
                    {
                        "start_line": start,
                        "end_line": start + len(text.split("\n")) - 1,
                        "text": text,
                        "truncated": False,
                    }
                ],
            }
        ],
        "details": {f"handle-{offset}": {"provenance": "compiler", "original_offset": offset}},
        "limits": ["static_only"],
        "limit_causes": [],
        "source_windows_incomplete": False,
        "next_cursor": "c" * 64 if remaining else None,
    }


def wire(value):
    return {"structuredContent": value, "content": [{"type": "text", "text": compact(value)}], "isError": False}


class Collection(unittest.TestCase):
    def test_full_inventory_provenance_multiplicity_and_details_survive(self):
        first = page(remaining=2, sites=[[4, 10, "detail"], [4, 13], [4, 13]])
        second = page(offset=3, sites=[[4, 16], [4, 10]], text="b\nc", start=2)
        for p in (first, second):
            p["completion"]["required_inventory"]["known_count"] = 5
        original = copy.deepcopy([first, second])
        fused = fuse_pages(original)
        interned = intern_records(fused)
        self.assertEqual(normalized_inventory(original), normalized_inventory(interned))
        self.assertEqual(expand_records(interned), fused["records"])
        self.assertEqual(len(fused["records"][0]["sites"]), 5)
        self.assertEqual(fused["sources"][0]["windows"][0]["text"], "a\nb\nc")

        def source_map(values):
            return {
                (s["file"], s["source_hash"], w["start_line"] + i): line
                for p in values
                for s in p["sources"]
                for w in s["windows"]
                for i, line in enumerate(w["text"].split("\n"))
            }

        self.assertEqual(source_map(original), source_map([fused]))
        self.assertEqual(fused["details"], {**first["details"], **second["details"]})
        self.assertEqual(original, [first, second])

    def test_phase_confidence_sections_homonyms_and_handle_conflicts(self):
        first, second = page(remaining=1), page(offset=1, phase="before")
        second["records"][0]["confidence"] = "conditional"
        second["records"][0]["sections"] = ["before_uses"]
        second["records"][0]["target"] = "other/path.ts::target#function"
        fused = fuse_pages([first, second])
        self.assertEqual(len(fused["records"]), 2)
        self.assertEqual(normalized_inventory([first, second]), normalized_inventory(fused))
        second["details"] = copy.deepcopy(first["details"])
        second["details"]["handle-0"]["provenance"] = "different"
        with self.assertRaisesRegex(CollectionConflict, "detail_handle_conflict"):
            fuse_pages([first, second])

    def test_overlap_bytes_unicode_crlf_truncation_and_metadata(self):
        windows = [
            {"start_line": 1, "end_line": 2, "text": "α\r\n🦀\r", "truncated": False},
            {"start_line": 2, "end_line": 3, "text": "🦀\r\nγ", "truncated": False},
            {"start_line": 4, "end_line": 4, "text": "tail", "truncated": False},
        ]
        merged = merge_windows(windows)
        self.assertEqual(merged[0]["text"], "α\r\n🦀\r\nγ\ntail")
        windows[1]["text"] = "wrong\r\nγ"
        windows[1]["precision"] = "other precision"
        with self.assertRaisesRegex(CollectionConflict, "overlap_conflict"):
            merge_windows(windows)
        windows[1]["truncated"] = True
        with self.assertRaisesRegex(CollectionConflict, "overlap_conflict"):
            merge_windows(windows)
        windows[1]["text"] = "🦀\r\nγ"
        self.assertEqual(len(merge_windows(windows)), 3)
        windows[1]["truncated"] = False
        windows[1]["phase"] = "before"
        self.assertEqual(len(merge_windows(windows)), 3)

    def test_snapshot_source_hash_and_missing_page_are_rejected(self):
        for field in ("root_id", "health_fingerprint", "generation", "environment_fingerprint"):
            first, second = page(remaining=1), page(offset=1)
            second["snapshot"][field] = "changed"
            with self.assertRaisesRegex(CollectionConflict, "snapshot_changed"):
                fuse_pages([first, second])
        first, second = page(remaining=1), page(offset=1)
        second["sources"][0]["source_hash"] = "newhash"
        with self.assertRaisesRegex(CollectionConflict, "source_hash_changed"):
            fuse_pages([first, second])
        second = page(offset=5)
        with self.assertRaisesRegex(CollectionConflict, "discontinuity"):
            fuse_pages([first, second])

    def test_limits_optional_verification_and_negative_size_case(self):
        first, second = page(remaining=1), page(offset=1)
        first["source_windows_incomplete"] = True
        first["limit_causes"] = ["source_limit"]
        first["completion"]["optional_context"] = "limited"
        fused = fuse_pages([first, second])
        self.assertTrue(fused["source_windows_incomplete"])
        self.assertIn("source_limit", fused["limit_causes"])
        self.assertEqual(fused["page_states"][0]["completion"]["optional_context"], "limited")
        self.assertEqual(fused["completion"]["verification"]["compiler"], "not_run")
        small = page()
        small["completion"]["required_inventory"]["known_count"] = 1
        legacy = {"format": "pcg-lean-collection-1", "pages": [small], "collection": {}}
        selected = select_collection([small], {}, {"target": "target", "intent": "rename"})
        self.assertLessEqual(len(compact(selected)), len(compact(legacy)))
        self.assertEqual(normalized_inventory([small]), normalized_inventory(selected))


class Telemetry(unittest.TestCase):
    def test_partial_overlap_external_reads_compaction_and_budget(self):
        ledger = ContextLedger()
        ledger.range("root", "hash", 1, 2, "abc\ndef")
        ledger.external("root", "hash", 2, 3, "def\nghi")
        self.assertEqual((ledger.new_chars, ledger.repeated_chars), (11, 3))
        ledger.compaction()
        ledger.range("root", "hash", 1, 3, "abc\ndef\nghi")
        self.assertEqual(ledger.rehydrated_chars, 11)
        ledger.range("other", "hash", 1, 1, "abc")
        self.assertEqual(ledger.new_chars, 14)
        bounded = ContextLedger(max_entries=2)
        bounded.range("root", "hash", 1, 2, "a\nb")
        self.assertEqual(len(bounded.seen), 2)
        self.assertFalse(bounded.complete)
        self.assertEqual(bounded.unidentified_chars, 1)
        observer = Observer()
        value = page()
        value["sources"][0]["windows"] = [
            {"start_line": 1, "end_line": 1, "text": "abc", "phase": phase} for phase in ("before", "current")
        ]
        observer.inject(wire(value), "structured")
        self.assertEqual(observer.summary()["new_context_chars"], 6)
        self.assertEqual(observer.summary()["repeated_context_chars"], 0)
        self.assertEqual([w["phase"] for w in source_windows(value)], ["before", "current"])

    def test_request_correlation_has_no_raw_source_and_unknown_is_explicit(self):
        observer = Observer()
        observer.observe_wire(wire(page()), "inspect_change", {"target": "private-code"})
        observer.inject({}, "transformed", "secret source", prompt_windows=[])
        observer.request_model("request1", "[]", "")
        observer.request_model("request2")
        self.assertEqual(observer.events[1]["tool_result_ids"], [observer.events[0]["id"]])
        self.assertEqual(observer.events[2]["insertion_ids"], [observer.events[1]["id"]])
        self.assertIsNone(observer.events[3]["schema_sha256"])
        self.assertNotIn("secret source", compact(observer.events))
        self.assertNotIn("private-code", compact(observer.events))

    def test_new_receipts_unknown_creation_failed_attempts_and_cumulative(self):
        event = {
            "request_id": "r",
            "provider": "openai",
            "model": "fixed",
            "effort": "high",
            "usage": {
                "input_tokens": 100,
                "cached_input_tokens": 80,
                "output_tokens": 10,
                "reasoning_output_tokens": 5,
            },
        }
        measured = requests([event, event], "usage-v2")
        self.assertEqual(measured["totals"]["total_tokens"], 110)
        self.assertEqual(measured["totals"]["uncached_input_tokens"], 20)
        self.assertIsNone(measured["totals"]["cache_creation_input_tokens"])
        self.assertEqual(verify(measured)["totals"], measured["totals"])
        self.assertEqual(measured["duplicate_events"], 1)
        for state in (False, None):
            with self.assertRaisesRegex(ValueError, "partial/unknown"):
                normalize_attempt({"usage_events": [event], "usage_complete": state}, "usage-v2")
        cumulative = [
            {"type": "turn_context", "payload": {"model": "fixed", "effort": "high"}},
            cumulative_event(1),
            cumulative_event(1),
            cumulative_event(2, 1),
            cumulative_event(1),
        ]
        normalized = normalize_attempt({"codex_usage_metadata": cumulative, "usage_complete": True}, "usage-v2")
        self.assertEqual(normalized["model_requests"], 3)
        self.assertEqual(normalized["counter_resets"], 1)
        with tempfile.TemporaryDirectory() as temp:
            m = manifest(Path(temp), n=2)
            m.update(protocol_revision="comparison-v2", primary_metric="total_tokens_per_accepted_task")
            self.assertEqual(validate_manifest(m, Path(temp)), [])
            runs = [record(m, cell) for cell in cells(m)]
            failed = copy.deepcopy(runs[0])
            failed["success"] = False
            runs[0]["attempt"] = 2
            result = evaluate(m, [failed, *runs])
            a = result["aggregates"][failed["condition"]]
            self.assertEqual(a["primary_per_accepted_task"], a["total_tokens_per_accepted_task"])
            self.assertGreater(a["primary_per_accepted_task"], a["uncached_input_per_accepted_task"])
            failed["usage"] = None
            result = evaluate(m, [failed, *runs])
            self.assertIsNone(result["aggregates"][failed["condition"]]["primary_per_accepted_task"])
            del runs[0]["client"]["graph_mcp_calls"]
            result = evaluate(m, [failed, *runs])
            self.assertIsNone(result["aggregates"][runs[0]["condition"]]["graph_used_cells"])

    def test_native_deadline_and_eof_require_reconnect(self):
        client = object.__new__(Client)
        client.i = 0
        client.abandoned = False
        client.q = queue.Queue()
        sent = []
        client.send = sent.append
        with self.assertRaises(TimeoutError):
            client.request("tools/call", {}, deadline=time.monotonic() - 1)
        self.assertEqual(sent[-1]["method"], "notifications/cancelled")
        with self.assertRaises(ConnectionError):
            client.request("tools/call", {})
        client.abandoned = False
        client.q.put({"process_ended": True})
        with self.assertRaisesRegex(ConnectionError, "EOF"):
            client.request("tools/call", {})
        self.assertTrue(client.abandoned)

    def test_v2_revision_survives_cumulative_and_inclusive_streams(self):
        cumulative = [
            {"type": "turn_context", "payload": {"model": "fixed", "effort": "high"}},
            cumulative_event(1),
        ]
        observed = {"codex_usage_metadata": cumulative, "usage_complete": True}
        v2 = normalize_attempt(observed, "usage-v2")
        self.assertEqual(v2["totals"]["cache_creation_input_tokens"], 0)
        self.assertEqual(v2["usage_revision"], "usage-v2")
        self.assertEqual(verify(v2)["totals"], v2["totals"])
        self.assertEqual(normalize_attempt(observed)["totals"]["cache_creation_input_tokens"], 0)
        event = {
            "request_id": "r",
            "provider": "openai",
            "model": "fixed",
            "effort": "high",
            "usage": {"input_tokens": 100, "cached_input_tokens": 80, "output_tokens": 10},
        }
        parent = {"id": "parent", "scope": "inclusive_attempt", "usage_events": [event]}
        observed = {"usage_streams": [parent], "usage_complete": True}
        parent_v2 = normalize_attempt(observed, "usage-v2")
        self.assertIsNone(parent_v2["totals"]["cache_creation_input_tokens"])
        self.assertEqual(verify(parent_v2)["totals"], parent_v2["totals"])
        parent["usage_complete"] = False
        with self.assertRaisesRegex(ValueError, "partial/unknown"):
            normalize_attempt(observed, "usage-v2")
        observed["usage_streams"] = [{"id": "child", "scope": "disjoint_requests", "usage_events": [event]}]
        self.assertIsNone(normalize_attempt(observed, "usage-v2")["totals"]["cache_creation_input_tokens"])
        observed["usage_streams"][0]["usage_complete"] = None
        with self.assertRaisesRegex(ValueError, "partial/unknown"):
            normalize_attempt(observed, "usage-v2")


class Workflows(unittest.TestCase):
    def test_local_has_no_pcg_surface_and_all_intents_use_canonical_options(self):
        self.assertEqual(workflow_surface(CATALOG, "local"), {"profile": "local", "tools": [], "instructions": ""})
        spec = next(tool for tool in CATALOG if tool["name"] == "inspect_change")
        for rule in spec["inputSchema"]["allOf"]:
            intent = rule["if"]["properties"]["intent"]["const"]
            surface = workflow_surface(CATALOG, intent)
            projected = surface["tools"][0]["inputSchema"]
            self.assertEqual(projected["properties"]["options"], rule["then"]["properties"]["options"])
            self.assertNotIn("allOf", projected)
            self.assertNotIn("cursor", projected["properties"])
            self.assertLess(
                len(compact(surface["tools"])), len(compact(workflow_surface(CATALOG, "agent")["tools"])) / 2
            )
        self.assertEqual(workflow_surface(CATALOG, "full")["tools"], CATALOG)
        surface = workflow_surface(CATALOG, "rename")
        with self.assertRaises(ValueError):
            workflow_arguments(
                surface, {"target": "t", "intent": "rename", "format": "lean", "options": {"destination": "x"}}
            )
        with self.assertRaises(ValueError):
            workflow_arguments(surface, {"target": "t", "intent": "trace_flow", "format": "lean"})


class Binding(unittest.IsolatedAsyncioTestCase):
    async def test_single_actual_insertion_collection_and_model_request(self):
        values = [page(remaining=1), page(offset=1, text="b\nc", start=2)]
        observer = Observer()
        calls = []
        insertions = []

        async def call(name, arguments):
            calls.append(arguments)
            return wire(values[len(calls) - 1])

        surface = workflow_surface(CATALOG, "rename")
        binding = AsyncLeanBinding(call, observer, surface)
        result = await binding.collect({"target": "t", "intent": "rename", "format": "lean"}, insertions.append)
        self.assertTrue(result["complete"])
        self.assertEqual(calls[1]["cursor"], "c" * 64)
        self.assertEqual(insertions, [result["text"]])
        self.assertEqual(normalized_inventory(values), normalized_inventory(json.loads(result["text"])))
        observer.request_model("r", compact(surface["tools"]), surface["instructions"])
        self.assertEqual(observer.events[-1]["insertion_ids"], [observer.events[-2]["id"]])
        self.assertEqual(observer.summary()["injected_chars"], len(result["text"]))
        self.assertEqual(len(source_windows(json.loads(result["text"]))), 1)

    async def test_timeout_cancels_active_rpc_and_reports_incomplete(self):
        cancelled = asyncio.Event()
        observer = Observer()
        inserted = []

        async def call(name, arguments):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        binding = AsyncLeanBinding(call, observer, workflow_surface(CATALOG, "rename"), max_seconds=1)
        started = time.monotonic()
        result = await binding.collect({"target": "t", "intent": "rename", "format": "lean"}, inserted.append)
        await asyncio.wait_for(cancelled.wait(), 0.5)
        self.assertLess(time.monotonic() - started, 1.5)
        self.assertFalse(result["complete"])
        self.assertEqual(result["reason"], "collector_time_budget")
        self.assertEqual(observer.summary()["new_context_chars"], 0)
        self.assertEqual(observer.summary()["mcp_calls"], 1)
        self.assertEqual(observer.summary()["errors"], 1)

    async def test_cancellation_and_failed_insertion_never_record_prompt_content(self):
        started = asyncio.Event()
        cancelled = asyncio.Event()
        observer = Observer()
        inserted = []

        async def call(name, arguments):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        binding = AsyncLeanBinding(call, observer, workflow_surface(CATALOG, "rename"))
        task = asyncio.create_task(
            binding.collect({"target": "t", "intent": "rename", "format": "lean"}, inserted.append)
        )
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        await asyncio.wait_for(cancelled.wait(), 0.5)
        self.assertEqual(inserted, [])
        self.assertEqual(observer.summary()["injected_chars"], 0)

        self.assertFalse(binding.active)

        async def fast(name, arguments):
            value = page()
            value["completion"]["required_inventory"]["known_count"] = 1
            return wire(value)

        def broken_insert(text):
            raise RuntimeError("insertion failed")

        binding = AsyncLeanBinding(fast, observer, workflow_surface(CATALOG, "rename"))
        with self.assertRaisesRegex(RuntimeError, "insertion failed"):
            await binding.collect({"target": "t", "intent": "rename", "format": "lean"}, broken_insert)
        self.assertEqual(observer.summary()["injected_chars"], 0)
        self.assertFalse(observer.summary()["insertion_boundary_complete"])
        self.assertFalse(observer.summary()["context_identity_complete"])
        self.assertFalse(observer.summary()["boundary_accounting_complete"])

    async def test_async_insertion_is_rejected_before_rpc(self):
        called = False

        async def call(name, arguments):
            nonlocal called
            called = True
            return wire(page())

        async def insert(text):
            self.fail("async insertion must not run")

        binding = AsyncLeanBinding(call, Observer(), workflow_surface(CATALOG, "rename"))
        with self.assertRaisesRegex(ValueError, "synchronous"):
            await binding.collect({"target": "t", "intent": "rename", "format": "lean"}, insert)
        self.assertFalse(called)

    async def test_incompatible_insertion_return_does_not_commit(self):
        async def call(name, arguments):
            value = page()
            value["completion"]["required_inventory"]["known_count"] = 1
            return wire(value)

        async def async_insert(text):
            self.fail("unawaited callback result must be closed")

        def synchronous_wrapper(text):
            # A synchronous dispatcher can accidentally return an awaitable.
            return async_insert(text)

        for callback in (synchronous_wrapper, lambda text: "unexpected result"):
            observer = Observer()
            binding = AsyncLeanBinding(call, observer, workflow_surface(CATALOG, "rename"))
            with self.assertRaisesRegex(TypeError, "return None"):
                await binding.collect({"target": "t", "intent": "rename", "format": "lean"}, callback)
            self.assertEqual(observer.summary()["injected_chars"], 0)
            self.assertFalse(observer.summary()["boundary_accounting_complete"])

    async def test_identity_conflict_discards_every_old_source(self):
        values = [page(remaining=1), page(offset=1)]
        values[1]["snapshot"]["health_fingerprint"] = "changed"
        observer = Observer()
        calls = []

        async def call(name, args):
            calls.append(args)
            return wire(values[len(calls) - 1])

        binding = AsyncLeanBinding(call, observer, workflow_surface(CATALOG, "rename"))
        result = await binding.collect({"target": "t", "intent": "rename", "format": "lean"}, lambda text: None)
        self.assertEqual(result["reason"], "snapshot_changed")
        self.assertFalse(result["complete"])
        self.assertEqual(observer.summary()["new_context_chars"], 0)


if __name__ == "__main__":
    unittest.main()
