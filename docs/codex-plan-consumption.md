# Codex plan consumption policy

Adopted 2026-10-08. The product goal is to complete more correct coding tasks
within the user's included Codex allowance. The monthly subscription fee does
not imply a monthly token bucket or a per-token invoice.

## Metric priority

For future Codex subscription experiments, the primary product outcome is
**observed included-plan allowance consumed per accepted task**, reported
separately for each actual usage window and limit bucket. Preserve correctness,
required evidence, freshness and visible precision limits.

If attributable allowance consumption cannot be measured, report it as
`unknown`. Use a **rate-weighted token/credit equivalent per accepted task** as
an explicitly labelled supporting proxy. Raw total tokens, uncached input,
cached input, output and model requests remain mandatory diagnostic measures.
Neither raw token counts nor credit/API prices establish subscription usage.

Include every model call and failed attempt assigned to a condition. Report
preparation, coordination and invalidated-campaign consumption separately,
without hiding it. With zero accepted tasks, per-accepted-task metrics are
undefined; report consumption and failures instead of zero.

## Token categories and weights

- Uncached input: input processed without a matching prompt-cache reuse.
- Cached input: input reused from a matching prefix; it is a subset of total
  input, not an additional quantity. Instructions, schemas, history and tool
  results can contribute to either input category.
- Output: generated text, code, tool-call arguments and reasoning. Reasoning
  tokens are already included in output; never add them again.

Weights depend on the model, billing system, speed mode and current rate card.
Do not treat cached input as free, apply one weight to all tokens, or assume a
short final answer accounts for all output. Freeze the applicable official
rate-card URL, verification date, units and model/speed settings before a new
campaign. Do not hard-code today's prices as a universal runner constant.

As verified on 2026-10-08, the official **Codex credit** rates for GPT-6.1 Sol
at Standard speed are:

| Category | Credits per million tokens | Relative weight |
| --- | ---: | ---: |
| Uncached input | 50 | 1 |
| Cached input | 2.5 | 0.05 |
| Output, including reasoning | 250 | 5 |

For this specific rate card, with `U`, `C` and `O` denoting the complete
uncached-input, cached-input and output counts:

`standard_credit_equivalent = (50 * U + 2.5 * C + 250 * O) / 1_000_000`

This is a credit equivalent, **not observed included-plan quota or a euro
charge**. Codex credit billing has no separate cache-write charge. API pricing
is a separate contract; where cache-write pricing applies, use its actual
accounting and avoid charging the same input twice. Unknown rate/counter
components prevent an exact charge claim.

## Observing included-plan consumption

Preregister the account's actual limit buckets/windows and the client boundary
used to read usage. For each measured interval, retain before/after usage,
observation times, window/reset identities, plan/model/speed settings and
counter precision. A dashboard percentage is a percentage of its own bucket,
not tokens, credits or euros. Never add percentages from different windows.

Exclude concurrent account activity from the measurement interval where
possible, or mark attribution as unknown. Account usage may be shared across
Codex and other eligible features. A reset, changed allowance, stale/delayed
counter or coarse rounding can invalidate a delta. A displayed zero delta is
not evidence of free usage when the counter cannot resolve the consumption.
Do not reconstruct historical quota from current account counters.

Compare paired tasks with the same plan/window, model, effort, speed, client,
task/oracle and declared cache conditions. Report quality, uncertainty,
latency and scope alongside consumption. A measured improvement in one
bucket or fixture is not a general monthly-plan savings claim.

## Historical evidence and implementation boundary

Existing manifests, primary metrics, reports, tags and gate decisions remain
unchanged. `comparison-v1` uses uncached input and `comparison-v2` uses raw total
tokens as their frozen primaries. This document does **not** implement a quota
collector or change the current runner's validation. A future runner/protocol
revision and preregistration must precede a new primary-metric experiment.

For illustration only, applying the Standard credit rates above to the recorded
dev.2 totals gives A = 17.02249 and D = 19.61298 credit equivalents: **+15.22%**.
The frozen raw-total result remains **+55.9%**; observed subscription consumption
remains unknown. This calculation is not a new model run, a billed-credit
receipt or a reclassification of the historical savings gate. See
[the dev.2 screening](benchmarks/efficiency-0.10/dev2-screening-report-20261008.md).

Adopting this metric policy grants no new AI run, spending or execution
authorization. Existing explicit run/token budgets and stop rules still apply.

## Official references

- [Codex pricing, token rates and included-plan usage](https://learn.chatgpt.com/docs/pricing#token-rates): credit prices alone do not determine included subscription consumption; model, context, reasoning, tools, retrieval and caching affect usage.
- [Token accounting and reasoning/output subsets](https://developers.openai.com/api/docs/guides/agents-api/observability#understand-token-usage).
- [API pricing](https://developers.openai.com/api/docs/pricing): separate from subscription and Codex credit billing.

Reverify current pricing and plan rules before each new cost experiment.
