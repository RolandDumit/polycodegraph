# 0.10.0-dev.2 work and release criteria

Continue on `codex/0.10-token-efficiency`. The annotated `v0.10.0-dev.1`
tag freezes commit `90eec266f05755e98f60def8d26c7ba5f968592c` and its
T0–T2 screening evidence. Historical manifests and measurements remain unchanged.

The user clarified the product goal on 2026-10-08: extend the included Codex
subscription allowance. Future experiments follow the
[plan consumption policy](codex-plan-consumption.md), distinguishing observed
quota, rate-weighted credit equivalents and raw tokens. The completed dev.2
screening retains its original primary; no subscription-quota savings were
measured and no new AI budget is implied.

The user clarified on 2026-10-08 that the target of at most 15% additional
total tokens relative to A belongs to 1.0. The historical screening savings gate
failed; it is not reclassified as passing. Stable 0.10 requires completing the
T3–T6 tranche with compatible defaults, verified correctness and honest limits,
not achieving the 1.0 efficiency target.

Implementation order:

- T3: explicit intent source policy, independent source budget, preserved required
  inventory and explicit client insertion tokenizer budget where supported.
- T4: scope-aware bounded lexical indexing, anchor grouping, inverted lookup and
  optional ranking ablation. Keep the lexical baseline selectable.
- T5: distinguish known inventory, local diagnostic relevance and unknown task
  coverage without weakening global health or freshness.
- T6: explicit client retention acknowledgement, epoch reset and rehydration;
  self-contained fallback remains available. No inferred model retention.

Deterministic checks precede any new paid campaign. The previous 24 authorized
screening turns are complete; a new campaign needs an explicit run/token budget.
Character or byte measurements do not establish model-token savings. T6 cannot
be enabled in a generic MCP relay that cannot observe retained client context.

Create `v0.10.0-dev.2` only at a verified checkpoint. Publish stable `v0.10.0`
after final validation and release notes; no stable tag is created during work.

Implementation and current verification are recorded in the
[dev.2 report](benchmarks/efficiency-0.10/dev2-results-20261008.md). T3–T6 have
code and deterministic regression coverage. The [24-turn screening](benchmarks/efficiency-0.10/dev2-screening-report-20261008.md)
is complete: all static outcomes pass, total tokens are +55.9% versus A, and T3
read counts increase. Independent confirmation, T4 discovery benefit and T6
end-to-end compaction savings remain unmeasured. The annotated dev.2 tag is
published; no stable tag has been created.

The [T3 follow-up](benchmarks/efficiency-0.10/t3-followup-20261008.md) adds targeted
edit-receipt guidance and a bounded audit of the existing post-edit read hashes.
Deterministic checks pass; its behavioral effect needs a separately authorized
diagnostic ablation. Historical acceptance and savings gates remain unchanged.

That [eight-turn diagnostic](benchmarks/efficiency-0.10/t3-readback-results-20261008.md)
is now complete under a separate authorization: all static outcomes pass,
same-hash post-edit reads decrease from 85 to zero, and direct reads from 178 to
87. The correction passes its narrow refactoring criterion. Total tokens fall
15.5% versus the old guide; uncached input increases 14.4%. Included-plan savings
remain unknown. There is no fresh A control or general source-policy claim.

[G5 preparation](benchmarks/efficiency-0.10/g5-holdout-proposal-20261008.md) has
twelve new untuned authored tasks with native and independent-oracle preflight,
two proposed replicas and a new budget request. [T6's installed-client audit](
benchmarks/efficiency-0.10/t6-model-verification-20261008.md) identifies the missing
exact retained-context boundary. Both model gates remain open; neither has an
AI allocation from the completed T3 diagnostic.
