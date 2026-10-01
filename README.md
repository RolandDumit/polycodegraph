# dart-codegraph

Dart/Flutter code intelligence for coding agents and AI harnesses, powered by **Dart Analyzer** and exposed through a **Model Context Protocol (MCP)** server.

Index a repository, explore its symbols and dependencies through compact graph queries, assess the impact of a change, and request only the source snippets you need. Relations use Analyzer's resolved elements rather than matching names across files.

- **Symbols and relations:** classes, mixins, enums, extensions, typedefs, functions, methods, fields, constructors, imports, references, inheritance and overrides.
- **Agent tools:** symbol search, callers/callees, implementations, neighbors, dependencies, architecture summaries and conservative blast radius.
- **Incremental index:** content hashes, transitive invalidation and a persistent repository-local cache.
- **Optional Flutter discovery:** Widget/Screen, Bloc/Cubit, Riverpod providers, repositories, use cases, routes, GetIt registrations and Freezed annotations.
- **Local workflow:** stdio MCP for Codex/Claude Code, CLI commands, YAML/JSON configuration and an adaptable AGENTS.md harness.

No embeddings, LLM API key or database service is required. The server runs with Dart; Flutter projects need their dependencies resolved with the Flutter SDK.

**Version 0.1.0.** Local stdio transport. Dart Analyzer 13.3.0; Dart SDK 3.11 or later. The package name is `dart_codegraph`; the executable and project name are `dart-codegraph`.

## Install and run

Clone the repository and install its dependencies:

```sh
git clone https://github.com/RolandDumit/dart-codegraph.git
cd dart-codegraph
dart pub get
```

From the checkout, index a Dart/Flutter project and start the MCP server:

```sh
dart run bin/dart_codegraph.dart --help
dart run bin/dart_codegraph.dart init --root /path/to/project
dart run bin/dart_codegraph.dart index --root /path/to/project
dart run bin/dart_codegraph.dart status --root /path/to/project
dart run bin/dart_codegraph.dart serve --root /path/to/project
```

For the project being indexed, run `dart pub get` first, or `flutter pub get` for Flutter. This resolves package imports and provides Flutter's SDK/embedder mappings. The server never runs package managers or code generation on your behalf.

Install a local checkout as a CLI (this project has not been published to pub.dev):

```sh
dart pub global activate --source path /absolute/path/to/dart-codegraph
dart-codegraph index --root /path/to/project
```

Add your pub cache's `bin` directory to `PATH`. For a standalone native executable on the current operating system/architecture:

```sh
mkdir -p build
dart compile exe bin/dart_codegraph.dart -o build/dart-codegraph
./build/dart-codegraph serve --root /path/to/project
```

The native executable still needs access to a Dart SDK for analysis. Specify `sdk_path` in configuration when SDK auto-detection is unavailable, especially when the executable is moved outside a Dart installation. For Flutter, point it to `flutter/bin/cache/dart-sdk`.

## Configuration

`init` creates `dart-codegraph.yaml`, and refuses to overwrite an existing config. The loader also accepts `dart-codegraph.yml` or `dart-codegraph.json`; `--config path` selects an explicit file. Paths and globs are relative to `--root`; `sdk_path` can be absolute.

```yaml
include:
  - "lib/**/*.dart"
  - "bin/**/*.dart"
  - "test/**/*.dart"
exclude:
  - "**/.git/**"
  - "**/.dart_tool/**"
  - "**/build/**"
  - "**/.dart-codegraph/**"
cache: .dart-codegraph
flutter: true
max_results: 200
max_snippet_lines: 120
max_snippet_chars: 16000
max_file_bytes: 2097152
# sdk_path: /opt/flutter/bin/cache/dart-sdk
```

Defaults index all repository Dart files, including generated sources. Codegraph's explicit inclusion rules take precedence over analysis_options source exclusions; Analyzer still uses the project's language and diagnostic options. Keeping generated `.g.dart`/`.freezed.dart` files gives the best resolved graph. Excluding them reduces coverage; changes to excluded Dart sources still invalidate the index. `exclude` replaces the configured list; internal `.git`, `.dart_tool`, `build`, and the cache directory are always omitted from source discovery. `.dart_tool/package_config.json` is still tracked for invalidation. Unknown keys and invalid types fail with a useful error.

