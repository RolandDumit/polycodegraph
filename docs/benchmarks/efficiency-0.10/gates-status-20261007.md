# 0.10 gate continuation, 2026-10-07

The T0–T2 development implementation was pushed as `0.10.0-dev.1` on
`codex/0.10-token-efficiency`, source commit
`52802dda7440c89715f7b5016c5dab176973fa80`. This is a development branch;
the rollout and measured-savings gates remain open.

## Current evidence

| Gate | Evidence and remaining work |
| --- | --- |
| G0 | Frozen binary/provider/client identities, actual registration, isolation and treatment use verified for the repaired smoke. Freeze the new screening separately. |
| G1 | Native deterministic/provider/differential and rename checks passed in the recorded fixture scope. Platform CI is being verified; skipped SDK checks are not coverage. |
| G2-product | Complete provider receipts are available for both four-turn smoke campaigns. Screening requires paired task identities and independent oracles. |
| G2-mechanism | Exact internal provider prompt/insertion remains unavailable in the current client. Qualify attribution according to plan §6.3; do not infer insertion from wire receipts. |
| G3 | Not passed. The single repaired task used 86,152 total tokens for D versus 71,409 for A. Twelve distinct paired screening tasks are authorized next. |
| G4 | Collector bounds, cancellation and deterministic regressions pass. Real local-task costs and workload p95/RSS still require measurement. |
| G5 | No independent confirmation run. Its sample size and budget must be set after screening variance is available. |

The historical `report.md`, `readiness.json`, `protocol.md` and source manifests
describe their frozen pre-AI identities. They are not live gate dashboards.
The [repaired smoke report](eduroma-smoke-rerun-results-20261007.md) records
the latest completed model measurements, including C's budget failure and
the authorized final overshoot.

## Authorized next phase

The user explicitly approved **24 additional solver turns**, twelve distinct
tasks paired A/D, `gpt-6.1-sol` with effort `high`, and **1,000,000 additional
aggregate uncached input tokens**. The budget is checked after each attempt,
with possible final-attempt overshoot explicitly accepted. Preparation AI,
judge AI and external solver retries are zero; economic cost is unverified.

No screening turn has run at the time of this preparation record. Freeze the
corpus, source snapshots, oracles, task-specific workflow routing, schedule,
model/client/measurement identities and stop rules before the first run.
Confirmatory G5 runs require a later, separately approved budget. Negative
screening outcomes cannot be relabeled as a passed savings gate.

## Platform follow-up

[CI for the pushed development commit](https://github.com/RolandDumit/polycodegraph/actions/runs/37647140414)
exposed macOS failures in the wire-recorder tests and native workflow smoke.
Their trusted temporary fixtures were spelled through `/var`, a system link to
the canonical directory. The recorder and relay intentionally reject symlink
ancestors for private receipts.

The fix canonicalizes the trusted test fixture roots before invoking the
recorder/relay. Production symlink rejection remains unchanged. The oversized
input regression also verifies that a receipt was created, so an unrelated
path-validation failure cannot satisfy that test. Linux Python tests and native
workflow checks, including a deliberately aliased temporary root, verify this
repair locally; macOS acceptance requires the subsequent CI result.

Subsequent package checks exposed a separate macOS watcher race: the immediate
post-edit review rejected a stale source snapshot. The zero-model smoke now
repeats only that exact stale-hash error, with the same baseline and same process,
for at most five seconds. Provider errors, expired baselines and other failures
are never retried. This bounded lifecycle wait does not add solver retries to the
AI campaign. Local tests cover successful reconciliation, unrelated failures and
deadline exhaustion; native macOS acceptance still depends on CI.

The separately frozen screening uses source commit `88d22a7` and manifest digest
`0d017847738090bb321ccaf4bab16269f02d78649a2d20f907d6887bfc05e7b8`.
Its candidate binary is unchanged by the subsequent smoke-only watcher repair.
See [the preregistration](screening-preregistration-20261007.md) for the controlled
static fixture scope, exact acceptance and stop rules. Results will be recorded
separately after the authorized campaign; historical smoke observations are not
replayed or included in its new budget.
