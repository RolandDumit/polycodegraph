# 0.10.0-dev.2 work and release criteria

Continue on `codex/0.10-token-efficiency`. The annotated `v0.10.0-dev.1`
tag freezes commit `90eec266f05755e98f60def8d26c7ba5f968592c` and its
T0–T2 screening evidence. Historical manifests and measurements remain unchanged.

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
