# Validation of the Rust migration (0.5.0)

Local reference: immutable `v0.4.0`, initially commit `2501034b84fab0ca0c0194d95be74a7660bb8a56`. Both servers use the retained semantic adapters; the comparison checks the new orchestration/storage/query/transport against the old core. Stable IDs, complete fixture searches, architecture/diagnostics, callers, callees, references, implementations, neighbors, dependencies, affected_by_change, blast_radius and snippets are compared for every fixture symbol. Only generation is normalized; initialize version and new metadata are checked separately.

## Local checks (Linux x64, 2026-10-01)

- Rust formatting, Clippy with warnings denied, 28 core/transport/storage/incremental tests.
- Dart provider formatting, analysis with infos denied and three Analyzer tests, including generics/accessors/operators, conditional dependencies and emission with unchanged context.
- Ruff and strict mypy on the retained Python adapters; Go vet on the retained Go adapter.
- Differential native MCP: Dart fixture 37 symbols / 99 edges; polyglot 41 / 108; Python/Rust 32 / 81; mobile 75 / 131; actual Flutter 24 / 75. Mixed ten-language repository: 185 / 419.
- Actual Android SDK classpath: 5 symbols / 6 edges; TypeScript server with no Dart SDK on PATH.
- Relocated native Linux package, including selective provider setup and adjacent-asset discovery, tested in paths containing spaces.
- Release synthetic benchmark: 100,000 symbols / 500,000 relations, repeated queries plus reconciliation, and separate persistence measurements. End-to-end fixture timing includes provider process memory. See docs/benchmarks.

Regression tests cover watcher overflow/loss recovery, duplicate source events, atomic replacement, rename/delete, independent scopes and dependency invalidation, source changes during analysis, concurrent writers, failed provider updates, interrupted SQLite publication, cache corruption at startup/during service, sidecar symlinks, external prepared context edits, Unicode/CRLF snippets, stale source, bounds/timeouts/output overflow, descendant termination, cancellation/duplicate IDs/queue limits, framing, lifecycle and EOF draining. A no-change index reuses its graph and performs no extraction; warm queries between reconciliations perform no full scans.

## Cross-platform acceptance

CI requires core and native semantic/provider smoke checks on Linux, Windows and macOS, Flutter on each host, Android SDK on each host and real UIKit/bridging-header resolution on macOS/Xcode. Package builds and relocation/setup smoke tests cover Linux x64, Windows x64, macOS x64 and ARM64. The workflow uses `v0.4.0` as its compiled oracle and uploads benchmark reports.

Remote CI results must be checked for the exact commit before calling cross-platform acceptance complete. Local Linux checks do not verify UIKit, Windows or macOS. Package preparation does not publish a GitHub release/tag; that remains a separate step after validation.

## Limits

Watcher loss can leave stale data until the 30-second reconciliation. Use an explicit index scan for sensitive work, or watch:false for per-query verification. External artifacts beyond declared/tracked source contexts still need forced indexing after preparation. Provider analysis can read wider semantic context than the records emitted; scope tests guarantee isolated publication, not compiler incremental compilation. Dynamic/runtime and omitted cross-language relationships remain incomplete. The benchmark does not demonstrate token savings, a universal speed ratio or a memory reduction.
