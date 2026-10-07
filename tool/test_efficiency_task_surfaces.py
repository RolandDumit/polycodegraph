"""Task-specific registration proofs: no model, credentials or indexed execution."""

import copy
import tempfile
import unittest
from pathlib import Path

from efficiency_benchmark import evaluate, validate_manifest
from efficiency_comparison import cells
from test_comparison import manifest, record


class TaskSurfaces(unittest.TestCase):
    def test_local_zero_and_profile_specific_receipts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            frozen = manifest(root)
            candidate = next(c for c in frozen["conditions"] if c["id"] == "D")
            candidate["task_surfaces"] = {
                "t0": dict(
                    graph_enabled=False, schema_sha256=None, harness_sha256=None
                ),
                "t1": dict(
                    graph_enabled=True,
                    schema_sha256="rename-schema",
                    harness_sha256="harness",
                ),
            }
            self.assertEqual(validate_manifest(frozen, root), [])
            runs = [record(frozen, c) for c in cells(frozen)]
            local = next(
                r for r in runs if r["condition"] == "D" and r["task_id"] == "t0"
            )
            local["client"].update(
                graph_mcp_calls=0,
                graph_artifacts_visible=False,
                graph_surface_sha256=None,
                graph_harness_sha256=None,
            )
            structural = next(
                r for r in runs if r["condition"] == "D" and r["task_id"] == "t1"
            )
            structural["client"]["graph_surface_sha256"] = "rename-schema"
            self.assertTrue(
                evaluate(frozen, runs)["consumption_evidence"]["comparable"]
            )
            wrong_profile = copy.deepcopy(runs)
            next(
                r
                for r in wrong_profile
                if r["condition"] == "D" and r["task_id"] == "t1"
            )["client"]["graph_surface_sha256"] = "schema"
            self.assertFalse(
                evaluate(frozen, wrong_profile)["consumption_evidence"]["comparable"]
            )
            local["client"]["graph_artifacts_visible"] = True
            self.assertFalse(evaluate(frozen, runs)["isolation_evidence"]["verified"])
            candidate["task_surfaces"].pop("t0")
            with self.assertRaisesRegex(ValueError, "cover exactly"):
                validate_manifest(frozen, root)

    def test_reference_cannot_gain_graph_or_local_guide(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            frozen = manifest(root)
            reference = frozen["conditions"][0]
            reference["task_surfaces"] = dict.fromkeys(
                ["t0", "t1"],
                dict(
                    graph_enabled=True, schema_sha256="schema", harness_sha256="guide"
                ),
            )
            with self.assertRaisesRegex(ValueError, "enabled task surface"):
                validate_manifest(frozen, root)
            reference["task_surfaces"] = dict.fromkeys(
                ["t0", "t1"],
                dict(graph_enabled=False, schema_sha256=None, harness_sha256="guide"),
            )
            with self.assertRaisesRegex(ValueError, "exclude graph"):
                validate_manifest(frozen, root)
