# Frozen acceptance protocol for the 0.6 candidate

Date: 2026-10-02. Primary outcome is uncached executor input, not MCP bytes or
latency. Do not change this protocol after inspecting candidate token results.

## Conditions and order

Six fresh contexts, sequential A1/B1/C1 then C2/B2/A2; no automatic extra batches.
A has no graph, B uses official 0.5 and the previous harness, C uses the fixed
candidate revision/profile and only the targeted graph instructions. Use
gpt-6.1-sol/high in every case, identical unrelated tools and common task prompt,
the same original unrenamed 385-source snapshot, and a final report capped at
150 words. Record tool schemas, source/build identities, model/effort and first
request cache separately. Index preparation happens before each executor run;
report its time/cost independently, without excluding any in-run overhead.

Task: rename `Presenza.data` and its constructor parameter to `dataTimbratura`,
preserving DTO/JSON keys, unrelated `data` fields and behavior. Use isolated
copies, never the original checkout or an already renamed copy. The independent
validator must confirm 7 changed files / 21 expected occurrences, no unrelated
edits/new diagnostics, 9 regression checks and 2 data tests. Reconfirm this
baseline before starting; if it differs, record the new baseline before runs.

Executors must not access other cases, reports, oracle or reference patches.
Use a restricted broker/tool environment; instructions alone are not proof of
access isolation. Freeze the exact common prompt/tool surface before running.
The parent retains validation/oracle and records all failed attempts.

## Token accounting and gates

Preflight reliable usage counters for fresh executors before spending six runs.
Read only `token_count` and model/effort metadata; keep rollouts local/ignored.
`tool/token_usage.py` verifies cumulative totals against per-request events,
deduplicates unchanged totals and sums reset segments. Missing/disagreeing
counters fail validation rather than producing an estimate. Cached input is
part of input; reasoning is part of output; never add them again.

For all six runs record uncached input, cached input, output, reasoning subset,
total, first request/cache, correctness, attempts and preparation/coordinator
cost separately. Compare both replicas and averages C/A and C/B. The gate is:
all six correct; C mean uncached input at least 20% lower than A; mean cached
input and output at most 5% higher than A. C/B-only benefit is partial. If C
does not improve B, stop and propose a trace-backed revision before another
batch. Two replicas/shared caches do not establish causality/significance or
subscription savings.

After runs, pass local rollout paths and independent correctness booleans to:

```sh
python tool/token_usage.py \
  --run A1=<local-rollout> --run B1=<local-rollout> --run C1=<local-rollout> \
  --run C2=<local-rollout> --run B2=<local-rollout> --run A2=<local-rollout> \
  --validation <local-validation.json> --output <aggregate-report.json>
```

Publish aggregated measurements only. Do not publish machine paths, whole
responses, source snapshots, credentials or messages from other conversations.
An aggregate tool report cannot by itself verify tool isolation/source/task
parity; include the independent execution manifest and validator evidence.

## Current status

Deterministic MCP replay and semantic checks are complete; the six fresh
executor runs are **not performed**. The current session has not established a
restricted fresh-executor environment matching the previous broker and recording
per-run counters. Old usage counters were verified, but are not candidate
results. Therefore the primary token gate is not measurable in this delivery.
Compact remains experimental opt-in; no version bump, release or plan-completed
claim is authorized by these output-volume results.
