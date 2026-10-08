# G5 — untuned authored holdout, proposed execution

This confirmation records the effect of the corrected 0.10 candidate on new
source structures and reports uncertainty, including negative results. The
user's +15% total-token target versus A belongs to 1.0; it is not reintroduced
as a 0.10 release requirement. Neither passing this evidence gate nor releasing
0.10 establishes included-plan savings.

## Corpus and controls

Twelve separately authored controlled TypeScript tasks, two per historical
family, replace the screening templates. They include object/array local edits,
rename through a re-export and import alias, a static method with homonyms,
multiple distinct argument expressions, mixed direct and forwarding consumers,
Boolean and arithmetic symptom fixes, a diamond and recursion flow, an endpoint
review and pure declaration relocation. There is no model-based preparation or
selection. The corpus generator is `tool/efficiency_holdout_corpus.py`.

The fixtures are new and untuned, but authored after seeing the screening;
they are not a random sample of real repositories. Family labels preserve the
historical grouping; the new review fixtures do not certify large-file scaling.
No benefit is generalized to other languages, clients, models or application
runtime. The independent static oracle remains outside the solver's source
allowlist. Exact postimages/findings and rejection of unrelated mutations are
verified before execution, including native review baseline comparisons.

Compare A (no graph/schema/graph guide) and D (the corrected workflow client).
Use two serial fresh-workspace replicas per condition: **48 solver turns**.
Alternate order within task and across replicas. Freeze binary, source,
providers, profile schemas, instructions, ordinary tool host, oracles, parser,
corpus, schedule and stop rules before the first model turn. No tuning or
candidate correction during the campaign; record every failure and interruption.

## Sizing and interpretation

The dev.2 screening's 12 paired log total-token ratios have sample standard
deviation **0.37917**. A conditional normal planning approximation for a 95%
log-ratio interval with multiplicative half-width 1.30 gives
`ceil((1.96 × 0.37917 / log(1.30))²) = 9` task units. Balance six families at
12 tasks, with two replicas to expose within-task variation. Replicas do not
increase the independent task count. This borrowed variance and different
source structures make the calculation provisional; it does not guarantee the
width of the aggregate ratio bootstrap or power for a savings threshold.

At the screening mean, 48 turns would use about **1,113,938 uncached input
tokens**. The requested aggregate limit is **1,500,000**. These are planning
figures, not a monetary quote or included-plan allowance estimate.

`holdout-report-v1` reports all attempts, acceptance, paired differences and
aggregate usage ratios with 5,000 paired-task bootstrap resamples, seed
20261008. All replicas and conditions stay together when sampling a task.
Intervals are conditional diagnostics for this authored corpus. No general
quality noninferiority is claimed: even zero failed task units out of 12 has
a one-sided 95% absolute failure upper bound of about **22.1%**, under independent
Bernoulli sampling, which itself is not established for this authored sample.
Critical rename/signature postimage failures require correction and stay visible.

The [subscription policy](../../codex-plan-consumption.md) fixes attributable
included allowance per accepted task as the economic primary. It stays unknown
when account activity cannot be excluded or counter precision is insufficient.
The comparison runner's `usage-v2` total-token axis is a raw usage diagnostic;
`tool/efficiency_confirmation.py` supplies the separate holdout report and
explicit unknown quota. It cannot upgrade raw-token savings to subscription
savings. Historical comparison-v1/v2 screening results are immutable.

## Requested authorization and stopping

Request **48 new solver turns**, `gpt-6.1-sol`, effort `high`, maximum additional
**1,500,000 uncached input tokens**, checked after every turn. The final turn may
exceed the threshold; this is not a hard token cap. Economic cost is unverified.
Stop at 48 turns, exhausted aggregate budget, incomplete usage or interruption.
No external retry, preparation AI, model judge, indexed application execution,
plugins, scripts, hooks, code generation or runtime tests are authorized.

The T3 eight-turn allocation is consumed and cannot fund this campaign. The
proposal itself grants no budget. Native/ordinary-host preflight has completed
without model turns; the private draft remains execution-disabled pending
explicit authorization. This allocation does not include T6 or model compaction.
