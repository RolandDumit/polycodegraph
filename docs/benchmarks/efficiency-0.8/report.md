# PolyCodeGraph 0.8 efficiency candidate

This freezes the 2026-10-05 rc.1 implementation/replays. Subsequent AI evidence is
in the [2026-10-06 application pilot](../efficiency-0.8-application/report.md); final
publication is tracked by the [0.8 release notes](../../releases/v0.8.0.md). Its
zero-model-run statements apply to this earlier fixture report. The frozen source
manifest describes rc.1 and is not an assertion that final release sources are unchanged.

2026-10-05. Local candidate `0.8.0-rc.1`, branch `work/efficiency-0.8`, derived
from v0.7.0 / `06e0a72741d2370b74888b86311709dfd9c3f286`. The implementation
is uncommitted; its source manifest and release-binary digest identify the candidate.
No commit, push, PR, tag or release was requested/performed.

The old stash remains `10ec8cca20a08b882f508569acfed18f3617c4f3` (stash@{0},
“On main: 0.8.0-rc.1”). Existing branches/worktree were preserved. No previous
0.8 implementation was imported. Prepared *0.7* provider assets/configurations
and historical replay inputs were reused after F0; baseline/candidate build,
provider copies and caches are separate. The tag and starting HEAD were verified
explicitly, rather than inferred from cleanliness. A final provenance audit found
three pre-final 0.7 files in the prepared asset copies, including Dart intent metadata.
Both copies were replaced with all 47 tracked tag sources, Dart/Kotlin/Go workers were
rebuilt, and affected native/replay/package checks were repeated. Earlier measurements
using those assets are superseded. [Provider provenance](provider-provenance.json)
records source identities and separate compiled worker digests; no provider source
change is part of the candidate.

The deliverable fixes deterministic product defects and provides opt-in experiments
and a benchmark runner. **Zero new AI benchmark runs were performed.** The target
of at least 20% lower accepted-task cost vs A, improvement vs B and equal quality
is **not measured**. Payload size, MCP count and local estimates cannot establish
model usage, monetary savings or subscription quota consumption.

## Identities and baseline

[Manifest](manifest.json) and [source manifest](source-manifest.json) record toolchain,
source/config/harness/server-schema identities and six task snapshots/prompts/criteria.
B is a locked local release build of the exact tag, not the official Linux artifact
whose historical audit digest was supplied in the plan. Baseline cargo xtask check
passed before editing. Raw build/provider/runtime logs, SDK paths and old private
application replay sources remain ignored under work/ or outside Git.

The declared six tasks use the fixed orders ABC, ACB, BAC, BCA, CAB, CBA. They cover
React JSX/local work, Dart domain rename, signature consumers, a symptom bug,
branched trace and large-file review. The Dart pilot is domain code suitable for
Flutter applications, not a widget/runtime benchmark. Flutter native fixtures are
validated separately. Oracle/executor/model/effort/isolation and actual client schema/
instruction insertion identities remain unset; launch is deliberately blocked until
they are registered. Preparation of 18 isolated copies is not 18 AI executions.

## Changes and attribution

| Phase | State | Hypothesis, implementation and actual evidence |
| --- | --- | --- |
| F0 | Implemented, verified locally | Exact clean tag; frozen locked release; separate build/provider/cache directories. Baseline reproduced global-warning growth and default errors for 100/140 functions. |
| F1 | Implemented, verified | Exact limitation identity/first-order dedup and one global test warning; explicit per-page/remaining/collection/exploration/source states. Isolated F1 replay preserves 2/41/101/141 records in 1/2/3/4 pages with four warnings, at unchanged default budget. |
| F2 | Implemented; client experiment pending | Refresh/storage/clone/build/intent phases, provider starts/context/emission, categorized retries and hash volumes, record classes, one-representation bytes/chars. Runner reuses token_usage, validates raw usage/subsets/resets, preserves failures, frozen order and source inventory. Actual model insertion/isolation unobserved. |
| F3 | Implemented; AI benefit pending | Harness/initialize/README permit zero graph calls for known local work and direct targets; no ritual status/search. Discovery avoids indexing. Native registry validation and instructions checked; whole-task routing benefit unmeasured. |
| F4 | Implemented, verified with conservative limits | Explicit hash-checked scoped text capture, minimal handle, bounded line hunks and smallest containing declaration. Body vs contract/global expansion; dirty initial state, imports, additions/removals, shifted lines and health tested. One changed body in 140-function synthetic file yields two records/one page. |
| F5 | Implemented opt-in; end-to-end benefit pending | Locations, headers, AST/site/hunk context and full evidence; merged source windows, distinct mandatory inventory, estimated response and record collection budgets. 512/1024/2048 measured locally; too-small metadata budgets recover explicitly. Unicode/CRLF and late large-function hunks tested. |
| F6 | Implemented, verified | Selective explain focus; signature options affect optional forwarding with compatibility unknown. Destination uses one bounded shortest static path; unrelated branch excluded. Relation buckets prevent irrelevant reference fan-in consuming contract budget; distinct sites preserved. |
| F7 | Implemented opt-in experiment | Explicit root/gen/health/environment/epoch/window acknowledgement, rehydrate, self-contained fallback and visible errors. Exact source-window suppression tested; arbitrary overlapping intervals and cross-request symbol dictionaries deferred. Existing 0.7 within-page dictionaries are reused, not claimed new. |
| F8 | Implemented opt-in experiment | Full accepted registry separate from five advertised tools; status discovers schemas without provider starts. Hidden alias remains callable and validated. Smaller advertised schema measured; real client discovery/cache/usage unmeasured. |
| F9 | Implemented opt-in lexical baseline; relevance/cost gate pending | Bounded line documents, IDF overlap, camel/snake/path tokens, existing semantic anchors and optional direct expansion. No embeddings/new graph database/LLM. Native lexical vs expansion vs name search recorded; no claim of corpus-wide recall or AI improvement. |
| F10 | Selected changes implemented | SQLite file index measured in isolation; independent transactional storage revision tested on schema 3/health-only changes; watcher drops README/log events while preserving structure/overflow recovery. Clone/rebuild/provider persistence/asset-fingerprint caching deferred without representative profiling evidence. |
| F11 | Runner/protocol/manifest delivered; not_measured | No reliable isolated executor/oracle with usage registered. Pilot, ablations, replications and holdout not executed; no historical logs reused as candidate model runs. |
| F12 | Delivered for review | Design, migration/rollback, coherent harness, source/config identities, aggregates and explicit gates/limitations. |

