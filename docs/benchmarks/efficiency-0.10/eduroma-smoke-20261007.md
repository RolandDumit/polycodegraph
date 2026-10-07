# EduRoma: real-client wiring smoke, 2026-10-07

**Partial smoke; real-model acceptance remains on hold.** Four authorized solver
turns ran, one each for A/B/C/D, using `gpt-6.1-sol`, effort `high`, through Codex
CLI 0.159.2 app-server. C passed the source task and invoked PCG successfully.
A/B encountered a client routing error; D encountered an inherited cache-file
limit. These results do **not** establish comparative token savings.

[Machine-readable results](eduroma-smoke-20261007.json) contain normalized
provider counters, treatment identities, native-call accounting and limitations.
The [first-tranche report](report.md) remains the frozen, pre-AI snapshot.

## Task and source protection

The task was read-only: identify the production authentication contract, its
direct implementation, the usecase login delegation and their composition-root
registration. All conditions received the same source snapshot, prompt and
bounded literal-search/source-reading tools. PCG use was required when registered.
An independent deterministic oracle checked exact symbols/paths and the source
relationships, without using a graph response as its answer key.

The snapshot contained 385 Dart files and 408 files overall. Hashes of 401 original
source/configuration files remained unchanged. Package-resolution metadata was
rewritten consistently for the isolated snapshot. Project scripts, plugins,
hooks, application builds, tests and code generation were not executed.
Client credentials were confined to a protected channel and removed after each
paid turn. Isolation probes passed; final credential-file checks found none.
Raw project text, prompts, reference answers and traces remain in ignored private
campaign directories and are not included in this report.

## Results and accounting

The fixed execution order was A, B, D, C. Each condition had one paid solver turn;
there were no preparation/judge AI turns or external retries. The table includes
failed turns and every recorded provider usage increment.

| Condition | PCG configuration | Outcome | Uncached input | Total tokens | Usage events |
| --- | --- | --- | ---: | ---: | ---: |
| A | No graph registration, schema or guide | Tool routing failed; answer unverified | 11,666 | 34,231 | 3 |
| B | Exact 0.9, full 16-tool surface, audit response | Tool routing failed; attempt guard exceeded | 26,815 | 40,348 | 3 |
| C | Exact 0.9, five tools, lean collection-1 | Source task and PCG invocation accepted; provider inventory incomplete | 27,843 | 173,365 | 8 |
| D | 0.10 candidate, one workflow tool, automatic collection selection | Source answer verified; PCG collection timed out; attempt guard exceeded | 26,151 | 335,949 | 22 |

Aggregate measured usage was **92,475 uncached input tokens**, within the approved
100,000-token limit. Total input was 579,515, including 487,040 cached tokens;
output was 4,378, for 583,893 total tokens. Reasoning output, 1,530 tokens, is a
subset of output and is not added again. Economic cost is unverified.

Transparent wire captures observed C's two native graph calls (`status` and
`inspect_change`) and one returned intent page. D attempted one native intent
call and returned zero native pages. Ordinary source-tool calls were C: 10 and
D: 11. A/B never reached ordinary source or native graph tools; each produced
two routing errors. Bound source-tool errors were retained in the private traces
and their model usage is included above. No compaction was observed.

The journal continuations reused A's original observation as a reference without
another model turn. The published totals select the four unique paid turns and
count A once; they do not sum the replayed journal entries.

## Failures and bounded corrections

The initial client configuration disabled `code_mode_host`, which this model
needs to forward tool calls. A/B received `code-mode host is disabled`, so they
cannot serve as usable no-graph/full-graph baselines. Routing was enabled for
the remaining conditions while shell, application execution and other external
tools stayed disabled.

B exceeded the initial per-attempt 25,000 uncached-input guard. The first journal
stopped after B. D subsequently exceeded its 300,000 total-input attempt guard;
its 26,151 uncached tokens remained within the aggregate authorization. The
remaining journals reserved the already measured consumption before starting
another paid condition. No failed condition was repeated.

The trusted runner's 8 MiB file-size limit also applied to PCG's derived SQLite
files. During D the WAL reached exactly 8,388,608 bytes and the collector returned
`collector_time_budget` after its 240-second allowance. Successful native
preflights produced a 235,847,680-byte database, demonstrating that this global
file limit was inadequate for this fixture.

C used a private launcher copy with a bounded **512 MiB per-file allowance**;
executor response reading remained capped at 8 MiB. A preliminary check under
that same launcher succeeded without AI. C then passed its only paid turn.
The product's default benchmark launcher still retains the original 8 MiB
limit: an explicit allowance for owned derived caches is needed before a new
comparison campaign.

After the correction, a further **zero-AI** RPC check of the 0.10 candidate
succeeded on the same contract-file target used by D. It returned one text
collection-1 response without structured duplication or a timeout. Automatic
selection of collection-1 for that request is allowed; the earlier symbol-target
preflight returned collection-2. This verifies the bounded native/client path,
not a repeated paid D smoke or a token-saving result.

## Precision and remaining acceptance work

C reported `remaining_known=0`, `provider_incomplete=true` and
`collection.complete=false`; the solver disclosed these limits and independently
checked the source facts. The corrected candidate RPC also retained an incomplete
collection. Successful task verification does not establish complete semantic
coverage, compiler correctness, runtime behavior or rename safety.

Actual registration was checked in app-server against captured canonical MCP
schemas: A 0 tools, B 16, C 5, D 1. Every paid turn had complete provider usage
metadata and the requested model/effort. Exact per-request provider context and
tool-result insertion remain unobserved; they are null rather than inferred
from characters or MCP serialization.

Different client/resource revisions, broken A/B baselines and one task/replica
make comparative ratios, noninferiority, component attribution and economic
decisions invalid. T0–T2 end-to-end acceptance remains pending. This smoke does
not justify advancing to T3/T4 on a measured-savings claim.

`cargo xtask check` passed, including 88 Rust tests. No product implementation was
changed by this smoke. Application compilation/tests and Android/UIKit SDK
validation were outside this read-only Dart task and are not claimed as verified
coverage. Frozen campaign artifacts, native binaries and provider identities
were checked; the original project remained untouched.
