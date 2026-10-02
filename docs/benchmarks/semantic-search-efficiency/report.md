# Semantic-search efficiency: 0.6 candidate

2026-10-02, Linux x64. Implementation/deterministic verification completed;
**primary AI-token acceptance is not measured**. Compact remains opt-in. The
six fresh executor runs are pending, not replaced by this response replay.

## What changed

Compact status/index reports retain freshness, generation, coverage, graph counts,
provider availability, diagnostic severity counts and update totals. Detailed
diagnostics (including unknown fields/full messages), skipped files, update lists,
provider runtime details and metrics can be requested over MCP. Legacy is still
default and per-call `detail: full` restores it. Defaults are search 10, relations
20 and implicit snippets 30 lines; explicit limits/depth/windows are preserved.

File filters are validated against indexed root-relative prefixes. A valid empty
match differs from an invalid prefix; a unique correction is suggested but never
applied. Diagnostic/coverage health identity can change without source generation.
Effective graph configuration hashing prevents repeated extraction for profile
or formatting edits. A 0.5 cache can rebuild once on first reconciliation. A
configuration edit during analysis aborts publication, retaining the prior index.

The consumer template reduces unnecessary status checks and repetition of
inspect sections while preserving explicit sensitive scans and post-edit indexing.
The optional [Flutter harness patch](../../harness-integration.patch) edits only
its graph card; it is prepared/checkable, **not applied** to the primary Flutter
checkout. No adapter/normalizer layer is needed. Duplicate/overlap session tracking
is deferred: most relation calls in these traces have different targets or kinds,
and indexing across source changes is not a duplicate just because arguments match.

## Response measurement

Original broker traces store arguments/sizes, not response bodies. We replayed
their real MCP calls and recorded edits on freshly restored copies of the
**original unrenamed** snapshot. Its 385 source hashes were verified before and
after replay. The primary Flutter checkout and old renamed copies were not used
as baselines or modified. Baseline code is release commit
`45fa910bde4cd98c19140b2d81ae850bea06a97c`; both cores were built release/locked
with Rust 1.99.0 into separate targets. Prepared provider assets were reused.

Each measurement counts one broker-consumed JSON object, matching its observed
formatting (JSON spaces and newline). It does not add text and structuredContent.
The exact requested limits/depth, call count and edits are unchanged. No execution
of indexed project code, provider installation or model invocation is part of replay.
Legacy timing fields may vary slightly in serialized size.

| Replay | Legacy bytes | Compact bytes | Reduction |
|---|---:|---:|---:|
| with1, 13 calls | 55,709 | 30,662 | 44.96% |
| with2, 11 calls | 51,212 | 25,160 | 50.87% |

`status` volume falls about 85.3%; combined index reports fall 88.1% and 92.0%.
Search and relation responses **grow** because coverage/health and omission
metadata remain explicit, and the wrong-root prefix gains an actionable warning.
Unchanged indexing also grows from a tiny legacy report to a health summary;
the large benefit is replacing the post-edit file-list dump. The first replay
has three index calls (one pre-edit, one update, one unchanged post-edit); the
second has two (update and unchanged). These costs remain in the totals.

The tools-list JSON representation grows from 8,945 to 10,278 bytes (+14.9%).
Client schema/context overhead is not hidden or treated as a response saving.
These bytes cannot be translated into whole-task tokens or subscription allowance.

Comparison preserved original fields, stable IDs, rows, distinct reference sites,
confidence, totals, pagination, conservative depth and omissions. Generation was
normalized between versions because configuration hashing changed; each individual
response was checked for a single coherent generation. [Aggregated measurements
and build/source identities](response-volume.json) contain no machine paths,
raw responses, source copies or unrelated conversation content.

## Verification

- `cargo xtask check`: format, Clippy with warnings denied, **39 Rust tests passed**.
  Includes watcher overflow/loss/fallback, atomic source changes, scope boundaries,
  writer publication failures, config races, same-generation diagnostic updates,
  profile reload, all omitted detail pages and explicit-limit/full-mode parity.
- Four Python accounting tests passed: counter duplication/reset, disagreement,
  subset accounting and the six-run gate. The extractor also reproduced all four
  existing Presenza rollout totals using only token/model metadata; no rollouts
  or messages were copied into this repository.
- Real stdio profile smoke passed: compact/full, unchanged reconciliation,
  error handling, provider failure details, prefix validation and per-tool metrics.
- Native differential vs 0.5 passed for ten languages together: 185 symbols,
  419 edges; Dart fixture 37/99; real Flutter fixture 24/75. Native query tests
  cover every fixture symbol, relationships, snippets, inspection and post-edit
  updates; runtime timing/freshness metadata are not compared as semantic fields.
- Android SDK smoke passed (5 symbols/6 edges). TypeScript worked without Dart
  on PATH. No semantic resolver changes or new provider installations were made.
- Original Flutter harness check/policy passed with ten pre-existing drift
  warnings; baseline was not reset. Consumer patch applies cleanly. Git whitespace
  checks passed. No Flutter application edits, commits, pushes or version bump.

Windows/macOS execution and UIKit are **not verified in this local Linux run**.
The existing platform CI includes the new profile/accounting tests, but has not
run for this uncommitted candidate. The six new AI executor patches and their
7-file/21-occurrence, 9-regression/2-data-test validator are **not executed** here.
The original experiment's validation results are not claimed as fresh coverage.

## Remaining acceptance

The response reduction gate is meaningful and semantic checks pass. It does not
prove the requested >=20% reduction in uncached input versus no graph, or the
<=5% cached/output limits. A restricted fresh-executor environment with matching
tool surface and per-run counters has not been established in this session.
The [frozen six-run protocol](protocol.md) and usage extractor are ready; no
candidate token results exist. The overall plan remains open, with primary
outcome **not measurable in this delivery**, rather than declared complete.

Activate using a separate candidate executable plus `response_profile: compact`
or `serve --response-profile compact`, then restart MCP in the client. Roll back
the executable/profile and restart. See [contract/rollback](../../response-profiles.md).
Official 0.5 binaries/launchers remain unchanged; candidate binaries still report
package version 0.5.0 and are identified by the recorded build digest.

## Release publication

These measurements describe the pre-version-bump candidate and its recorded build
digests. Version 0.6.0 publishes that implementation with release metadata updates.
The six-run AI token gate remains pending and compact remains opt-in. Local release
checks and platform package validation are recorded in the GitHub release and its
Actions run; they do not replace the pending AI experiment.
