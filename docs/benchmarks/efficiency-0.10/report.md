# 0.10 development: first-tranche implementation evidence

Recorded 2026-10-07. Candidate: **0.10.0-dev.1**, working-tree changes based on
v0.9.0 commit `f1e0484cb1ac66f0fe623fc6e8c4531a886b0a07`. T0–T2 are implemented
as optional client integration. **No AI campaign ran; end-to-end token savings
and quality non-inferiority are unmeasured.** This is development evidence, not
a release decision.

The [migration contract](../../migration-0.10.md) specifies activation, bounds,
fallback and rollback. [Deterministic results](deterministic-results.json),
[source/artifact identities](source-manifest.json) and
[execution readiness](readiness.json) accompany this report. The
[preregistered continuation](protocol.md) uses the existing comparison runner;
task/model/executor/oracle/schedule freezes and explicit AI budgets are still
required before launch.

## Implemented scope

- **T0:** bounded, hashed call/result/insertion/outgoing-request correlation;
  source accounting for partial line overlaps, external reads and compaction;
  explicit unknowns on missing identity, truncation or ledger overflow.
  `comparison-v2` selects total provider input plus output per accepted cell,
  retaining uncached input as supporting output and all failed/retried attempts.
  `usage-v2` keeps unavailable cache creation null, including inclusive/disjoint
  stream normalization. The frozen cumulative parser still requires complete
  counters and validates duplicates/resets. Historical revisions remain usable.
- **T1:** static task-start surfaces derived from the canonical catalog. Local
  work exposes zero PCG tools/instructions when applied by a supporting executor.
  Each of ten intent profiles registers canonical `inspect_change` with its own
  typed options; target discovery is explicit. Full/agent specs remain intact.
  A short consumer guide is separate from ordinary repository instructions.
- **T2:** opt-in `pcg-lean-collection-2`, lossless record grouping, full-value
  dictionaries and complete compatible source-window merging. Snapshot, source
  hash, detail and page-inventory conflicts discard the partial collection.
  Every site tuple, offset, occurrence, confidence, phase, provenance, handle and
  precision limit is preserved. The shortest valid representation is selected,
  including collection-1 fallback. Async/native bindings enforce RPC deadlines;
  cancelled or failed insertions never record source as inserted.

The Rust change adds `environment_fingerprint` to lean snapshot identity.
Resolvers, storage, indexing, stable IDs, server full/agent catalogs, audit/lean
defaults and ordinary harness remain unchanged. Packaging ships all seven client
modules together. No indexed application, project plugin, hook or code generator
was executed; adapter preparation compiled only trusted PCG provider workers.

The continuation adds the runnable `efficiency_mcp.py` stdio relay and bounded
async native transport. Ordinary MCP clients can apply a fixed workflow profile,
optional discovery, guide/collection ablations and explicit native cursor
recovery. Full/agent defaults retain the original guide and direct results;
local starts no native process. Metadata is forwarded on every internal page,
and review baselines survive source edits within the same native session.
Responses are prepared, never counted as actual provider insertion. The trusted
benchmark executor launcher now sets the POSIX output limit before executing its
operator-selected program, avoiding a threaded subprocess `preexec_fn` hook.

## Local collection measurements

Native TypeScript compiler fixture, 200 distinct same-line reference offsets,
`edit_context`, 20 sites per page. Both alternatives contain the collection
envelope; the corpus uses empty collector policy metadata, while the fused
alternative also includes the original request. Sizes are Unicode characters of
one compact JSON representation, excluding JSON-RPC framing/text duplication,
schemas, instructions, later reads and model turns. All four semantic inventory
multisets compare equal.

| Intent | Raw pages | Collection-1 | Selected | Source windows before/after | Selected format |
| --- | ---: | ---: | ---: | ---: | --- |
| rename | 11 | 30,637 | 12,418 | 12 / 2 | collection-2 |
| change_signature | 11 | 31,571 | 11,243 | 12 / 2 | collection-2 |
| explain_symbol | 11 | 29,359 | 11,071 | 13 / 3 | collection-2 |
| trace_flow | 1 | 2,254 | 2,254 | 1 / 1 | **collection-1 fallback** |

