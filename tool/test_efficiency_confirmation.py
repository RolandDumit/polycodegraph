"""Holdout evidence cannot turn missing quota or incomplete replications into savings."""

import copy
import tempfile
import unittest
from pathlib import Path

from efficiency_comparison import cells, schedule
from efficiency_confirmation import report, sizing
from test_comparison import manifest, record


def registered(root):
    value = manifest(root, task_count=12, replicas=2)
    value.update(protocol_revision="comparison-v2", primary_metric="total_tokens_per_accepted_task")
    value["conditions"] = [c for c in value["conditions"] if c["id"] in ("A", "D")]
    value["schedule"] = schedule([t["id"] for t in value["tasks"]], ["A", "D"], 2)
    for block in value["schedule"]:
        block["phase"] = "P3"
    value["analysis"].update(reference="A", candidate="D", previous=None, comparisons=[["D", "A"]])
    value["confirmation"] = dict(revision="holdout-report-v1", corpus_role="untuned_authored_holdout",
        replicas_per_condition=2, included_plan_primary="attributable_allowance_per_accepted_task",
        runtime_execution=False, task_ids=[t["id"] for t in value["tasks"]])
    return value


class Confirmation(unittest.TestCase):
    def test_complete_lower_raw_usage_still_does_not_prove_included_allowance_savings(self):
        with tempfile.TemporaryDirectory() as temp:
            value = registered(Path(temp))
            runs = [record(value, c, cost=10 if c[2] == "D" else 20) for c in cells(value)]
            result = report(value, runs)
            self.assertEqual(result["status"], "evidence_recorded")
            self.assertTrue(result["all_static_outcomes_accepted"])
            self.assertIsNone(result["included_plan_primary"]["value"])
            self.assertFalse(result["product_savings_confirmed"])
            self.assertEqual(result["quality"]["general_noninferiority"], "not_established")
            self.assertLess(result["raw_usage_diagnostics"]["comparisons"]["D/A"]["ratio"], 1)

    def test_missing_replica_and_failed_source_oracle_remain_visible(self):
        with tempfile.TemporaryDirectory() as temp:
            value = registered(Path(temp))
            runs = [record(value, c) for c in cells(value)]
            self.assertEqual(report(value, runs[:-1])["status"], "incomplete_evidence")
            runs[-1]["success"] = False
            result = report(value, runs)
            self.assertFalse(result["all_static_outcomes_accepted"])
            self.assertEqual(result["failed_task_ids"], [runs[-1]["task_id"]])
            self.assertIsNone(result["quality"]["zero_failure_one_sided95_bound_by_task"])
            wrong = copy.deepcopy(value)
            wrong["schedule"].append(wrong["schedule"][0])
            with self.assertRaisesRegex(ValueError, "registration"):
                report(wrong, runs)

    def test_sizing_uses_task_variance_and_does_not_count_replicas_as_tasks(self):
        screening = {"evaluation": {"per_task": {
            "x": {"A": {"primary_per_accepted_task": 100}, "D": {"primary_per_accepted_task": 100}},
            "y": {"A": {"primary_per_accepted_task": 100}, "D": {"primary_per_accepted_task": 150}},
        }}, "total_uncached_input_tokens": 400, "runs": [None] * 4}
        value = sizing(screening)
        self.assertEqual(value["screening_task_count"], 2)
        self.assertEqual(value["solver_turns"], value["balanced_authored_holdout_tasks"] * 4)
        screening["evaluation"]["per_task"]["x"]["D"]["primary_per_accepted_task"] = None
        with self.assertRaisesRegex(ValueError, "fully accepted"):
            sizing(screening)


if __name__ == "__main__":
    unittest.main()
