# 0.10 screening result: savings gate failed

The authorized screening completed **24 solver turns on 12 distinct controlled
static TypeScript tasks**, with 12/12 accepted for A and 12/12 for D. The candidate
used **54.3% more total tokens per accepted task** and **42.8% more uncached input**.
G3 fails both preregistered cost requirements. Keep the workflow opt-in; this
candidate has no demonstrated savings advantage over A on any screened family.
No stable-release or general quality claim follows from this experiment.

## Complete cost and acceptance

| Measure | A: source tools | D: task workflow |
| --- | ---: | ---: |
| Accepted tasks | 12 / 12 | 12 / 12 |
| Total input + output tokens | 874,776 | 1,349,485 |
| Total tokens per accepted task | 72,898 | 112,457.08 |
| Uncached input tokens | 208,407 | 297,653 |
| Uncached input per accepted task | 17,367.25 | 24,804.42 |
| Provider usage events | 71 | 77 |
| Ordinary leaf tool calls | 327 | 349 |
| Native graph leaf calls | 0 | 42 |
| Successfully delivered native pages | 0 | 39 |
| Model-facing graph calls | 0 | 25 |
| Source reads | 183 | 219 |
| Solver elapsed p95, 12 observations | 51.25 s | 80.90 s |

The campaign consumed **506,060 of 1,000,000 authorized additional uncached input
tokens**, with no budget overshoot and no failed solver attempts. External solver
retries, preparation AI and judge AI were zero. Internal provider transport
retries and economic cost remain unknown. Dynamic tool errors handled within a
single turn remain included in all charged usage and boundary counts.

Total-cost D/A was **1.5427**, paired task-bootstrap exploratory 95% interval
**[1.2110, 1.9218]** (2,000 resamples). Median paired ratio was **1.2014**, with
sample standard deviation **0.3689** on log ratios. There were two related
instances per family; this interval does not establish repository-wide inference
or narrow quality noninferiority. The frozen runner's generic verdict remains
`INCONCLUSIVE` for holdout/generalization; that does not override the explicitly
failed G3 screening threshold.

| Task family | D/A total tokens per accepted task |
| --- | ---: |
| Local edit | 1.0013 |
| Ambiguous rename | 1.2761 |
| Public signature | 1.5857 |
| Symptom bug | 1.1784 |
| Branched flow | 1.1413 |
| Large-file review | 2.8195 |

All exact postimages and requested findings passed independent static oracles.
The rename/signature checks preserved all permitted consumer edits and left
homonyms, wire strings and unrelated source bytes unchanged. These oracles do
not execute application code or certify runtime correctness. They check the
presence of a limitations field, not every natural-language claim inside it.

## Identity, wiring and observation limits

The [preregistered campaign](screening-preregistration-20261007.md) froze source
commit `88d22a728e99aea3cb46e87b0da00e4fd44fb64e`, candidate binary
`3d57898f8a46590c22ffcc2f987fdb677be09c67c8411106c8ad0e7371166a24`, manifest
`0d017847738090bb321ccaf4bab16269f02d78649a2d20f907d6887bfc05e7b8`,
`gpt-6.1-sol` effort `high`, and Codex CLI 0.159.2 app-server. Six A/D and six D/A
sequences used fresh workspaces and sessions. The frozen identities still
validated after all turns. Later watcher smoke repairs changed only the test
harness; the solver's frozen modules and binary stayed identical.

Both local D cells registered no graph server and received the same ordinary
surface as A. The ten structural D cells used their actual task-specific static
catalog and native intent. Actual catalog hashes, leaf RPCs, source host calls,
all native pages and complete provider usage were recorded. The solver's
filesystem was read-only; a trusted host applied bounded, hash-checked literal
edits only inside each copied source allowlist. No copied credential file remained
in any cell after execution.

The [boundary audit](screening-boundary-audit-20261007.json) reports actual offered
catalog sizes as characters/bytes, **not measured model tokens**. It distinguishes
ordinary/native leaf calls from outer graph calls and model code-mode wrappers.
Native calls were all `inspect_change`; expansion tool calls were zero. Reads
after the first successful edit were 66 for A and 106 for D; their necessity or
classification as corrective reads is unknown. Complete charged input/output
usage supports G2-product. Internal prompt insertion and exact per-schema/token
attribution remain unavailable, qualifying G2-mechanism under plan §6.3.

## Native runtime and remaining gates

The [native benchmark](native-runtime-results-20261007.json) measured complete
collections on four known fixture tasks, with 20 warmed observations each and
all continuations included. Inventories were equivalent to native 0.9. D warm
p95 ranged **23.3–333.2 ms**, sampled peak descendant RSS was **320.9 MiB** maximum,
and cold first-collection costs were **0.70–1.01 s**. These pass the preregistered
5-second warm and 512-MiB sampled guards on this workload. D's native timings and
RSS are higher than the corresponding baseline; this is no speed or memory
reduction claim. Shared OS caches, concurrent campaign activity and 25-ms Linux
RSS sampling limit the measurement.

G0 and G2-product pass for this frozen screening. G1 deterministic checks and
G4's local-token/critical-edit/native-bound checks pass in their recorded fixture
scope, with [all 20 platform CI jobs passing](platform-validation-20261007.json). Local token cost
rose only **0.135%**, inside the 5% diagnostic margin; two local pairs cannot
establish general noninferiority. Whole-solver p95 was higher for D and is reported
separately from the bounded native collector.

**G3 failed; G5 has not run.** A holdout confirmation of savings is premature
while this candidate fails the primary target. The next useful work is a new,
separately identified T3 experiment on intent-specific context and review metadata,
with deterministic inventory/source checks first. The largest observed overhead
is review; extra ordinary reads and larger charged input are observed, while
internal causal attribution remains unknown. T4 seed search was not evaluated:
these tasks supply known targets, so they cannot justify a retrieval rewrite.
A subsequent AI phase requires new run-count authorization even though the token
budget was not fully used; all 24 authorized turns have been consumed.

Raw private receipts, prompts, oracle keys and environment paths remain ignored.
[Sanitized results](screening-results-20261007.json) preserve the full totals,
per-task observations, per-family metrics and exploratory intervals. Earlier
smoke costs remain separate and are neither replayed nor charged to this budget.

## Zero-AI follow-up for T3

Actual outer receipts show 22 of 25 graph calls explicitly requested
`full_evidence`; two omitted the view and one requested `edit_context`. A separate
[source-view diagnostic](source-view-diagnostic-20261007.json) therefore compared
complete native projections on all ten structural fixture tasks without changing
the frozen candidate or spending further AI tokens. All normalized required
records/sites, confidence and provenance remained equal across the compared views.

Selecting `locations` for rename reduced complete projected characters by
34–35%; `contracts` for signatures reduced them by 36–38%; `locations` for current
review context reduced them by 12–14%. `edit_context` made essentially no
material difference for these small bug/flow fixtures. These are deterministic
character counts, not model tokens. Review in this diagnostic has no before/after
baseline, so it does not establish review-delta savings. A new policy must be
explicit, preserve caller-requested context and every required site, and verify
source-read behavior and baseline deltas before a new AI campaign. Smaller payload
alone is insufficient to close G3.
