"""Extract only usage metadata, and evaluate the preregistered six-run gate.

Never exports conversation messages or copies a rollout. Cache is part of input;
reasoning is part of output. No inference about subscription allowance/pricing.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean

FIELDS = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "reasoning_output_tokens", "total_tokens")
ORDER = ("A1", "B1", "C1", "C2", "B2", "A2")


def counters(value):
    result = {key: value[key] for key in FIELDS}
    if any(type(n) is not int or n < 0 for n in result.values()):
        raise ValueError("invalid token counter")
    if result["cached_input_tokens"] > result["input_tokens"] or result["reasoning_output_tokens"] > result["output_tokens"]:
        raise ValueError("invalid cached/reasoning subsets")
    if result["total_tokens"] != result["input_tokens"] + result["output_tokens"]:
        raise ValueError("total does not equal input + output")
    return result


def extract(events):
    previous = None
    last = None
    summed = dict.fromkeys(FIELDS, 0)
    segments = dict.fromkeys(FIELDS, 0)
    first = None
    duplicates = resets = observed = 0
    models, efforts = set(), set()
    for event in events:
        if event.get("type") == "turn_context":
            payload = event.get("payload", {})
            if payload.get("model"):
                models.add(payload["model"])
            if payload.get("effort"):
                efforts.add(payload["effort"])
        payload = event.get("payload", {})
        if event.get("type") != "event_msg" or payload.get("type") != "token_count" or not payload.get("info"):
            continue
        info = payload["info"]
        total = counters(info["total_token_usage"])
        last = counters(info["last_token_usage"])
        if total == previous:
            duplicates += 1
            continue
        if previous and any(total[key] < previous[key] for key in FIELDS):
            for key in FIELDS:
                segments[key] += previous[key]
            resets += 1
            previous = None
        delta = {key: total[key] - (previous[key] if previous else 0) for key in FIELDS}
        if delta != last:
            raise ValueError("cumulative counters disagree with per-request usage; fresh/reset context cannot be verified")
        for key in FIELDS:
            summed[key] += last[key]
        first = first or last
        previous = total
        observed += 1
    if not observed:
        raise ValueError("no reliable token_count events")
    final = {key: segments[key] + previous[key] for key in FIELDS}
    if final != summed:
        raise ValueError("usage sum disagrees with final cumulative totals")
    return {"total_token_usage": final, "uncached_input_tokens": final["input_tokens"] - final["cached_input_tokens"], "first_request_token_usage": first, "usage_events": observed, "duplicates_ignored": duplicates, "counter_resets": resets, "sum_matches_cumulative": True, "model": sorted(models), "reasoning_effort": sorted(efforts)}


def evaluate(runs, validation):
    if tuple(runs) != ORDER or set(validation) != set(ORDER):
        raise ValueError("need six runs in A1/B1/C1/C2/B2/A2 order and correctness for each")
    for usage in runs.values():
        total = counters(usage["total_token_usage"])
        if usage["uncached_input_tokens"] != total["input_tokens"] - total["cached_input_tokens"] or usage.get("sum_matches_cumulative") is not True:
            raise ValueError("run usage is internally inconsistent or unverified")
    settings = {(tuple(v["model"]), tuple(v["reasoning_effort"])) for v in runs.values()}
    if len(settings) != 1 or not all(v["model"] and v["reasoning_effort"] for v in runs.values()):
        raise ValueError("model/effort are missing or differ between runs")
    components = ("uncached_input_tokens", "cached_input_tokens", "output_tokens")
    averages = {}
    for condition in "ABC":
        selected = [v for key, v in runs.items() if key.startswith(condition)]
        averages[condition] = {key: mean(v[key] if key == "uncached_input_tokens" else v["total_token_usage"][key] for v in selected) for key in components}
    comparisons = {}
    for base in "AB":
        comparisons["C/" + base] = {key: 100 * (averages["C"][key] / averages[base][key] - 1) if averages[base][key] else None for key in components}
    replicas = {}
    for replica in ("1", "2"):
        for base in "AB":
            candidate, reference = runs["C" + replica], runs[base + replica]
            replicas[f"C{replica}/{base}{replica}"] = {}
            for key in components:
                numerator = candidate[key] if key == "uncached_input_tokens" else candidate["total_token_usage"][key]
                denominator = reference[key] if key == "uncached_input_tokens" else reference["total_token_usage"][key]
                replicas[f"C{replica}/{base}{replica}"][key] = 100 * (numerator / denominator - 1) if denominator else None
    correctness = all(v is True for v in validation.values())
    primary = comparisons["C/A"]
    reached = correctness and primary["uncached_input_tokens"] is not None and primary["uncached_input_tokens"] <= -20 and all(primary[k] is not None and primary[k] <= 5 for k in ("cached_input_tokens", "output_tokens"))
    improved_b = comparisons["C/B"]["uncached_input_tokens"] is not None and comparisons["C/B"]["uncached_input_tokens"] < 0
    secondary_passed = all(primary[k] is not None and primary[k] <= 5 for k in ("cached_input_tokens", "output_tokens"))
    return {"outcome": "reached" if reached else "partial" if correctness and improved_b and secondary_passed else "failed", "correctness_passed": correctness, "averages": averages, "comparisons_percent": comparisons, "replica_comparisons_percent": replicas, "runs": runs, "validation": validation, "limits": "two replicas, shared cache, no causal/significance or subscription-quota claim; includes all executor overhead"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="append", required=True, help="NAME=local rollout path; six-run order required")
    parser.add_argument("--validation", type=Path, required=True, help="JSON NAME:boolean; independent full correctness checks")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runs = {}
    for spec in args.run:
        name, path = spec.split("=", 1)
        if name in runs:
            raise ValueError("duplicate run name")
        with Path(path).open(encoding="utf-8") as stream:
            runs[name] = extract(json.loads(line) for line in stream)
    report = evaluate(runs, json.loads(args.validation.read_text()))
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