Symlinks and sources larger than `max_file_bytes` are omitted and reported under `skipped`. Source reads and cache paths are restricted to the configured repository; symlink paths cannot be read through `snippet`. Dependency edges pointing to an omitted source node are dropped and counted in `dropped_edges`. Configure trusted repositories only.

CLI `status` inspects the existing cache and pending edits without rebuilding. MCP `status` refreshes before returning health. `serve` starts immediately and indexes lazily on the first graph query, allowing initialization on large projects.

## Connect Codex

Use the executable's absolute path. In `~/.codex/config.toml` (or your project's trusted `.codex/config.toml`):

```toml
[mcp_servers.dart_codegraph]
command = "/absolute/path/to/dart-codegraph/build/dart-codegraph"
args = ["serve", "--root", "/absolute/path/to/flutter-project"]
startup_timeout_sec = 20
tool_timeout_sec = 180
```

Alternatively, after local global activation:

```sh
codex mcp add dart_codegraph -- dart-codegraph serve --root /absolute/path/to/project
```

Use `codex mcp list` to verify registration. The executable must be available in the environment that launches Codex. Model and reasoning effort belong to the host agent settings; this MCP server does not select or invoke an LLM.

## Connect Claude Code

```sh
claude mcp add --transport stdio --scope project dart-codegraph -- \
  /absolute/path/to/dart-codegraph/build/dart-codegraph serve \
  --root /absolute/path/to/flutter-project
```

Equivalent `.mcp.json`:

```json
{
  "mcpServers": {
    "dart-codegraph": {
      "type": "stdio",
      "command": "/absolute/path/to/dart-codegraph/build/dart-codegraph",
      "args": ["serve", "--root", "/absolute/path/to/flutter-project"]
    }
  }
}
```

Allow the project server in Claude Code and inspect it with `/mcp`. For large repositories, increase the client's MCP tool timeout as needed.

## MCP tools

All graph queries refresh the index first. `detect_changes` reports pending changes without indexing. A fixed root prevents an agent from changing the repository or reading arbitrary paths through tool arguments.

| Tool | Arguments | Purpose |
| --- | --- | --- |
| `index_repository` | `force?` | Refresh; report changed, deleted and reindexed files |
| `status` | none | Fresh graph health, diagnostics and counts |
| `detect_changes` | none | Pending edits and environment changes |
| `get_architecture` | `limit?` | Counts, tags, directories, relationship kinds and hubs |
| `search_symbol` / `search` | `query`, `kind?`, `tag?`, `file?` | Case-insensitive substring symbol discovery |
| `callers` | `target` | Resolved incoming call sites |
| `callees` | `target` | Resolved outgoing call sites |
| `references` | `target` | Resolved incoming identifier/type references |
| `implementations` | `target` | Transitive subtypes or overriding members |
| `dependencies` | `target`, `direction?` | File-level directives and cross-file symbol dependencies |
| `neighbors` | `target`, `direction?`, `kinds?` | Adjacent graph nodes and source sites |
| `affected_by_change` / `blast_radius` | `target`, `depth?` | Conservative reverse closure, with reasons |
| `snippet` | `target?`, `file?`, `start_line?`, `end_line?`, `context?` | Bounded source window |

List-returning tools accept `offset` (default 0) and `limit` (default 50, capped by `max_results`). `get_architecture` defaults to 20 hubs. `search_symbol.file` is a relative path prefix; `kind`/`tag` are exact filters. An empty `query` lists symbols. Search favors exact names, then prefixes, then substrings. A `target` is a returned stable ID, an unambiguous qualified name/name, or an indexed relative file path. Ambiguous names return candidate IDs instead of guessing.

`direction` is `in`, `out`, or `both`; defaults are `out` for dependencies and `both` for neighbors. `depth` defaults to 6 and supports 1–32. `snippet` needs `target` or `file`; the default window is the symbol's extent (or one line for a file-only request), plus two context lines. Lines are one-based; source is capped by line and character budgets. Inspect `truncated` before assuming you have a complete function.