These are approximately 59–64% smaller serializations for the three multi-page
cases and zero improvement for the small case. They establish representation
equivalence on this fixture, not AI savings. A separate native collector exercise
includes its real budget envelope and insertion observer; its complete boundary
counters are retained in the result artifact. Eleven MCP calls are still required:
fusion reduces the inserted representation, not transport round trips.

Supplemental frozen-page replay retains two larger collections (21 and 11 pages),
their input hashes, all alternatives and equality checks. These pages were
captured during development before the package version bump; the capture binary
identity is unavailable. They support deterministic transformation checks only.
The fresh native corpus above identifies the final candidate binary.

## Static exposure and instruction ablations

Canonical tool array serialized compactly, without the `tools/list` wrapper:
these are the helper's minimal-guide projections, with cursor recovery/discovery
disabled. The ordinary relay adds its explicit cursor and optional discovery;
full/agent default to the original native guide. Actual offered relay catalog
sizes, guide sizes and all seven module hashes are recorded separately in the
workflow preflight result below.

| Surface | Tools | Schema characters | Returned PCG guide characters |
| --- | ---: | ---: | ---: |
| local | 0 | 2 (serialized empty list) | 0 |
| full | 16 | 16,310 | 336 |
| agent | 5 | 9,661 | 336 |
| rename | 1 | 1,763 | 336 |
| change_signature | 1 | 2,231 | 336 |
| review_change | 1 | 2,220 | 336 |

All ten workflow schemas are below half the canonical agent tool-array size in
the deterministic test. The ordinary consumer file is 6,914 characters versus
336 for the returned minimal guide. Schema-only, instruction-only and full
treatment are distinct future ablations; these counts are not additive token
savings. The native full `tools/list` wrapper is 17,620 characters under its
separate serialization recipe; do not mix those size scopes.

The local empty list represents no registered PCG tool, not a two-character
model schema. The relay is explicitly configurable for ordinary MCP clients;
it does not install itself into Codex or a provider executor.
Real schema registration, retained MCP initialization guidance and subsequent
prompt insertion must be observed at each outgoing model request. Native smoke
registration and synthetic async insertion do not establish that boundary.

## Checks actually completed

- `cargo xtask check`: formatting, Clippy with warnings denied, **88 Rust tests**.
  Existing cases cover watcher overflow/reconciliation, notification loss,
  transactional visibility, edits during analysis, old-dependency invalidation,
  independent scopes retaining context, framing/cancellation/EOF draining,
  review baselines and cursor identity/expiry.
- `python -m unittest discover -s tool -p 'test_*.py'`: **67 tests**. New cases
  cover full multiset/source equivalence, CRLF/Unicode, homonyms/phases/provenance,
  limits/truncation/conflicts, ledger overflow/compaction, nullable usage,
  duplicates/resets/failed attempts, revision propagation, static surfaces,
  actual async timeout/cancellation and insertion failure, native deadline/EOF.
  Relay cases include queue overflow, queued/active cancellation, ID reuse,
  malformed UTF-8/JSON recovery, finite numbers/depth, EOF draining, bounded
  forced shutdown and cleanup confined to owned descendants across groups.
  Async insertion callbacks are rejected before RPC; failed synchronous callbacks
  make insertion accounting explicitly incomplete.
- Native `intent_smoke.py --group mixed`, including primitive differential
  comparison against exact 0.6: all **ten providers**, ten intents and ten fused
  workflows per provider; 200 fixture symbols and 438 edges. Providers: Dart,
  Go, Java, JavaScript, Kotlin, Objective-C, Python, Rust, Swift and TypeScript.
- Native post-0.8 regression corpus: all 100 reference sites retained after
  relocation; no false added/removed relations; strict scope typo rejected;
  audit/lean inventory parity; unchanged symbol ID and visible contract source
  change after a signature edit; native collector deadline and reconnect checks.
- Deterministic original rename evidence gate against 0.6: **passed**, on the
  immutable 385-file consumer snapshot. All 19 resolved references and 17
  independent oracle line patterns retained; two intent pages plus one expansion
  versus 13 baseline collection calls. Schema and excluded startup costs remain
  in the receipt. The historical supplementary rename case that missed its
  volume target remains in the [0.9 evidence](../../releases/v0.9.0.md).
