"""Preregistered narrow holdout reporting without changing screening protocols.

The comparison runner continues to record usage-v2. This report labels its raw
usage as diagnostic; attributable included-plan consumption remains unknown in
the absence of independent, sufficiently precise account-window observations.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path

from efficiency_comparison import evaluate_campaign


def sizing(screening: dict) -> dict:
    """Conditional log-ratio precision planning, not noninferiority or power proof."""
    tasks = screening["evaluation"]["per_task"]
    ratios = []
    for values in tasks.values():
        a, d = (values[c]["primary_per_accepted_task"] for c in ("A", "D"))
        if a is None or d is None or a <= 0 or d <= 0:
            raise ValueError("sizing requires fully accepted positive paired screening costs")
        ratios.append(math.log(d / a))
    if len(ratios) < 2:
        raise ValueError("sizing requires more than one paired task")
    deviation = statistics.stdev(ratios)
    desired_log_half_width = math.log(1.3)
    minimum = math.ceil((1.96 * deviation / desired_log_half_width) ** 2)
    balanced = max(12, math.ceil(minimum / 6) * 6)
    return {
        "method": "normal log-ratio approximation; variance borrowed from known screening",
        "screening_task_count": len(ratios),
        "paired_log_ratio_sample_sd": deviation,
        "desired_multiplicative_half_width": 1.3,
        "minimum_independent_tasks_approximation": minimum,
        "balanced_authored_holdout_tasks": balanced,
        "replicas_per_condition": 2,
        "solver_turns": balanced * 4,
        "expected_uncached_input_from_screening_mean": screening["total_uncached_input_tokens"] / len(screening["runs"]) * balanced * 4,
        "zero_failure_one_sided95_bound_by_task": 1 - 0.05 ** (1 / balanced),
        "limitations": "Task heterogeneity and nonrandom authored sampling limit this approximation. Replicas are not independent tasks. This is not power for a savings threshold or paired quality noninferiority.",
    }


def report(manifest: dict, runs: list[dict]) -> dict:
    """Record G5 evidence, including negative results, in its frozen narrow scope."""
    registration = manifest.get("confirmation", {})
    if (
        registration.get("revision") != "holdout-report-v1"
        or registration.get("corpus_role") != "untuned_authored_holdout"
        or registration.get("replicas_per_condition") != 2
        or registration.get("included_plan_primary") != "attributable_allowance_per_accepted_task"
        or registration.get("runtime_execution") is not False
        or manifest.get("protocol_revision") != "comparison-v2"
        or {c["id"]: c["graph_enabled"] for c in manifest["conditions"]} != {"A": False, "D": True}
        or manifest["analysis"].get("comparisons") != [["D", "A"]]
        or len(manifest["tasks"]) != 12
        or len(manifest["schedule"]) != 24
        or {t["id"] for t in manifest["tasks"]} != set(registration.get("task_ids", []))
        or any(block["phase"] != "P3" or block["replica"] not in (1, 2) for block in manifest["schedule"])
        or {(block["task_id"], block["replica"]) for block in manifest["schedule"]}
        != {(t["id"], r) for t in manifest["tasks"] for r in (1, 2)}
    ):
        raise ValueError("incomplete frozen holdout registration")
    result = evaluate_campaign(manifest, runs)
    comparable = result["consumption_evidence"]["comparable"] and result["isolation_evidence"]["verified"] and result["quality_evidence"]["verified"]
    failed_tasks = sorted({r["task_id"] for r in runs if not r["success"]})
    accepted_by_task = {
        t["id"]: all(result["per_task"][t["id"]][c]["accepted_cells"] == 2 for c in ("A", "D"))
        for t in manifest["tasks"]
    }
    return {
        "protocol_revision": "holdout-report-v1",
        "status": "not_run" if not runs else "evidence_recorded" if comparable else "incomplete_evidence",
        "all_static_outcomes_accepted": comparable and all(accepted_by_task.values()),
        "failed_task_ids": failed_tasks,
        "sampling_unit": "authored_task_with_both_conditions_and_all_replicas",
        "scope": "Twelve untuned controlled TypeScript source structures; one installed Codex client/model/effort. Static postimages/findings only, no runtime or other-language claim.",
        "included_plan_primary": {"metric": registration["included_plan_primary"], "value": None, "reason": "No sufficiently precise attributable account-window observations; shared account activity is not excluded."},
        "raw_usage_diagnostics": {"aggregates": result["aggregates"], "per_task": result["per_task"], "per_class": result["per_class"], "comparisons": result["comparisons"]},
        "quality": {"general_noninferiority": "not_established", "static_accepted_by_task": accepted_by_task,
            "zero_failure_one_sided95_bound_by_task": 1 - 0.05 ** (1 / 12) if comparable and not failed_tasks else None,
            "bound_assumption": "Independent task-level Bernoulli sampling; authored nonrandom corpus limits any population interpretation."},
        "product_savings_confirmed": False,
        "release_interpretation": "Report effect and intervals even when negative; +15% versus A belongs to the user's 1.0 objective. Critical source failures still require correction; this report cannot certify included-plan savings.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screening", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--runs", type=Path)
    args = parser.parse_args()
    if args.screening is not None and args.manifest is None and args.runs is None:
        value = sizing(json.loads(args.screening.read_text()))
    elif args.screening is None and args.manifest is not None and args.runs is not None:
        value = report(json.loads(args.manifest.read_text()), json.loads(args.runs.read_text()))
    else:
        parser.error("choose --screening or both --manifest and --runs")
    print(json.dumps(value, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