Examples using the included Dart fixture:

```json
{"name":"get_architecture","arguments":{}}
{"name":"search_symbol","arguments":{"query":"UserRepository","kind":"class"}}
{"name":"callers","arguments":{"target":"lib/domain.dart::UserRepository.fetch#method"}}
{"name":"implementations","arguments":{"target":"UserRepository"}}
{"name":"blast_radius","arguments":{"target":"UserRepository.fetch","depth":12,"limit":20}}
{"name":"neighbors","arguments":{"target":"MemoryRepository","direction":"out","kinds":["extends","with","contains"]}}
{"name":"snippet","arguments":{"target":"LoadUserUseCase.call","context":1}}
```

The protocol returns one text content block containing compact JSON and an equivalent `structuredContent` object for clients that support it. Source is returned only by `snippet`. Tables use a single column header and arrays of rows:

```json
{
  "generation": "<snapshot-hash>",
  "columns": ["id", "kind", "name", "file", "line", "tags"],
  "rows": [["lib/domain.dart::UserRepository#class", "class", "UserRepository", "lib/domain.dart", 3, ["Repository"]]],
  "total": 1,
  "offset": 0,
  "next_offset": null
}
```

Relationship rows add `relation`, `direction`, `site_file`, `site_line` and `confidence`. Call/reference confidence is `resolved`. Impact rows add `distance`, `via` and `reason`. Impact results include `conservative`, `depth_limited`, and `affected_files` for the explored closure. Architecture directories/skipped lists, change-report lists and affected-file summaries are capped at `max_results`, with accompanying `*_total` counts; CLI index reports retain full lists. Page through `next_offset` while the generation remains unchanged; restart pagination if the generation changes. The snapshot hash is deterministic for a fixed root, SDK, configuration and repository state.

## Accuracy and Flutter discovery

Declarations include classes, mixins, enhanced enums/constants, named and unnamed extensions, extension types, typedefs, top-level and named local functions, methods/operators, getters/setters, fields, variables and constructors. Implicit default constructors are represented with `synthetic: true`. Stable IDs use relative source file, qualified name and kind. Editing lines preserves IDs; renaming or moving a symbol changes them. Unnamed extensions/local scopes use source offsets where Analyzer exposes no name, so those IDs may change after preceding edits.

Edges include containment, import/export/part/part-of, extends/implements/with/on constraints, resolved references, calls (including constructors, getters and operators), overriding methods, and recognizable GetIt registrations. Conditional directive alternatives are retained as conservative file dependencies where their URIs resolve.

Calls use Analyzer's **static target**. A call through an interface points to the interface method. `implementations` exposes possible overriding declarations, including abstract members. Impact traversal follows overriding members back to their dispatch contracts, so interface callers are conservatively affected by implementation changes. It also expands members of affected types/files and traverses importers. A depth-limited or diagnostically incomplete graph is not proof that other code is unaffected.

Dynamic receivers, reflection, runtime DI lookup, arbitrary callback flow, anonymous closures, generated code not present on disk, native/plugin dispatch and runtime router behavior cannot be recovered completely. Calls in anonymous closures are attributed to the nearest indexed enclosing declaration. Callback variables do not create guessed call edges. `unresolved_calls`, Analyzer diagnostics, `skipped` and `dropped_edges` expose coverage limits. Only repository symbols are indexed; external SDK/package symbols are not expanded, while imported external URIs remain file dependency nodes.

With `flutter: true`, optional tags include:

| Tag | Recognition |
| --- | --- |
| `Widget` | Resolved Flutter Widget ancestry |
| `Screen` | Widget whose name ends in Screen, Page or View |
| `Bloc` / `Cubit` | Resolved package ancestry |
| `Provider` | Riverpod constructor/ancestry or `@riverpod` annotation |
| `Repository` / `UseCase` | Type name conventions |
| `Route` | Route/Router type names or go_router route construction |
| `GetItRegistration` | Resolved get_it `register*` invocation; typed registrations create `registers` edges |
| `Freezed` | `@freezed` / `@unfreezed` annotation |

