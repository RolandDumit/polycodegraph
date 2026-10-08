"""Instruction-only controls cannot relax historical product or budget gates."""

import copy
import tempfile
import unittest
from pathlib import Path

from efficiency_benchmark import evaluate, validate_manifest
from efficiency_comparison import cells, schedule
from efficiency_read_audit import audit
from test_comparison import manifest, record


def ablation(root):
    frozen = manifest(root)
    frozen.update(
        protocol_revision="instruction-ablation-v1",
        primary_metric="total_tokens_per_accepted_task",
    )
    frozen["conditions"] = frozen["conditions"][1:3]
    frozen["analysis"].update(
        reference="B",
        candidate="C",
        previous=None,
        comparisons=[["C", "B"]],
        experiment_kind="instruction_only_diagnostic",
        behavioral_primary="same_hash_post_edit_reads_per_accepted_task",
    )
    frozen["schedule"] = schedule([t["id"] for t in frozen["tasks"]], ["B", "C"], 1)
    for condition in frozen["conditions"]:
        condition["harness_sha256"] = condition["id"] + "-guide"
        condition["shared_client_runtime_sha256"] = {"binding": "frozen-common-code"}
        condition["task_surfaces"] = {
            t["id"]: dict(
                graph_enabled=True,
                schema_sha256="schema",
                harness_sha256=condition["harness_sha256"],
            )
            for t in frozen["tasks"]
        }
    return frozen


def observed(frozen, cell):
    value = record(frozen, cell)
    condition = next(c for c in frozen["conditions"] if c["id"] == cell[2])
    value["client"]["graph_harness_sha256"] = condition["harness_sha256"]
    value["client"]["edit_receipt_audit"] = audit([])
    value["client"]["ordinary_tool_calls"] = 0
    return value


class InstructionAblation(unittest.TestCase):
    def test_versioned_graph_control_preserves_the_old_no_graph_requirement(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            frozen = ablation(root)
            self.assertEqual(validate_manifest(frozen, root), [])
            frozen["protocol_revision"] = "comparison-v2"
            with self.assertRaisesRegex(ValueError, "reference must exclude graph"):
                validate_manifest(frozen, root)

    def test_only_guide_can_change_among_frozen_treatments(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            frozen = ablation(root)
            for field in (
                "binary_sha256",
                "config_sha256",
                "shared_client_runtime_sha256",
            ):
                wrong = copy.deepcopy(frozen)
                wrong["conditions"][1][field] = (
                    {"binding": "different"}
                    if field == "shared_client_runtime_sha256"
                    else "different"
                )
                with self.assertRaisesRegex(ValueError, "changed shared"):
                    validate_manifest(wrong, root)
            wrong = copy.deepcopy(frozen)
            wrong["conditions"][1]["task_surfaces"]["t0"]["schema_sha256"] = "different"
            with self.assertRaisesRegex(ValueError, "changed a task schema"):
                validate_manifest(wrong, root)

    def test_diagnostic_does_not_claim_product_savings_or_quota(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            frozen = ablation(root)
            runs = [observed(frozen, cell) for cell in cells(frozen)]
            result = evaluate(frozen, runs)
            self.assertEqual(result["decision"], "DIAGNOSTIC_ONLY")
            self.assertFalse(
                result["economic_interpretation"]["product_savings_confirmed"]
            )
            self.assertTrue(result["consumption_evidence"]["comparable"])
            self.assertEqual(
                result["behavioral_evidence"]["C"][
                    "same_hash_post_edit_reads_per_accepted_task"
                ],
                0,
            )
            next(r for r in runs if r["condition"] == "C")["client"].pop(
                "edit_receipt_audit"
            )
            result = evaluate(frozen, runs)
            self.assertIsNone(
                result["behavioral_evidence"]["C"]["same_hash_post_edit_reads"]
            )

    def test_zero_acceptance_and_no_authorization_remain_undefined_and_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            frozen = ablation(root)
            runs = [observed(frozen, cell) for cell in cells(frozen)]
            for value in runs:
                value["success"] = False
            self.assertIsNone(
                evaluate(frozen, runs)["behavioral_evidence"]["C"][
                    "same_hash_post_edit_reads_per_accepted_task"
                ]
            )
            frozen["budget"]["execution_enabled"] = False
            self.assertIn(
                "AI execution not authorized", validate_manifest(frozen, root)
            )
            with self.assertRaisesRegex(ValueError, "launch blocked"):
                validate_manifest(frozen, root, launch=True)


if __name__ == "__main__":
    unittest.main()