## Deterministic findings

[Baseline review](baseline-review.json), [isolated F1](f1-review.json) and
[final review](candidate-review.json) use a trusted synthetic TypeScript provider to
isolate the Rust core. This adapts the audit's sample; it is not native provider
coverage or an AI run. Warning counts in B are 4/43/103/143 for 1/40/100/140
functions; 100/140 fail the default budget. Isolated F1 has four warnings in all
cases and conserves the full old file-wide inventory. Final localized review has
three relevant distinct warnings, two records and one page for every case. The
file-wide source-change caveat is replaced by explicit localization facts/fallbacks,
not silent removal of static/test coverage warnings. The default 12,000-character
budget was not raised. Oversized real records still error with precise recovery.

[Rename evidence replay](rename-replay.json) retains all 19 resolved references,
17 oracle line patterns, homonym/wire-key separation and every required page/source
expansion. The historical 0.6 deterministic gate passes. It includes schema costs
separately and declares excluded startup calls. A fresh [0.7 replay](baseline-rename-replay.json) checks the frozen B configuration
against the same historical gate. Compared with that 0.7 replay, the
legacy candidate rename payload is larger because of additive completion/requirement
metadata; this is not presented as a B-to-C saving. It is zero model runs.

[Native replay](native-replay.json) measures B/C exact fixture collections, all four
views, three estimated budgets, acknowledgement/rehydration, destination selection,
lexical variants, full/agent/discovered schemas and accepted hidden aliases. Required
signature records are conserved. The small fixture exposes a tradeoff: locations can
avoid source, while source views add metadata and can exceed the old response size.
512 estimated tokens cannot fit the response metadata in this case; 1024/2048 are
reported at their actual outcome, not used as universal required-inventory caps.
Exact acknowledged windows reduce repeated text, but this does not prove lower
whole-task model usage. The replay deliberately injects one structured representation;
the real client may choose text, both, or a transformation and remains unobserved.

## Collection and schema volumes

These are characters of the declared server representation, not provider tokens.
The required three signature records remain present in each native view.

| Native signature collection | Characters | Pages |
| --- | ---: | ---: |
| B legacy | 3839 | 1 |
| C legacy | 4017 | 1 |
| C locations | 3741 | 1 |
| C contracts | 4564 | 1 |
| C edit_context | 4649 | 1 |
| C full_evidence | 4650 | 1 |

Full tools/list is 14032 characters for B and 15589 for C; C's five-tool agent profile
is 8940, plus 784 characters for the measured single advanced-schema discovery.
The discovery request/wrapper and actual model schema serialization are not included
in those response volumes. Acknowledging one retained edit-context window changes
4649 to 4506 characters, and rehydration returns 4653. Acknowledgement arguments have
their own unmeasured model cost.

The matched rename collections use 21047 characters for B and 22394 for C, each with
three collection calls (including source expansion), 24 evidence records and all
19 resolved references. Adding one broker schema representation gives 36266 for B
and 39249 for C. Neither includes the five disclosed startup calls or model work
during editing/testing/retry. The additive candidate default increases this small
legacy collection; selective views/tool exposure require whole-task evaluation.

