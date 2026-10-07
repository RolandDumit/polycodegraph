# post08-v1: preregistration before model execution

Registered 2026-10-06. This revision does not change historical 0.8 gates.
No model executor, model/effort identity or paid-run budget is authorized yet.
The authorized limits are zero runs, zero model requests and zero uncached input
tokens. `check`/`prepare`/empty `evaluate` are permitted; `run` must reject this
manifest. Missing usage stays null. No model consumption is inferred from replay.

## Metric and acceptance

Primary: sum of provider uncached input across every attempt divided by accepted
tasks. Zero accepted tasks makes it undefined. Report success/assigned tasks,
consumption/assigned task, input total, cached input, cache creation when exposed,
output, reasoning output, model requests and verified monetary cost. Reasoning
may be an output subset and is not added twice. Preserve raw events locally and
use the existing normalizer's cumulative/delta, reset, deduplication and subset
validation. Unknown timeout usage prevents an economic decision; it is not zero.

Freeze one exact model, effort, client, base harness, ordinary tools, test policy
and independent oracle before launch. No subscription-quota conversion. Prices
require exact model identity and a verified schedule. This revision keeps money
unmeasured rather than substitute a new primary after seeing results.

## E1: exposure diagnosis (not run)

One known local React edit in `view.tsx`, same snapshot/request/acceptance/test
policy. Proposed conditions A0 (neither schemas nor graph instructions), S
(schemas only), I (instructions only, conditional on tool availability), SI
(both); three replicas each, maximum 12 executions, one attempt per cell.
Model/client support for separating S from instructions is unverified. If the
client bundles them, register a reduced supported matrix before execution and
label it a bundle; do not claim schema-only effects. Count spontaneous graph
calls and interpret those runs accordingly. No fake tools or oracle-based router.
Measure actual insertion, not `tools/list` alone. Deferred discovery must include
an actual successful call if selected. CLI/schema instructions are not free.

## E2: diagnostic task comparison (not run)

The manifest proposes three task families: symptom bug, path to destination and
before/after review with line relocation. Three fresh replicas per family, A /
B08 / C-lean, maximum 27 executions with one executor attempt per cell. Reuse of
historical fixtures does not reuse historical runs as replicas. Counterbalance
ABC/BCA/CAB within each family; family rotations are fixed in the manifest.
Each family's aggregate weight is equal (three assigned replicas each).

A excludes the graph and its artifacts/schemas/instructions. B08 uses immutable
final 0.8.0 and its audit format. C-lean uses the same semantic provider assets
plus F1 and the opt-in adapter/projection/policy. Both proposed graph conditions
use compact responses and five advertised agent tools. Graph policy is part of
the treatment, not an identical prompt. Server schemas and actual inserted
schemas/instructions have distinct identities. Native reproduction uses the
full profile and is not the proposed model experiment.

Each attempt starts from an isolated copy and fresh context. Oracle criteria,
reference patches, other runs and raw usage are unavailable to the solver.
Isolated trusted workflow checks may run; the indexing server must never run
application hooks/plugins/codegen. The review solver retains the same starting
working source before making the specified changes in every condition. No
privileged HEAD baseline or omitted graph preparation. Freeze provider/config
and dependency identities; cold graph at each task start, account preparation
and all subsequent queries. Record observed prompt cache behavior, without
claiming control of provider caching. Keep variable run/replica IDs out of the
stable prompt prefix and in runner metadata.

Executor timeout maximum 1200 seconds. No replacement executor attempts in the
proposed matrix. Internal model retries, errors, expansions, optional reviews,
all schemas, pages and checks remain counted. An infrastructure-invalid attempt
retains its costs; no post-hoc replacement is allowed in this revision. A launch
requires registered executor/oracle/surface identities and independently verified
enforcement of campaign request/token limits during an attempt. The outer
runner also stops on exceeded limits or unknown usage. It cannot enforce an
executor's per-request spending by itself.

Consumption evidence requires trustworthy usage, identity, isolation and
correctness. Attribution additionally requires actual insertion and source/read
sequence. Incomplete attribution need not block descriptive consumption results,
but excludes claims that lean projection caused a saving or avoided double input.

## Decisions frozen before runs

Aggregate ratios use sums, not unweighted task-percentage averages. Report per
family and replica medians/variation; replicas are not independent repositories.
Count graph-used tasks separately from graph avoidance. A useful exclusion policy
alone does not demonstrate a code-intelligence benefit. A single diagnostic task
per class cannot establish a general advantage or 5% statistical margin.

With unchanged quality, C/A <= 1 and at least two structural families no worse
in median authorize a separately budgeted F3 or confirmation. A ratio 1..1.10 or
high variability permits at most one bounded, observation-based diagnostic cycle.
Above 1.10 without a cheaper useful segment, stop automatic F3; a stable residual
20–30% excess without a concrete fix supports stopping token-saving investment.
Inferior quality/site loss/scope inconsistency fails the candidate regardless of
cost. Untrustworthy accounts or missing runs yield `inconclusive`. Local E1
non-regression uses a proposed 1.05 aggregate signal, not proof with this sample.

Any segment exception, further diagnostic, F3/E3 or holdout needs a new registered
matrix and explicit budget. No model campaign here is implicitly authorized.
Holdout would include new local/rename/signature/bug/trace/large-review tasks;
general benefit would need more independent tasks. Confirmation target C/A <=
0.90, ambitious <=0.80, with equivalent quality and stated uncertainty. No
optional stopping or discarding unfavorable outliers. Costs of development,
maintenance and deterministic runtime remain separate from solver token costs.
