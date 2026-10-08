# Architecture

Rust core modules separate configuration, filesystem discovery, semantic providers, index orchestration, SQLite persistence, graph queries and MCP. The Cargo workspace has core, CLI and xtask packages. Existing language engines are retained; Dart Analyzer is a JSON subprocess provider rather than the hosting runtime.

## Index and query lifetime

A repository starts its watcher before reading/indexing cache. A serialized index owner drains bounded events, reconciles hashes periodically and expands semantic scopes/dependency closures. Provider context contains all needed source identities; emit_files identifies records to publish. Resolution may remain wider than the published scope.

SQLite schema 4 reads existing schema 3 caches and stores metadata, records, scopes, symbols, edges, dependencies and diagnostics with source/target/file/name indexes. Each committed update has an independent revision; querying a small revision can avoid loading unchanged records, including when health changes at the same source generation. An advisory file lock protects writers and SQLite transactions publish generations. Reads use a coherent transaction. Corrupt caches are preserved and rebuilt.

An immutable snapshot is shared by node/edge views; numeric positions and incoming/outgoing indexes avoid duplicating complete symbol/edge payloads. Queries reuse these structures for the same generation. Changing a generation reconstructs derived indexes after successful publication. There is no HTTP/distributed service.

## Coverage and boundaries

Dart uses Analyzer; TS/JS compiler API; Java javac; Go go/packages/go/types; Python AST/Jedi; Rust rust-analyzer; Swift JSON AST/USRs; Objective-C libclang; Kotlin K2 IR. Calls require semantic evidence. Naming tags and conservative impact are discovery aids, not runtime guarantees. Existing omissions remain documented in README.

The watcher is an optimization, not infallible change detection: 30-second source/environment hash reconciliation, error/overflow recovery and explicit index scans preserve a recovery path. watch:false scans every query. SDK and external artifact changes outside tracked inputs require forced indexing.

Provider process groups/job objects have deadlines and bounded stdout/stderr. Initial failures create file nodes with coverage diagnostics; failed subsequent updates retain the prior committed generation. Source and context inputs are validated before transactional publication. No indexed project code or build hooks execute.

The response module caches counts/diagnostic identities with each graph, separately
from semantic records. Compact presentation never changes graph coverage or
provider requests. Presentation profile changes are excluded from index identity.
Reconciliation reloads changed persisted diagnostics even when source generation
is unchanged. Detailed MCP pages preserve original diagnostic fields/messages.

## Intent context

The intents module separates typed input, planning, extraction constraints, page
rendering and session state. An additional adjacency index is built once with each
generation for provider intent-only evidence; primitive nodes/edges stay intact.
Plans query one refreshed snapshot without MCP subcalls. Source windows are streamed
and hash-checked, and shrinking pages reuse the same selected source slices.
Opaque bounded cursor/baseline handles have independent TTLs and snapshot identities.
See [the intent contract](intents.md) for budgets and precision.

Relation-specific adjacency buckets are built once per graph. Optional lexical discovery uses bounded source line documents and existing declaration intervals; it creates no semantic edges. Intent planning/rendering, provider invocations and categorized hashing have separate counters. See [0.8 design](efficiency-0.8-design.md) for additive views, source capture and client acknowledgement.

The opt-in [0.10 client integration](migration-0.10.md) separates static workflow
schema projection, bounded insertion accounting, lossless collection fusion and
deadline-aware binding. Its optional packaged stdio relay applies that surface
and collector for ordinary MCP clients, using a separate cancellation-safe native
session and explicit cursor recovery. It consumes canonical MCP pages without changing the
semantic planner or storage. Native lean identity additionally exposes the
provider environment fingerprint. The server does not install a client adapter
or infer model prompt insertion/token usage.

Version 0.10 keeps required intent records independent of explicit source-text
budgets and intent source selection. Lexical discovery uses a bounded, immutable
snapshot-owned scope/config cache with inverted postings; anchor grouping and
binary-term BM25 are opt-in projections/ablations. Task coverage separates local
observed limits from unknown question coverage without overriding global health.
Binding-owned retention references need explicit confirmed model context, reset
on compaction/identity changes and keep a self-contained fallback. The generic
MCP relay cannot observe that context and leaves retention disabled.
