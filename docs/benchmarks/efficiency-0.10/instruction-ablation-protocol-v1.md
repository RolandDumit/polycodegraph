# instruction-ablation-v1 — diagnostic protocol

This separate version permits a graph-enabled reference for a paired
instruction-only diagnostic. `comparison-v1` and `comparison-v2` keep their
mandatory no-graph product reference and historical metrics. No existing
manifest or result is upgraded to this protocol.

The registered comparison has two graph-enabled conditions, an explicit
reference/candidate and one candidate/reference comparison. Every frozen task
has the same graph schema in both conditions. Native binary, native source
identity, configuration, provider artifacts and shared client runtime hashes
must match. The workflow instructions differ and are frozen per task. Base
instructions and ordinary tool host are shared executor identities. The
instruction-bearing workflow module is separately frozen in each treatment;
native paired preflight verifies schema/source/inventory equivalence.

The diagnostic criterion is preregistered in `analysis.behavioral_primary` as
`same_hash_post_edit_reads_per_accepted_task`, with the exact decision in the
campaign proposal. Client receipts provide the bounded audit. Missing,
malformed or evicted classifications stay unknown; zero accepted tasks leaves
per-accepted values undefined. Receipt equality never proves read necessity or
correctness. All attempts contribute to the counts and token accounting.

The inherited `primary_metric: total_tokens_per_accepted_task` selects the
runner's **raw usage accounting axis**, including cached input and output,
using `usage-v2`. It is a mandatory diagnostic cost field, not a measurement of
subscription allowance. The behavioral criterion is reported separately.
Product/economic interpretation follows the [subscription policy](
../../codex-plan-consumption.md): actual attributable quota has priority;
unknown quota stays unknown, frozen weighted credits are supporting proxies,
and raw categories remain visible. This protocol does not implement a quota
collector or replace the historical product savings primary retrospectively.

The runner returns `DIAGNOSTIC_ONLY` for a fully measured isolated comparison,
never a product savings or rollout verdict. This label means the comparison
was recorded, not that the behavioral criterion passed. Static acceptance,
failures, missing attribution and the proposal's behavioral decision remain
separate. There is no no-graph product control, independent G5 confirmation or
general quality claim.

The existing bounded serial scheduler, source snapshots, independent oracles,
append-only attempt journal, interruption handling and explicit after-attempt
AI budget still apply. Lack of authorization blocks launch, and this protocol
grants no solver/preparation/judge budget. Every actual campaign freezes its
identities, requested counts, limits and stopping rule before a model turn.
