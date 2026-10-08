"""Development regressions: explicit source policy and real insertion boundaries."""

from __future__ import annotations

import copy
import json
import unittest

from efficiency_binding import AsyncLeanBinding
from efficiency_client import LeanAdapter, Observer
from efficiency_collection import normalized_inventory, source_windows
from efficiency_retention import RetainedContext
from efficiency_workflow import workflow_arguments, workflow_surface
from test_efficiency010 import CATALOG, page, wire


class InsertionBudget(unittest.TestCase):
    def test_workflow_policy_is_explicit_and_preserves_requested_view(self):
        surface = workflow_surface(CATALOG, "rename")
        args = {
            "target": "t",
            "intent": "rename",
            "format": "lean",
            "view": "full_evidence",
        }
        result = workflow_arguments(surface, args)
        self.assertEqual(result["source_policy"], "intent")
        self.assertEqual(result["view"], "full_evidence")
        self.assertNotIn("source_policy", args)

    def test_exact_budget_caps_the_final_inserted_representation(self):
        # A deterministic test tokenizer, not a model-token measurement.
        observer = Observer()
        adapter = LeanAdapter(
            lambda *_: wire(page()),
            observer,
            max_input_tokens=300,
            count_tokens=lambda text: len(text.encode()),
            tokenizer_id="test-utf8-bytes",
        )
        result = adapter.collect({"target": "t", "intent": "rename"})
        self.assertLessEqual(len(result["text"].encode()), 300)
        self.assertEqual(result["reason"], "collector_token_budget")
        self.assertFalse(result["complete"])
        self.assertEqual(json.loads(result["text"])["collection"]["limit"], "collector_token_budget")
        self.assertEqual(observer.injected_bytes, len(result["text"].encode()))

    def test_missing_or_invalid_tokenizer_never_claims_exact_budget(self):
        with self.assertRaises(ValueError):
            LeanAdapter(None, Observer(), max_input_tokens=20)
        observer = Observer()
        adapter = LeanAdapter(
            lambda *_: wire(page()),
            observer,
            max_input_tokens=20,
            count_tokens=lambda _: 0.5,
            tokenizer_id="invalid",
        )
        with self.assertRaisesRegex(ValueError, "nonnegative integer"):
            adapter.collect({"target": "t", "intent": "rename"})
        self.assertEqual(observer.injected_chars, 0)


