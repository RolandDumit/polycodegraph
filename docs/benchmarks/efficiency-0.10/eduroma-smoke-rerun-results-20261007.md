# EduRoma: four fresh smokes after runner repairs, 2026-10-07

**A, B and the 0.10 candidate D passed campaign acceptance. C completed its
source task and native tool invocation, but exceeded its preregistered
per-attempt token guard.** The repaired routing and native cache path worked
in all four conditions. The comparison remains inconclusive; these results
do not establish general token savings or noninferiority.

[Machine-readable results](eduroma-smoke-rerun-results-20261007.json) retain all
four observations, usage, treatment identities, budget failure and precision
limits. The [repair preregistration](eduroma-smoke-rerun-20261007.md) and
[repair source manifest](smoke-runner-fix-source-manifest.json) remain unchanged.
The [previous failed campaign](eduroma-smoke-20261007.md) remains a separate
historical result.

## Execution and results

The user explicitly authorized four new solver turns after review of the fixes,
using `gpt-6.1-sol`, effort `high`, with 100,000 additional aggregate uncached
input tokens. The limit is checked after each attempt, with an explicitly
accepted possible final-run overshoot. Economic cost is unverified.

All four cells used the same repaired client, bounded source tools, isolation,
512 MiB allowance for owned derived files, independently capped 8 MiB executor
stdout/stderr, source snapshot, task, model and deterministic source oracle.
The fixed execution order was **A, B, D, C**. Every cell had a fresh client
context, home and cache. There were no replayed answers, external retries,
preparation AI or judge AI.

| Condition | Configuration | Campaign outcome | Source answer | Uncached input | Total tokens | Usage events |
| --- | --- | --- | --- | ---: | ---: | ---: |
| A | No graph tools, schema or guide | Accepted | Verified | 33,455 | 71,409 | 5 |
| B | Exact 0.9; 16 tools; audit | Accepted | Verified | 31,594 | 220,724 | 9 |
| D | 0.10; one workflow tool; automatic collection | Accepted | Verified | 23,283 | 86,152 | 5 |
| C | Exact 0.9; five tools; lean collection-1 | Per-attempt budget exhausted | Verified separately after the campaign | 47,802 | 172,458 | 8 |

C exceeded the observed-only **40,000 uncached-input per-attempt guard by
7,802 tokens**. Its journal remains `budget_exhausted`, with campaign acceptance
false. The runner did not invoke the oracle within that budget-exhausted
attempt. A supplementary, zero-AI invocation of the same frozen source oracle
verified C's exact answer and actual native treatment use. That diagnostic
does not retroactively accept C or change the frozen limits or journal.

Aggregate usage was **136,134 uncached input tokens**, exceeding the proposed
100,000 threshold by **36,134** in the final authorized attempt. The first three
attempts consumed 88,332; C started with positive remaining budget under the
explicit `remaining_positive` reservation policy. No further run started.
Total input was 546,758, including 410,624 cached tokens, and output was 3,985,
for **550,743 total tokens** across 27 measured usage increments. Reasoning
output, 717, is a subset of output and is not added again.

The previous campaign's 92,475 uncached input tokens are accounted separately;
the two campaigns together consumed 228,609. Every failed tool call and the
budget-exhausted C attempt remain in the accounting.

## Native tools and precision

Actual registered graph tools were A: 0, B: 16, C: 5 and D: 1, matching captured
canonical MCP schemas. B/C/D each made two native graph calls. B returned one
audit intent page; C one collection-1 page; D two intent pages, one through
collection-1 and one through collection-2. Both candidate collections retained
one text block without structured duplication. D's automatic choice of either
format is permitted by its frozen configuration.

Ordinary source-tool calls were A: 10, B: 12, D: 8 and C: 10. Bound tool errors
were respectively 2, 1, 1 and 1. These errors and their subsequent successful
tool calls are included in measured usage; they are not extra solver retries.
No compaction was observed. Native responses arrived without the prior
cache-file-limit timeout, and ordinary tools worked in A/B as well as C/D.

C and both D collections retain `provider_incomplete=true`,
`remaining_known=0` and `collection.complete=false`. All solvers disclosed
static-analysis limits; C/D explicitly disclosed provider incompleteness.
Correct source facts and working tool delivery do not imply a complete semantic
inventory, runtime correctness, compiler verification or rename safety.

One known authentication task with one replica per condition, plus C's budget
failure, cannot satisfy the measured-savings acceptance gate. Exact per-request
provider context and insertion, cache-write counters, provider internal
transport retries and economic cost remain unverified. Byte or character
counts are not substituted for measured model tokens.

## Integrity and checks

The task remained read-only: identify the production authentication contract,
implementation, login delegation and composition registration. The snapshot
contained 385 Dart files and 408 files overall. Hashes of all 401 original
source/configuration files remained unchanged. No indexed application code,
plugins, hooks, package scripts, builds, tests or code generation ran.

All four isolation probes passed. Temporary credential copies were removed.
Frozen executor, oracle, client, schema, provider and binary hashes were verified
before execution and after completion. The repair measurement identity is
`7cc2b05b31b7ed54d11b5043070e7fcc52e7d739df7987287e18820907cbef95`;
the approved manifest identity is
`8867bbd67972d4700569064ba7e06909ccca81e3c7b523e19c211df5aebe22f3`.

The repair validation passed 76 Python tests, configured lint/format checks and
`cargo xtask check` with 88 Rust tests. This run changed no native resolver,
provider implementation or shipped client module. Windows file-size enforcement,
Android/UIKit SDK checks and application compilation/tests are not claimed as
verified coverage. Raw project text, prompts, answers and traces remain private
in ignored campaign directories.
