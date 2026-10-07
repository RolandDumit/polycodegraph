# Authorized 24-turn screening

This screening compares A (bounded source tools only) with D (the same tools plus
one task-specific opt-in workflow). Both local tasks offer exactly the A surface
in both conditions. Twelve controlled static TypeScript tasks cover two instances
of each family: local edits, ambiguous renames, public signatures, symptom bugs,
branched flows and large-file reviews. The source generator is
`tool/efficiency_gate_corpus.py`; independent expected postimages remain outside
solver workspaces. No indexed application code, compiler hooks or project scripts
run. Acceptance requires exact permitted source bytes and findings, visible
precision limits, isolated credentials, and actual use of the assigned treatment.

Freeze the full task/source/oracle, binary, provider, model, client, tool catalog,
guide, isolation, measurement and schedule identities before the first turn. Use
one attempt per cell and six A/D and six D/A sequences, reversing the order of the
two tasks in each family. Each cell has a fresh workspace and client session.
There are no preparation or judge AI turns and no external solver retries.

The authorized budget is 24 additional turns and 1,000,000 additional uncached
input tokens using `gpt-6.1-sol`, effort `high`. Control happens after each attempt;
final-attempt overshoot is accepted. Per-attempt guards are 100,000 uncached input,
2,000,000 total input, 60,000 output tokens, 80 provider requests and 900 seconds.
Token/request guards are observed after completion; elapsed time is enforced.
Any missing usage or measurement failure stops subsequent turns. Monetary cost
and internal provider transport retries remain unknown.

The primary metric includes **all input and output tokens divided by accepted
tasks**, including cost of rejected attempts. Also report uncached input per
accepted task, all pages and expansions, ordinary tool calls, acceptance and
paired exploratory intervals. G3 requires at least 20% lower primary cost than A,
no increase in uncached input per accepted task and comparable quality. G4 checks
the 5% local-task margin and zero critical rename/signature regressions. Measure
native warm p95 and sampled process-tree RSS separately; they are not model tokens.
The native guard is 5 seconds per warmed complete collection and 512 MiB sampled
process-tree RSS on this fixture workload, with cold costs reported separately.

These are known controlled tasks. The two instances within each family share a
template, so task bootstrap intervals are exploratory and do not establish
repository-wide generalization or 5% quality noninferiority. Static acceptance
does not certify application runtime behavior. G5 requires unseen holdout tasks,
an independent replication and a later budget sized from observed variance.
Internal provider prompt insertion remains unknown (G2-mechanism); wire receipts
and complete usage can support G2-product under plan §6.3.
