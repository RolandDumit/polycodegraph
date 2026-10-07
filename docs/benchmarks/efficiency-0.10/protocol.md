# Efficiency 0.10 first-tranche preregistration

Registered 2026-10-07. Status: deterministic implementation/replay; **AI execution
not authorized**. This extends the existing runner as `comparison-v2`. Historical
comparison-v1/post08-v1 reports are not recomputed under a different primary.

Primary: sum of total provider input plus output for **all attempts**, including
failed/retried attempts, divided by accepted cells (`T_accepted`). Cache read and
creation follow the provider's accounting; reasoning is a subset of output.
Supporting: uncached input per accepted cell (`U_accepted`), cached/creation/output,
accepted/assigned cells, critical defects, required sites lost, out-of-scope edits,
model requests, all tool calls, PCG calls/pages/errors/expansions/retries, corrective
reads, compactions, solver/oracle latency, cold/warm retrieval and memory. Unknown
values stay null, including interrupted attempt usage; zero acceptance is undefined.
Money requires actual rates/receipts and a separate verified scope.

## Conditions and ablations

- A: strong no-graph baseline, no PCG artifacts/schemas/instructions, the same
  ordinary reading/search/editing tools, model/effort and independent oracle.
- B: exact v0.9.0 commit `f1e0484cb1ac66f0fe623fc6e8c4531a886b0a07`, distributed
  legacy responses/full surface and ordinary instructions; not C's optional mode.
- C: exact v0.9.0, compact/agent/lean and collection-1; declare its adapter and
  registered schemas/instructions rather than calling this the default release.
- D: frozen T0–T2 candidate, local surface with no graph when applicable, static
  canonical workflow for structural tasks and fused opt-in collection selection.

Schema-only, instructions-only and full-treatment ablations are separate cells.
Do not change the model or weaken A. No lazy tool-registration support is assumed.
Static schema selection must really be applied by the executor at task start.
Freeze actual server initialization guidance as well as the consumer guide; an
MCP client's retained initialization instructions are part of its fixed overhead.
The packaged `efficiency_mcp.py` relay provides an ordinary MCP entrypoint for D
and explicit schema/guide/collection ablations. Freeze its module hashes, startup
arguments, actual registered surface and retained guide for each cell. Its private
receipt observes prepared responses; provider prompt insertion stays unknown
unless independently observed by the executor. For A, omit PCG entirely rather
than registering an empty local relay. The native zero-model preflight does not
replace the separately authorized treatment-use smoke.

## Progressive stages and stop rules

1. Deterministic replay and native tests: zero model calls, inventory/source/limits
   equality, rename oracle, 0.6 primitive differential and identity/timeout gates.
2. After explicit budget approval: up to four real wiring smokes, one per condition.
   Require complete receipts, actual treatment use and independent acceptance.
   Smokes establish wiring, not a token advantage.
3. Separately authorized screening: 12 distinct tasks, two per six historical
   families (local edit, ambiguous rename, public signature, symptom bug, branched
   flow, large-file review), paired A/D, one replica: 24 runs before retries.
   A frozen schedule balances ordering. C/D ablations need their own budget.
4. Confirmation on independent held-out tasks, with replication and sample size
   determined from screening variance and preregistered quality/power requirements.
   Replicas of a task are not independent tasks.

Before any AI phase freeze private task snapshots/prompts, source manifests,
independent oracles, binary/client/parser/provider artifacts and source identities,
model/version/effort, actual schemas/config/instructions, schedule, enforcement
status and stop criteria. Candidate edits require a new identity/campaign.
The frozen 0.9 binary is locally hash-checked against its published validation
receipt; prepared adapter artifacts must also be frozen/version-matched separately.
No paid executor or new corpus has been silently installed or selected.

Budget approval must include phase, total/preparation runs, maximum uncached input
and economic cap/estimate when available. Retain the runner's explicit
after-attempt control and disclose possible final-attempt overshoot. Unknown usage
stops new attempts. A private append-only journal preserves interruptions; operational
preparation/invalidated campaign costs remain separate and visible. Current approved
AI runs, preparation AI runs and judge AI runs are all **zero**.

G0: frozen identity/isolation and applied treatment. G1: every required fixture
site, offset, confidence, phase, source hash and limit preserved; no false complete.
G2-product: complete provider receipts and paired treatment/oracle identities.
G2-mechanism additionally needs per-request materialized schemas/instructions and
tool/collection/insertion/source correlation. Missing internal prompt visibility
limits attribution but does not redefine the historical G2 or fabricate usage.

G3 target: at least 20% lower T_accepted than A, no higher U_accepted, comparable
quality. Zero lost required sites or critical rename/signature errors is mandatory.
G4: local task diagnostic margin 5%, no critical regressions, bounded collector and
observed p95 latency. G5: held-out confirmation with paired task-level bootstrap,
dispersion, intervals and explicit untested client/language/model scope. Screening
does not demonstrate narrow quality non-inferiority; freeze the confirmation margin
and power/sample plan before those runs. No quality-invariance claim without that gate.

If D improves C but remains worse than A, report that outcome. Keep graph use
opt-in or restricted to demonstrated task classes. Reduced payload with higher
total task usage, extra corrective reads or lost sites is a failed treatment.
Do not add T3/T4, embeddings, neural graph models or LLM summaries before assessing
the first tranche. Indexed applications, project plugins, scripts, hooks and
codegen are never executed by this benchmark; quality gaps remain explicit.

## Current unmeasured boundaries

No real model wiring smoke or campaign has run. Provider insertion/usage, corrective
reads, exact model tokenizer, monetary cost, heap/RSS/p95 workload distributions
and held-out acceptance are unknown. Native portable Swift/Objective-C coverage
does not establish macOS UIKit coverage. Deterministic result serialization is
reported separately in [the implementation report](report.md).