## Runtime, separate from AI

[SQLite experiment](sqlite-runtime.json) uses 100,000 synthetic edges and 31
DELETE/reinsert/FULL-commit samples. The plan changes SCAN edges to SEARCH using
edge_file. Recorded p50/p95 is 3.456/4.485 ms without vs 0.833/1.262 ms with the
index. Initial writing is 140.7 vs 170.1 ms and database size 10,596,352 vs
12,308,480 bytes. This is an isolated indexed-delete tradeoff, not whole indexing
or accepted-task cost. Existing schema 3 caches and multiple/health-only writes are
tested; old packages rebuild/reject schema 4 on rollback.

The native replay separately records matched cold indexing, 31 warm name queries,
one update, and server/provider/tree resident peaks sampled at 25 ms on Linux.
Warm samples lie within a reconciliation interval; OS/compiler caches are shared,
order is B then C, and one fixture run does not show a robust speed/RAM improvement.
Sampling excludes initialization/unequal feature replays and can miss transients.
Full-snapshot clone remains timed, not eliminated. Provider context-file counts are
requested context, not evidence of incremental compiler work. Provider persistence
is deferred rather than assumed to reduce RAM or AI usage.

| Matched native runtime | B | C |
| --- | ---: | ---: |
| Cold index, ms | 823.90 | 791.93 |
| Single update, ms | 841.97 | 836.47 |
| Warm query p50/p95, ms | 0.1914 / 0.3032 | 0.1971 / 0.2909 |
| Server peak resident bytes | 45383680 | 45449216 |
| Provider tree peak resident bytes | 281358336 | 278663168 |
| Total tree peak resident bytes | 326742016 | 319602688 |

## Verification and gate status

[Validation inventory](validation.json) records the exact local checks, source/binary
identities and explicitly unmeasured platform/AI coverage.

| Check | Actual status |
| --- | --- |
| Baseline cargo xtask check and locked release | Passed before edits |
| Candidate cargo xtask check | Passed: format, warning-free clippy, 72 Rust tests |
| Python usage/evaluator/boundary tests | Passed: 13 tests, including historical usage parser and synthetic accounting/boundary tests |
| Native intent smoke mixed and Flutter | Passed on Linux; ten intents, ten languages; primitives compared with 0.6 |
| Native primitive differential mixed | Passed on Linux against 0.6 |
| Deterministic rename evidence gate | Passed; all pages/expansions/schema volumes recorded |
| Dart provider format/analyze/test | Passed: format/analyze and four tests; pinned Analyzer unchanged |
| Android SDK native check | Passed on Linux |
| Profile/failure/recovery and no-Dart smoke | Passed on Linux |
| Linux package relocation/setup | Passed with adjacent TypeScript/Dart/Go assets |
| UIKit/Xcode, macOS, Windows, exact candidate remote CI | Not run; not verified coverage |
| AI pilot, ablation, extended corpus/holdout | Not run; no usage/cost data |

G0 is **not_measured** for the full pilot: product/source/binary/server-schema identities
are verified, but executor/model/oracle/actual prompt-insertion identities are missing.
G1 is **not_measured** for release-wide compatibility: the local Linux regression
subset passes, but required remote/platform coverage is incomplete. G2, G3 and G4
are **not_measured**: accounting/isolation, 18 accepted-task executions and extended
holdout evidence have not been obtained. [Results](results.json) exposes zero model
runs and null comparisons, not zero-token tasks or an achieved target.

## Remaining limits and next experiment

These opt-in features are delivered as engineering hypotheses pending whole-task
validation. Source views cannot promise parser-perfect signatures for providers that
lack boundaries; large scopes/hunks remain bounded with explicit expansion. Review
uses conservative line synchronization, not a language equivalence proof; arbitrary
moves remain added/removed IDs. Historical before IDs/sites/hashes are retained, but
captured historical source text is not separately retrievable. No parameter/ABI/type
compatibility proof is invented. Current graph cache, client retention and provider
prompt caching remain separate.

The server cannot know external reads/compaction. The client adapter matches exact
source windows and reports unidentified text; partial overlaps need additional executor
instrumentation. Index and intent hashing counters have declared scopes; primitive
snippets/lexical verification and exact heap allocations are not an exhaustive I/O/RAM
audit. Registry discovery support, actual schema insertion and monetary pricing still
need real client measurement. The small lexical corpus is insufficient to choose BM25,
embedding or a universal default. Provider persistence, copy-on-write records,
incremental graph indexes and stable asset-fingerprint caching remain deferred.

Register a verified executor/oracle/model/effort and actual prompt schemas/instructions
before launching the frozen pilot. Keep failures/retries/preparation in the accounting.
Inspect per-class costs and use trace-driven, separately frozen ablations. Register
cross-language/framework/repository-size replications and holdout before inspecting
those results. No economic gate is implied by delivering this implementation.