- Flutter native fixture: 24 symbols, 75 edges; ten intents and fused workflows.
  Android SDK fixture: five symbols/six edges and resolved repository call.
  **macOS/UIKit SDK check not run on this Linux host; unverified coverage.**
- Native workflow stdio preflight: passed. Rename retains every required site
  and visible source across 21 pages, with discovery and metadata; small
  move/trace collections fall back to collection-1. Review reuses its baseline
  after a source edit. A one-page collector stop exposes its limit and the same
  session resumes at native offset 20 via an explicit cursor. Private receipt
  verification records no model insertion or provider usage. Full/agent preserve
  original guides/direct results; local works without a native executable.
  The [workflow preflight receipt](workflow-preflight.json) records the actually
  offered schemas/guides and exact module identities, with model usage null.
- Native package build and relocated installation smoke: passed. TypeScript
  assets were prepared in the relocated package; compiled Dart/Go were found
  adjacent to the installed binary. Version metadata agrees across manifest,
  CLI and MCP. All seven client modules import in an isolated Python process
  without the workspace on its import path. The installed relay also passes the
  native workflow preflight using its adjacent binary and providers.
- Configured Ruff E/F/I/B/UP checks and formatting pass on all nineteen touched
  Python tools, also including SIM/C4/ISC/PIE/PLW/PLC0414/BLE audits. The earlier
  120 findings in this scope were resolved. This is a passing check for that
  explicit scope, not an all-rule audit of the entire repository.
  No static type-checking run or new workload RSS/p95 measurement is claimed.

Initial native preparation probes failed on stale Dart/Kotlin workers and missing
Swift compatibility/Go runtime setup. Isolated preparation from trusted adapter
sources and existing pinned dependencies resolved those failures; only the
subsequent successful runs count as validation. An initial rename replay used
an incompatible later trace with the 0.6 binary; the passing gate uses the
original immutable 0.6 trace. Failed probes involved zero model calls.

## Remaining release gates

G1 passes within the tested deterministic/native fixture scope. G0 has frozen
source/artifact identities for this implementation, but real executor treatment
application/isolation and version-matched A/B/C/D campaign preparations are
pending. G2-product/G2-mechanism and G3 total task consumption are unmeasured.
Collector bounds/deadlines pass deterministic checks; G4 p95/RSS and real local
task regressions remain unmeasured. G5 independent holdout is not run.

The [earlier executor preflight](../comparison-20261006-01/execution-readiness.md)
already verified credential isolation and real registration without invoking a
model. That result remains valid for its recorded identity. The missing budget
and the new candidate's treatment/campaign freeze are separate requirements;
this report does not reopen the historical isolation failure.

Model input/output, corrective rereads, provider insertion, exact tokenizer and
economic cost are null. Approved campaign, preparation and judge AI runs are
zero. Do not launch screening, infer causal overhead or add T3/T4 from this
report. The next AI step is a separately budgeted wiring smoke after the
[protocol](protocol.md) freezes its remaining inputs.

## Reproduction

Prepare only trusted pinned PCG adapters and a private runtime config. Keep SDK
paths, binaries, dependency caches, receipts and source windows in ignored local
storage. With those inputs available:

```sh
cargo xtask check
python -m unittest discover -s tool -p 'test_*.py'
python tool/intent_smoke.py --binary "$CANDIDATE" --config "$CONFIG" \
  --baseline "$BASELINE_06" --baseline-config "$CONFIG_06" --group mixed
python tool/intent_smoke.py --binary "$CANDIDATE" --config "$CONFIG" --group flutter
python tool/sdk_smoke.py --binary "$CANDIDATE" --config "$CONFIG" --android
python tool/post08_smoke.py --binary "$CANDIDATE" --config "$CONFIG" --output work/native.json
python tool/workflow_smoke.py --binary "$CANDIDATE" --config "$CONFIG" --output work/workflow.json
python tool/efficiency_replay.py --lean-pages "$FROZEN_PAGES" --output work/replay.json
cargo xtask package --providers "$PREPARED_PROVIDERS"
python tool/package_smoke.py
```

The existing `tool/intent_benchmark.py` additionally needs the original archived
consumer source manifest, 0.6 pre-edit trace and independent rename oracle. Those
private inputs are not published here. Run the UIKit command separately on macOS
with Xcode; a skipped host check is not verified coverage.
