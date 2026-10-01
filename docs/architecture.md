# Architecture

Rust core modules separate configuration, filesystem discovery, semantic providers, index orchestration, SQLite persistence, graph queries and MCP. The Cargo workspace has core, CLI and xtask packages. Existing language engines are retained; Dart Analyzer is a JSON subprocess provider rather than the hosting runtime.

## Index and query lifetime

A repository starts its watcher before reading/indexing cache. A serialized index owner drains bounded events, reconciles hashes periodically and expands semantic scopes/dependency closures. Provider context contains all needed source identities; emit_files identifies records to publish. Resolution may remain wider than the published scope.

SQLite schema 3 stores metadata, records, scopes, symbols, edges, dependencies and diagnostics with source/target/name indexes. An advisory file lock protects writers and SQLite transactions publish generations. Reads use a coherent transaction. Corrupt caches are preserved and rebuilt.

An immutable snapshot is shared by node/edge views; numeric positions and incoming/outgoing indexes avoid duplicating complete symbol/edge payloads. Queries reuse these structures for the same generation. Changing a generation reconstructs derived indexes after successful publication. There is no HTTP/distributed service.

## Coverage and boundaries

Dart uses Analyzer; TS/JS compiler API; Java javac; Go go/packages/go/types; Python AST/Jedi; Rust rust-analyzer; Swift JSON AST/USRs; Objective-C libclang; Kotlin K2 IR. Calls require semantic evidence. Naming tags and conservative impact are discovery aids, not runtime guarantees. Existing omissions remain documented in README.

The watcher is an optimization, not infallible change detection: 30-second source/environment hash reconciliation, error/overflow recovery and explicit index scans preserve a recovery path. watch:false scans every query. SDK and external artifact changes outside tracked inputs require forced indexing.

Provider process groups/job objects have deadlines and bounded stdout/stderr. Initial failures create file nodes with coverage diagnostics; failed subsequent updates retain the prior committed generation. Source and context inputs are validated before transactional publication. No indexed project code or build hooks execute.
