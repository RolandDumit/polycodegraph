"""Development regressions: explicit source policy and real insertion boundaries."""

from __future__ import annotations

import json
import unittest

from efficiency_client import LeanAdapter, Observer
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