class Retention(unittest.IsolatedAsyncioTestCase):
    async def test_acknowledgement_insertion_compaction_and_identity_changes(self):
        value = page(text="α\r\n" + "retained source " * 400)
        value["completion"]["required_inventory"]["known_count"] = 1
        retention = RetainedContext()
        observer = Observer()
        binding = AsyncLeanBinding(lambda *_: None, observer, workflow_surface(CATALOG, "rename"), retention=retention)

        async def call(*_):
            return wire(copy.deepcopy(value))

        binding.call = call
        args = {"target": "t", "intent": "rename", "format": "lean", "view": "full_evidence"}
        # Preparing or writing protocol output cannot establish retention.
        prepared = json.loads((await binding.collect(args))["text"])
        with self.assertRaises(ValueError):
            retention.acknowledge(retention.epoch, prepared["retention"]["offered_windows"])
        inserted = []
        first = json.loads((await binding.collect(args, inserted.append))["text"])
        retention.acknowledge(retention.epoch, first["retention"]["offered_windows"])
        second = json.loads((await binding.collect(args, inserted.append))["text"])
        self.assertEqual(second["retention"]["referenced_windows"], 1)
        self.assertNotIn("text", source_windows(second)[0])
        self.assertLess(len(inserted[1]), len(inserted[0]))
        self.assertEqual(normalized_inventory(first), normalized_inventory(second))
        old_epoch = retention.epoch
        retention.compaction()
        with self.assertRaises(ValueError):
            retention.acknowledge(old_epoch, first["retention"]["offered_windows"])
        rehydrated = json.loads((await binding.collect(args, inserted.append))["text"])
        self.assertIn("text", source_windows(rehydrated)[0])
        for field in ("root_id", "generation", "health_fingerprint", "environment_fingerprint"):
            retention.acknowledge(retention.epoch, rehydrated["retention"]["offered_windows"])
            value["snapshot"][field] += "changed"
            rehydrated = json.loads((await binding.collect(args, inserted.append))["text"])
            self.assertEqual(rehydrated["retention"]["referenced_windows"], 0)
            self.assertIn("text", source_windows(rehydrated)[0])

    async def test_failed_insertion_never_offers_acknowledgements(self):
        retention = RetainedContext()
        value = page(text="source " * 400)
        value["completion"]["required_inventory"]["known_count"] = 1

        async def call(*_):
            return wire(value)

        binding = AsyncLeanBinding(call, Observer(), workflow_surface(CATALOG, "rename"), retention=retention)

        def insert(_):
            raise RuntimeError("failed insertion")

        with self.assertRaises(RuntimeError):
            await binding.collect({"target": "t", "intent": "rename", "format": "lean"}, insert)
        self.assertFalse(retention.offered)
        self.assertFalse(retention.known)

    async def test_source_hash_baseline_phase_truncation_and_bounded_fallback(self):
        context = RetainedContext(max_windows=1)
        value = page(text="source " * 400)
        first = context.prepare(value)
        context.committed(first)
        context.acknowledge(context.epoch, first["retention"]["offered_windows"])
        for change in ("hash", "baseline", "phase", "truncated"):
            changed = copy.deepcopy(value)
            if change == "hash":
                changed["sources"][0]["source_hash"] = "new"
            elif change == "baseline":
                changed["request"] = {"options": {"baseline": "new-baseline"}}
            elif change == "phase":
                changed["sources"][0]["phase"] = "before"
            else:
                changed["sources"][0]["windows"][0]["truncated"] = True
            projection = context.prepare(changed)
            self.assertIn("text", projection["sources"][0]["windows"][0])
            self.assertLessEqual(len(projection["retention"]["offered_windows"]), 1)
        with self.assertRaises(ValueError):
            LeanAdapter(None, Observer(), retention=context)

    async def test_compaction_between_preparation_and_insertion_rehydrates(self):
        context = RetainedContext()
        value = page(text="source " * 400)
        value["completion"]["required_inventory"]["known_count"] = 1
        observer = Observer()
        adapter = LeanAdapter(lambda *_: wire(value), observer, defer_insertion=True, retention=context)
        first = json.loads(adapter.collect({"target": "t", "intent": "rename"})["text"])
        adapter.commit_insertion()
        context.acknowledge(context.epoch, first["retention"]["offered_windows"])
        second = json.loads(adapter.collect({"target": "t", "intent": "rename"})["text"])
        self.assertNotIn("text", source_windows(second)[0])
        context.compaction()
        restored = json.loads(adapter.insertion_text())
        self.assertIn("text", source_windows(restored)[0])
        adapter.commit_insertion()
        self.assertFalse(context.offered)
        self.assertEqual(normalized_inventory(first), normalized_inventory(restored))

    async def test_legacy_collection_retention_is_bound_to_actual_review_baseline(self):
        value = {"format": "pcg-lean-collection-1", "pages": [page(text="source " * 400)]}
        context = RetainedContext()
        args = {"options": {"baseline": "before-a"}}
        first = context.prepare(value, args)
        context.committed(first)
        context.acknowledge(context.epoch, first["retention"]["offered_windows"])
        repeated = context.prepare(value, args)
        self.assertEqual(repeated["retention"]["referenced_windows"], 1)
        different = context.prepare(value, {"options": {"baseline": "before-b"}})
        self.assertEqual(different["retention"]["referenced_windows"], 0)
        self.assertIn("text", source_windows(different)[0])
