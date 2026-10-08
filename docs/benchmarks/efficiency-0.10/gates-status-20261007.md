# 0.10 gate continuation, 2026-10-07

This dated status describes dev.1 and its screening. Subsequent milestone
clarification and T3–T6 work are recorded separately in
[the dev.2 report](dev2-results-20261008.md); the historical G3 result is unchanged.

The T0–T2 development implementation was pushed as `0.10.0-dev.1` on
`codex/0.10-token-efficiency`, source commit
`52802dda7440c89715f7b5016c5dab176973fa80`. This is a development branch;
the rollout and measured-savings gates remain open.

## Current evidence

| Gate | Evidence and remaining work |
| --- | --- |
| G0 | Passed for the frozen 24-turn screening: identities, task-specific registration, actual treatment and isolated credentials verified. |
| G1 | Native deterministic/provider/differential and rename checks pass in the recorded fixture scope. Latest platform CI passes all 20 jobs, including Android and UIKit SDK checks; conditional skipped steps are not coverage. |
| G2-product | Passed for screening: complete usage, paired task identities, actual offered surfaces, treatment and independent static oracles. |
| G2-mechanism | Exact internal provider prompt/insertion remains unavailable in the current client. Qualify attribution according to plan §6.3; do not infer insertion from wire receipts. |
| G3 | Failed screening: D used 54.3% more total tokens and 42.8% more uncached input per accepted task than A; both accepted 12/12. |
| G4 | Recorded guards pass in fixture scope: local token cost +0.135%, zero critical rename/signature defects, native warm p95 23–333 ms and sampled RSS below 321 MiB. Whole-solver p95 is higher for D; no general regression-free claim. |
| G5 | Not run. Current candidate fails G3; establish a useful revised-candidate signal before independent confirmation and a new explicit run/token budget. |

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

At preparation, no screening turn had run. The completed campaign now has 24/24
accepted static results and consumed 506,060 additional uncached input tokens;
all 24 authorized turns were used. The preparation requirement was to freeze the
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

## Completed screening

[Screening results](screening-results-20261007.md) record the full negative result,
observations by task/family, token and runtime intervals, actual boundary counts,
static oracle limits and zero-AI source-view diagnosis.
[Confirmation sizing](confirmation-sizing-20261007.md) uses the measured
dispersion for conditional planning; it neither authorizes more AI turns nor
claims a current advantage. Keep the native workflow opt-in. T3/T4 have not been
silently enabled by the diagnostic experiment.

## Final platform evidence

[CI for code commit b272b24](https://github.com/RolandDumit/polycodegraph/actions/runs/37653431960)
completed successfully: all 20 jobs passed, including native packages on Linux,
Windows, macOS arm64 and macOS Intel; Dart/Flutter/polyglot/mobile checks;
Android SDK and macOS UIKit SDK checks; native workflow/differential/rename
validation and core tests. Local `cargo xtask check`, 81 Python tests, native
workflow smoke and the twelve zero-AI task preflights also passed. The UIKit SDK
fixture actually resolved 13 symbols and 23 edges; it was not skipped.

[Platform evidence](platform-validation-20261007.json) preserves the tested code
identity and successful job links. The final results commit changes reports only
and reuses these completed checks.
[Current gate evaluation](gate-evaluation-20261007.json) records the remaining
G3 failure, qualified G2-mechanism boundary and unrun G5. The 0.10 development
branch is published; the proposed stable savings rollout is not accepted.
