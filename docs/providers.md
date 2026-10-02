# Provider contract

The experimental compact response profile changes presentation only. Providers
receive the same full context and emit-file requests, with unchanged semantic
evidence, IDs and coverage. Health counts never substitute for original records;
complete diagnostics remain accessible through paged MCP status sections.

The Rust core owns root validation, discovery, hashes, cache publication, graph traversal, compact query tables and MCP. The Dart Analyzer provider also runs as a subprocess. All adapters read one UTF-8 JSON object from stdin and write one JSON array to stdout; diagnostics/progress on stderr are bounded by the runner.

Request:

```json
{"root":"/absolute/repository","files":[{"file":"src/Main.java","hash":"sha256"}],"options":{"emit_files":["src/Main.java"],"classpath":["/absolute/dependency.jar"]}}
```

Each array item is a `FileRecord` from `crates/core/src/model.rs`, containing `file`, `hash`, `nodes`, `edges`, `dependencies`, `diagnostics`, and `unresolvedCalls`. File IDs are `file::file`; declaration IDs are `file::qualifiedName#kind`. Java overloads include erased argument types; TypeScript overload signatures are distinguished when necessary. Go receiver methods are contained by their named type. Dart IDs preserve the established format. Python uses lexical class/function scopes with ordinal suffixes for repeated definitions; Rust impl methods include their impl scope to avoid collisions between traits with identical method names.

Nodes carry repository-relative file, one-based start/end lines, source offset/length, optional parent/tags/synthetic. Source offsets follow each compiler's native units (UTF-16 for Dart/TS/Java, byte offsets for Go; code-point offsets for Python and Rust, converted from parser/LSP coordinates); snippets use line windows and do not interchange these offset units. Relations include source/target IDs, kind, source site and `confidence: resolved`. Keep compiler-backed static calls separate from possible implementation relationships. External/unindexed targets are omitted or dropped and counted by the query layer.

Dependencies list repository-relative files and drive invalidation. Diagnostics have severity, code, message and one-based line. A build-excluded file still returns a file node and a coverage diagnostic. An unresolved call must not create a guessed target. Builtins and known external declarations are not repository call targets. Missing external dependencies appear in compiler diagnostics.

Responses are bounded to 64 MiB, stderr to 8 KiB, and subprocess duration to `provider_timeout_seconds`. The core validates exact file coverage, expected hashes and node location bounds, sorts rows/diagnostics, and rejects stale/incoherent source snapshots. On initial indexing, provider failures become explicit `provider_unavailable` file diagnostics. A later failed provider update retains the previous committed generation and returns an error. Tool/asset changes and language dependency configuration participate in cache freshness.

To add a provider, implement compiler-backed extraction, include its source extension in discovery, add configuration/runtime health and fingerprint inputs, add a fixture with same-name decoys and semantic invalidation tests, and require its runtime in CI. Preserve existing MCP tool names and pagination contracts. Cache schema changes must increment the SQLite schema version in `store.rs`.

The language adapters were implemented independently, inspired by [Lordymine/codegraph's architecture](https://github.com/Lordymine/codegraph/blob/main/docs/ARCHITECTURE.md). Its implementation uses scip-typescript and go/packages/VTA; PolyCodeGraph currently uses the TypeScript compiler API directly and static go/types targets. Java is an additional javac-based provider.

Python/Rust use `providers/semantic/index.py --python|--rust`, with isolated UTF-8 Python mode. Request options include `python_search_paths`, `rust_analyzer_path`, `rust_cfg`, `rust_sysroot_src`, `adapter_directory` and the deadline. Python imports are static Jedi lookups; Rust references/calls require HIR definition locations at parsed syntax sites. Neither provider executes indexed application code. Rust build/proc-macro/runnable fields are never passed to the server. Missing/ambiguous targets produce diagnostics/unresolved counts instead of guessed edges.

Mobile adapters use `--swift`, `--objectivec` and `--kotlin` in the isolated Python driver. Swift JSON byte ranges and Clang UTF-8 ranges preserve original line endings; Kotlin UTF-16 IR ranges are converted to code-point offsets. Swift USRs, Clang canonical/override cursors and Kotlin original IR symbol identities are the only binding evidence. Stable qualified IDs never use line/offset coordinates; overloads include compiler-resolved parameter types. Objective-C header contracts remain distinct from connected implementation nodes. Module models are validated data only; missing SDKs/classes appear as explicit compiler diagnostics. Swift protocol witness-method mappings and Swift/ObjC or Kotlin/Java cross-language call edges are omitted. Kotlin IR requires successful frontend resolution; errors retain file nodes and diagnostics rather than stale bindings.

## Context and emission in 0.5

`files` contains context records and hashes. `options.emit_files` is the subset that must be returned; omission preserves legacy all-files emission. Resolve declarations/calls using the full context before filtering records. The core validates exact emission coverage, hashes, source bounds and semantic confidence. Do not drop relationships solely because their target is unchanged. Dart external URI nodes are the explicit exception to repository symbol locations.

## Intent-only metadata (0.7)

FileRecord optionally includes `intent: {symbols, relations, tests, capabilities, ast}`.
Missing metadata defaults empty. Auxiliary declarations and semantic binding relations
do not enter primitive symbol/edge tables. Context is retained even when emit_files
selects only changed records. AST version 1 contains statement boundaries, block/scope
IDs, local/parameter definitions, bound read/write sites, control events, offset_unit
and explicit limitations. The core validates locations/shape before publication.

Dart emits the lossless `pcg-ast-1` row transport: interned scope/definition tables,
uses referencing definition indexes, and fixed-width statement/control rows. It
expands once before validation; corrupt indexes fail. SQLite persists the decoded
metadata in file records without a schema bump. The existing 64 MiB subprocess
limit remains unchanged. SourceKit queries supplement Swift local identities when
available; library discovery resolves PATH executables and the driver runtime
resource path, including Xcode frameworks and Windows SDK DLL directories; PSI source parsing complements Kotlin IR without indexed project plugins.
See [extraction precision](intents.md#extraction-precision); no name matching replaces
compiler binding and no hypothetical dataflow/type compatibility is claimed.