Tags are discovery hints. Annotation and naming hints do not certify framework ownership, and no relation is inferred merely from a suffix. Unresolved annotations can still provide hints; diagnostics indicate the incomplete package resolution. This is an API inspired by [Lordymine/codegraph](https://github.com/Lordymine/codegraph), not a drop-in replacement for its schemas.

## Cache and incremental indexing

The repository-local cache stores per-file hashes, declarations, edges, dependencies and diagnostics in an atomic JSON snapshot. SHA-256 content hashes detect edits even when timestamps/sizes are unchanged. A warm unchanged query reuses extraction results, but still scans/hashes source files: freshness checking is O(source bytes), not constant time. Graph adjacency is reconstructed in memory for each tool query; this release favors simple inspectable storage over database-scale indexing.

An edit invalidates the file and transitive dependents from both directives and resolved cross-file references. Additions/deletions conservatively trigger a full rebuild. Changes to pubspecs, analysis options, package configs, excluded source files, SDK/config fingerprints also rebuild. Each indexing batch creates fresh Analyzer contexts, so reused Analyzer sessions cannot supply stale bindings. A second scan detects concurrent source edits; unstable repositories retry up to three times without publishing a mixed snapshot.

Writers serialize with an in-process queue and an OS advisory lock. Snapshot replacement is atomic on the same filesystem; a crashed writer leaves the previous complete snapshot. Corrupt, incompatible or wrong-root caches rebuild automatically. No daemon/watch service is required: freshness is checked on every query. Keep the cache on a local filesystem that supports locking and atomic rename, and add `.dart-codegraph/` to the indexed project's `.gitignore`.

## Suggested AGENTS.md harness integration

Copy the adaptable instructions from [docs/harness-AGENTS.md](docs/harness-AGENTS.md) into each project's harness. The intended loop is:

1. Read `status`/`get_architecture` and check diagnostics once.
2. Find stable symbol IDs with `search_symbol`.
3. Query `callers`, `implementations`, `dependencies` and `blast_radius` before changing an API.
4. Read only relevant `snippet` windows, expanding truncated windows explicitly.
5. Make the change, then call `index_repository` and inspect the updated graph.
6. Run the project's normal `dart analyze`/`flutter analyze` and tests; the graph does not replace them.

## Tests and fixture

```sh
dart format --output=none --set-exit-if-changed bin lib test
dart analyze
dart test
```

The default suite covers symbol extraction, parts, same-name disambiguation, calls, overrides, conservative impact, pagination, snippets, cache reuse/invalidation/recovery, concurrent writers, config/path validation and a real stdio subprocess. Tests copy the Dart fixture to temporary directories before edits.

Enable the real Flutter package integration test:

```sh
cd examples/flutter_fixture
flutter pub get
cd ../..
dart test test/flutter_fixture_test.dart
```

That test verifies actual Flutter, flutter_bloc, flutter_riverpod, GetIt, go_router and Freezed annotations, plus impact propagation into the screen file. It skips explicitly when the fixture's package config is absent. The fixture is a small runnable Flutter entry point; platform scaffolding is intentionally omitted. Freezed recognition is tested via annotations; build_runner generation is not required by the fixture.

CI runs Dart tests and a separate Flutter integration job. See [docs/architecture.md](docs/architecture.md) and [docs/protocol.md](docs/protocol.md) for implementation and protocol contracts. See [VALIDATION.md](VALIDATION.md) for the checks performed on this checkout.

## References

- [Dart Analyzer](https://pub.dev/packages/analyzer) and its [context collection API](https://pub.dev/documentation/analyzer/13.3.0/dart_analysis_analysis_context_collection/AnalysisContextCollection-class.html).
- MCP [stdio transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports) and [tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).
- [Codex MCP configuration](https://developers.openai.com/codex/mcp/) and [Claude Code MCP](https://code.claude.com/docs/en/mcp).

Released under the [MIT license](LICENSE). No telemetry is implemented by this server.
