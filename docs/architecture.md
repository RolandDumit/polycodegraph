# Architecture

`bin/dart_codegraph.dart` dispatches CLI commands. `GraphConfig` validates repository-scoped config and paths. `RepositoryIndexer` discovers source files, computes content/environment hashes, expands invalidation through cached file dependencies, and asks public Analyzer APIs for resolved compilation units. The analysis layer traverses declarations and resolved syntax; element identities normalize generic substitutions and synthetic variable accessors. It builds per-file records independent of query formatting.

`IndexStore` serializes a schema-versioned JSON snapshot under an advisory lock, using flushed temporary files and atomic rename. The indexer serializes same-process writers too. Cache fingerprints bind a snapshot to the root, Dart runtime/SDK configuration, Analyzer version and graph-affecting options. A second source/environment scan before publication prevents mixed source revisions. Unchanged per-file records survive incremental updates; additions/deletions and environment changes rebuild conservatively.

`GraphQuery` assembles symbol maps and bidirectional adjacency. Edges whose endpoints are not indexed are dropped and counted. Compact table results are sorted deterministically and paginated. Impact traversal uses reverse reference/call/type/directive relationships, member/container expansion, and outgoing override edges to include callers of dispatch contracts. Each returned node has a predecessor/reason and distance. Graph queries report the snapshot generation to let agents detect pagination drift.

`ToolRegistry` owns discoverable MCP schemas and argument validation. `McpServer` handles released MCP initialization, tools, ping and stdio framing. Transport parsing is bounded separately from source/snippet limits. MCP tools cannot choose another repository. The server does not execute repository programs or package scripts.

## Module layout

- `lib/src/analysis/`: resolved AST extraction, symbol identities, optional Flutter discovery.
- `lib/src/index/`: scanning, incremental invalidation, coherent snapshot publication, persistence.
- `lib/src/graph/`: serializable records and bounded graph/source queries.
- `lib/src/mcp/`: tool schemas, dispatcher and JSON-RPC stdio transport.
- `test/fixtures/dart_app/`: small independent Dart package with type/call/part examples.
- `examples/flutter_fixture/`: real package-backed Flutter application source.

## Operational limits

All snapshots and queries fit in process memory. Cold analysis and source hashing grow with repository size. Snapshots use JSON for portability, with no SQLite/FTS dependency. There is no watcher, HTTP transport, distributed locking, historical index store or embedding search. Multiple client processes can share a cache on a local filesystem. Advisory locks coordinate cooperating instances; the server does not claim isolation from arbitrary external cache writers.

Static resolution cannot model all runtime behavior. Unresolved calls and Analyzer diagnostics are retained; Flutter naming/annotation tags are optional hints. External package source changes without a changed pubspec/package config require `index --force` (for example, editing a path dependency outside the root). Put related packages under one indexed workspace root to track their sources automatically.
