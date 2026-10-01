# Architecture

PolyCodeGraph keeps one Dart CLI/MCP/query/index core and independent semantic adapters. Language discovery uses explicit repository include/exclude globs. `languageFor` distinguishes Dart, TypeScript/TSX, JavaScript/JSX/MJS/CJS, Java and Go. Matching names never create cross-language call edges.

## Semantic providers

- `lib/src/analysis/`: the Dart Analyzer provider, using resolved compilation units and canonical elements. Optional Flutter tags remain in this layer.
- `providers/typescript/`: a pinned TypeScript compiler API adapter. It discovers nearest tsconfig/jsconfig scopes, creates compiler Programs, indexes declarations, and resolves references, signatures, heritage, overrides and static modules. TS/JS share compiler scopes.
- `providers/java/Graph.java`: a dependency-free JDK source launcher using javac Trees, Elements and Types. It parses/analyzes the indexed Java units together, with configured classpath, disabled annotation processors and no emission. Erased parameter types disambiguate overloaded member IDs.
- `providers/go/`: a built adapter using go/packages and go/types. It discovers module scopes, honors build constraints, resolves identifier/selection targets and infers structural interface implementations with types.Implements. Calls remain static targets; function-variable and runtime callback flow are not expanded. Go module loading is read-only and disables network downloads.
- `lib/src/providers/`: subprocess orchestration, deadlines, output limits, runtime/asset fingerprints and per-file diagnostic fallback. Helpers are invoked as argument lists. Their stdout is internal JSON, never forwarded directly to MCP stdout.

The shared [provider contract](providers.md) uses the existing graph records. Provider results must cover every requested file exactly once, with expected hashes and repository-local symbol locations. Failed/unavailable adapters retain source file nodes with explicit error diagnostics; they cannot make successful language coverage look complete. `doctor` reports runtime/asset presence; `status` exposes coverage and diagnostic samples.

## Indexing and persistence

`RepositoryIndexer` discovers source files, computes source and build-environment hashes, and expands invalidation. Dart changes traverse cached file dependencies. A TS or JS change rebuilds the shared TS/JS language scope across the root; Java and Go rebuild their corresponding language across the root. This deliberately conservative first implementation handles implicit package membership and structural contracts. More granular project/module scope reuse is a future optimization and must preserve the semantic invalidation tests.

Additions/deletions, build manifests/lock/config files, excluded source changes and provider runtime/asset changes trigger a full rebuild. The fingerprint includes configured Java classpath content and Go build environment. Changes to external Dart path dependencies, Go module-cache contents or Node dependencies without a changed lock/config require `index --force`; related editable packages should live under the indexed root. Config changes and incompatible schemas also rebuild.

Fresh Analyzer contexts and compiler Programs prevent stale bindings. A second source/environment scan before publication rejects mixed source revisions, retrying up to three times. `IndexStore` stores a schema-2 JSON snapshot with flushed temporary writes and atomic replacement under an OS advisory lock. Same-process queues serialize writers too. Failed publication leaves the previous snapshot intact. A unavailable provider publishes an explicitly incomplete snapshot, rather than silently retaining stale symbols from that language.

## Graph and protocol

`GraphQuery` assembles symbol maps and sorted bidirectional adjacency. Edges whose endpoints are not indexed are dropped and counted. Compact tables are deterministically sorted and paginated. Impact traversal follows reverse call/reference/type/module edges, expands type members and follows overrides back to dispatch contracts. Every result reports a predecessor/reason and distance; bounded depth and incomplete diagnostics remain visible. Snippets check source hashes and obey line/character budgets.

`ToolRegistry` owns strict MCP schemas and dispatch. `McpServer` handles initialization, tools, ping and bounded newline JSON-RPC stdio framing. Source and subprocess budgets are separate from MCP transport limits. Tools cannot switch repository roots. MCP stdout contains only protocol messages. See [protocol.md](protocol.md).

## Development harness

[../AGENTS.md](../AGENTS.md) is the development contract. [../CONTRIBUTING.md](../CONTRIBUTING.md) and the shared `tool/check.dart` connect local checks to the same CI paths. [fixture-contracts.md](fixture-contracts.md) documents meaningful positive/negative semantic cases. `harness-AGENTS.md` remains the adaptable consumer template.

## Operational limits

Snapshots and queries fit in process memory. Cold analysis and hashing grow with repository size; classpath hashing also reads configured JAR/class content. Adapters have a configurable deadline and 64 MiB response cap; failure is visible as reduced coverage. JSON storage and adjacency rebuilding favor inspectability over database-scale throughput. There is no watcher, HTTP transport, distributed locking, historical store or embedding search. Cooperating processes can share a local filesystem cache that supports locking and atomic rename.

Static resolution cannot fully model dynamic dispatch, reflection, missing generated code, callback flow, cross-language RPC or FFI. External SDK/package symbols are not expanded into the repository graph. Optional Flutter naming/annotation tags are discovery hints. No production-scale token or performance benchmark is claimed.
