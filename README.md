# PolyCodeGraph

Semantic code intelligence for **Dart/Flutter, TypeScript, JavaScript, Java, Go, Python, Rust, Swift, Objective-C and Kotlin**, exposed through a compact **Model Context Protocol (MCP)** server for coding agents and AI harnesses.

Index a repository, explore its symbols and dependencies through compact graph queries, assess the impact of a change, and request only the source snippets you need. Relations use compiler-resolved symbols rather than matching names across files. A mixed repository shares one graph and one MCP API; each language keeps its own semantic resolver.

- **Symbols and relations:** classes, mixins, enums, extensions, typedefs, functions, methods, fields, constructors, imports, references, inheritance and overrides.
- **Agent tools:** symbol search, callers/callees, implementations, neighbors, dependencies, architecture summaries and conservative blast radius.
- **Incremental index:** content hashes, transitive invalidation and a persistent repository-local cache.
- **Optional Flutter discovery:** Widget/Screen, Bloc/Cubit, Riverpod providers, repositories, use cases, routes, GetIt registrations and Freezed annotations.
- **Local workflow:** stdio MCP for Codex/Claude Code, CLI commands, YAML/JSON configuration and an adaptable AGENTS.md harness.

No embeddings, LLM API key or database service is required. The server runs with Dart. Additional semantic adapters need their language runtimes; install only the adapters used by your projects.

**Version 0.4.0.** Local stdio transport. Dart Analyzer 13.3.0; Dart SDK 3.11 or later. The package name is `polycodegraph`; the executable and project name are `polycodegraph`.

## Install and run

Clone the repository and install its dependencies:

```sh
git clone https://github.com/RolandDumit/polycodegraph.git
cd polycodegraph
dart pub get
```

Install the runtimes for the languages you use: Node.js 22+ for TypeScript/JavaScript, a full JDK 17+ for Java, Go 1.25+ for Go, and Python 3.11+ for Python/Rust/mobile adapters. Swift analysis requires a native Swift 6.2+ toolchain; Kotlin requires the JDK. Prepare the adapters:

```sh
dart run tool/setup_providers.dart
# Or prepare only the adapter you need (same commands on all three systems):
dart run tool/setup_providers.dart --typescript
dart run tool/setup_providers.dart --go
dart run tool/setup_providers.dart --java
dart run tool/setup_providers.dart --python
dart run tool/setup_providers.dart --rust
dart run tool/setup_providers.dart --swift --objectivec --kotlin
```

Java uses JDK compiler APIs directly and needs no extra library. `setup_providers.dart` prepares all adapters by default; use its flags when you only need some languages. Bash is not required. Python dependencies are installed into an isolated adapter virtual environment with pinned wheel hashes. Rust setup downloads an official rust-analyzer release (2026-09-28), validates SHA-256, and selects the native Linux/macOS/Windows x86_64 or ARM64 binary. It does not require Cargo/rustup or run indexed build scripts.

From the checkout, index a repository and start the MCP server:

```sh
dart run bin/polycodegraph.dart --help
dart run bin/polycodegraph.dart doctor --root /path/to/project
dart run bin/polycodegraph.dart init --root /path/to/project
dart run bin/polycodegraph.dart index --root /path/to/project
dart run bin/polycodegraph.dart status --root /path/to/project
dart run bin/polycodegraph.dart serve --root /path/to/project
```

Prepare the indexed project dependencies yourself: `dart pub get`, `flutter pub get`, the usual Node package setup, or `go mod download`. For Dart/Flutter, this resolves package imports and provides Flutter's SDK/embedder mappings. The server never runs package managers or code generation on your behalf.

Install a local checkout as a CLI (this project has not been published to pub.dev):

```sh
dart pub global activate --source path /absolute/path/to/polycodegraph
polycodegraph index --root /path/to/project
```

Add your pub cache's `bin` directory to `PATH`. To compile and verify a native executable for the current operating system/architecture:

```sh
dart run tool/check.dart --build
```

This builds `build/polycodegraph` on Linux/macOS and `build/polycodegraph.exe` on Windows, and verifies real MCP queries against the compiled server. Run it on Linux/macOS:

```sh
./build/polycodegraph serve --root /path/to/project
```

On Windows (PowerShell):

```powershell
& .\build\polycodegraph.exe serve --root "C:/Projects/My Flutter App"
```

Native binaries and the compiled Go adapter must be built separately for each OS/architecture. The source checkout and `dart run` commands work on all three operating systems.

Keep the `providers/` directory next to the executable or one directory above it (as in `build/polycodegraph`), or set `providers_path` explicitly. A global activation outside the checkout may also need this explicit path. Include its installed TypeScript compiler, built Go adapter, Python adapter environment and native rust-analyzer installation when distributing it. Node/JDK/Go/Python remain runtime prerequisites for their respective adapters. Python virtual environments contain host-specific paths; recreate them on the destination (remove `providers/semantic/.venv` before running setup if the checkout was copied), or configure `python_path` to a prepared native interpreter. Kotlin distribution assets and the graph plugin must also accompany the executable.

The native executable still needs access to a Dart SDK for analysis. Specify `sdk_path` in configuration when SDK auto-detection is unavailable, especially when the executable is moved outside a Dart installation. For Flutter, point it to `flutter/bin/cache/dart-sdk`.

## Operating system support

Linux, macOS and Windows are supported. Development/setup scripts are written in Dart and work in a normal terminal or PowerShell; Bash, WSL and a Unix shell are optional. CI runs Dart/MCP/native-binary checks, mandatory multi-language integration tests and a real Flutter fixture on all three systems.

| Platform | Native server | Go adapter |
| --- | --- | --- |
| Linux | `build/polycodegraph` | `providers/go/graph` |
| macOS | `build/polycodegraph` | `providers/go/graph` |
| Windows | `build/polycodegraph.exe` | `providers/go/graph.exe` |

Use a Dart SDK (or Flutter's bundled Dart SDK) on your host. Install Node.js, a **full JDK**, Go and Python for the languages you need. The adapter setup selects the correct executable suffix automatically and launches native programs directly, including npm through Node, so paths with spaces work. `NODE`, `JAVA`, `GO`, `PYTHON`, `RUST_ANALYZER` and `SWIFTC` select native tooling for setup/checks; Windows `.cmd`, `.bat` and PowerShell launchers are not runtime executables. For custom npm installations, set `NPM_CLI` to `npm-cli.js`.

Graph IDs/globs always use forward slashes, independent of OS. Windows configuration can use `C:/Projects/My App` paths; alternatively use single-quoted YAML/TOML paths or escape backslashes in JSON. Cache files belong to their original repository root and are rebuilt after moving a checkout; do not transfer a native binary, compiled Go adapter, rust-analyzer binary or Python virtual environment between different OS/architectures.

## Configuration

`init` creates `polycodegraph.yaml`, and refuses to overwrite an existing config. The loader also accepts `polycodegraph.yml` or `polycodegraph.json`; `--config path` selects an explicit file. Paths and globs are relative to `--root`; `sdk_path` can be absolute.

```yaml
include:
  - "lib/**/*.dart"
  - "bin/**/*.dart"
  - "test/**/*.dart"
  - "**/*.ts"
  - "**/*.tsx"
  - "**/*.js"
  - "**/*.jsx"
  - "**/*.mjs"
  - "**/*.cjs"
  - "**/*.java"
  - "**/*.go"
  - "**/*.py"
  - "**/*.pyi"
  - "**/*.rs"
  - "**/*.swift"
  - "**/*.kt"
  - "**/*.h"
  - "**/*.m"
  - "**/*.mm"
exclude:
  - "**/.git/**"
  - "**/.dart_tool/**"
  - "**/build/**"
  - "**/.polycodegraph/**"
cache: .polycodegraph
flutter: true
max_results: 200
max_snippet_lines: 120
max_snippet_chars: 16000
max_file_bytes: 2097152
# sdk_path: /opt/flutter/bin/cache/dart-sdk
# providers_path: /absolute/path/to/polycodegraph/providers
node_path: node
java_path: java
go_path: go
# python_path: /absolute/path/to/prepared/python  # otherwise the adapter venv
python_search_paths: []  # extra source roots or dependency site-packages
# rust_analyzer_path: /absolute/path/to/rust-analyzer  # otherwise installed binary
rust_cfg: []  # extra cfg values, e.g. 'feature="offline"'
# rust_sysroot_src: /absolute/path/to/rust/library  # optional std/core source tree
swiftc_path: swiftc
# libclang_path: /absolute/path/to/native/libclang  # optional Xcode/native override
mobile_project_path: polycodegraph.mobile.json  # optional read-only module model
java_classpath: []  # paths to dependency JARs or compiled class directories
provider_timeout_seconds: 120
```

Defaults index repository sources for all ten languages, including generated Dart files. Dependency/artifact directories (`node_modules`, `vendor`, `target`, `dist`, `build`, `.build`, `.gradle`, `DerivedData`, `.tools`, `.venv`, `venv`, `__pycache__`, `.mypy_cache`, `.ruff_cache`, `.pytest_cache`, `.tox`, `.nox`) are skipped internally. Includes/excludes are explicit config globs; `.gitignore` is not interpreted. Codegraph's explicit inclusion rules take precedence over analysis_options source exclusions; Analyzer still uses the project's language and diagnostic options. Keeping generated `.g.dart`/`.freezed.dart` files gives the best resolved graph. Excluding them reduces coverage; changes to excluded Dart sources still invalidate the index. `exclude` replaces the configured list; internal `.git`, `.dart_tool`, `build`, and the cache directory are always omitted from source discovery. `.dart_tool/package_config.json` is still tracked for invalidation. Unknown keys and invalid types fail with a useful error.

Symlinks and sources larger than `max_file_bytes` are omitted and reported under `skipped`. Source reads and cache paths are restricted to the configured repository; symlink paths cannot be read through `snippet`. Dependency edges pointing to an omitted source node are dropped and counted in `dropped_edges`. Configure trusted repositories only.

CLI `status` inspects the existing cache and pending edits without rebuilding. MCP `status` refreshes before returning health. `serve` starts immediately and indexes lazily on the first graph query, allowing initialization on large projects.

## Connect Codex

Use the executable's absolute path. In `~/.codex/config.toml` (or your project's trusted `.codex/config.toml`):

```toml
[mcp_servers.polycodegraph]
command = "/absolute/path/to/polycodegraph/build/polycodegraph"
args = ["serve", "--root", "/absolute/path/to/flutter-project"]
startup_timeout_sec = 20
tool_timeout_sec = 180
```

Alternatively, after local global activation:

```sh
codex mcp add polycodegraph -- polycodegraph serve --root /absolute/path/to/project
```

Use `codex mcp list` to verify registration. The executable must be available in the environment that launches Codex. Model and reasoning effort belong to the host agent settings; this MCP server does not select or invoke an LLM.

On Windows, the same Codex configuration uses the `.exe` path (TOML literal strings preserve backslashes):

```toml
[mcp_servers.polycodegraph]
command = 'C:\Projects\polycodegraph\build\polycodegraph.exe'
args = ['serve', '--root', 'C:\Projects\My Flutter App']
startup_timeout_sec = 20
tool_timeout_sec = 180
```

## Connect Claude Code

```sh
claude mcp add --transport stdio --scope project polycodegraph -- \
  /absolute/path/to/polycodegraph/build/polycodegraph serve \
  --root /absolute/path/to/flutter-project
```

Equivalent `.mcp.json` (on Windows, use `C:/Projects/polycodegraph/build/polycodegraph.exe` and your project root):

```json
{
  "mcpServers": {
    "polycodegraph": {
      "type": "stdio",
      "command": "/absolute/path/to/polycodegraph/build/polycodegraph",
      "args": ["serve", "--root", "/absolute/path/to/flutter-project"]
    }
  }
}
```

Allow the project server in Claude Code and inspect it with `/mcp`. For large repositories, increase the client's MCP tool timeout as needed.

## Language providers

| Language | Semantic engine | Setup and boundaries |
| --- | --- | --- |
| Dart/Flutter | Dart Analyzer 13.3.0 | Existing package configuration and SDK; optional Flutter discovery |
| TypeScript/TSX | Pinned TypeScript compiler API | Reads the nearest tsconfig/jsconfig; resolves aliases, signatures, imports and inheritance |
| JavaScript/JSX/MJS/CJS | TypeScript compiler API | Supports static ES/CommonJS module relationships where the compiler resolves them; typings improve coverage |
| Java | javac Trees / Elements / Types | JDK 17+; configure dependency JARs/classes with `java_classpath`; overload IDs include erased parameter types |
| Go | go/packages + go/types | Go 1.25+ and prepared module/workspace dependencies; static interface methods and implicit structural implementations |
| Python/PYI | Python AST + pinned Jedi 0.20.0 | Python 3.11+; aliases, typed receivers, classes, constructors, methods, fields, properties, async functions and explicit inheritance |
| Rust | rust-analyzer LSP/HIR | Modules, structs, enums, traits, impl blocks, methods, fields, aliases, constants and statically resolved calls; read-only crate model |
| Swift | Swift 6.2+ semantic JSON AST | Compiler USRs for classes/structs, protocols, enums, extensions, aliases, properties, constructors, functions and calls |
| Objective-C/Objective-C++ | libclang canonical cursors | `.h`, `.m`, `.mm`; selectors, categories, properties, protocols, header imports, overrides and static receiver targets |
| Kotlin | Pinned Kotlin K2 2.3.10 resolved IR | `.kt`; classes, interfaces, objects, data/enum classes, extension/suspend functions, overloads, properties, constructors, calls and overrides |

Go loading is read-only and disables module downloads. Java analysis disables annotation processors and does not emit class files. Maven/Gradle build hooks are not executed; provide their resolved classpath. Missing generated sources, unavailable dependencies, unsupported build constraints and compiler errors reduce coverage and appear in diagnostics. Go uses current GOOS/GOARCH/GOFLAGS/build constraints; excluded sources retain a file node and a diagnostic.

`doctor` reports adapter/runtime presence. MCP `status` includes provider health, diagnostic counts and bounded samples (messages capped at 512 characters with explicit truncation); successful presence checks alone do not prove semantic resolution. If an adapter cannot run or times out, its source files receive `provider_unavailable` diagnostics and file nodes; other languages remain queryable. Installing/fixing an adapter invalidates the cached coverage automatically.

Static call targets are used throughout. Go function variables, Java reflection, JavaScript dynamic property access and arbitrary callback flow remain incomplete. An interface call points to its declared method; `implementations` and blast radius expose related implementations conservatively. Go supports structural interfaces without an explicit implements clause. Cross-language RPC/FFI/runtime calls are not inferred from matching names.

### iOS and Android languages

Prepare mobile adapters with a native Swift 6.2+ toolchain, JDK 17+ and Python 3.11+ installed:

```sh
dart run tool/setup_providers.dart --swift --objectivec --kotlin
```

Setup installs SHA-256-pinned libclang wheels, downloads the hash-verified official Kotlin 2.3.10 compiler distribution, and builds this repository's trusted graph plugin. It never runs downloaded shell launchers. The running server does not install tools, invoke Gradle/Xcode/SwiftPM, evaluate `Package.swift` or `.kts`, or load project compiler plugins, KAPT or KSP. Kotlin creates temporary compiler output to obtain resolved IR; it does not execute it. Custom Swift macro plugin paths are not supplied.

The server and portable fixtures work on Linux, macOS and Windows with native toolchains. **Analyzing UIKit/iOS SDK code requires macOS with Xcode and the corresponding SDK.** Android analysis accepts a prepared `android.jar` and dependency JARs on any host. A bridging header can be passed to Swift's importer; graph calls between Swift and Objective-C, or Kotlin and Java, are currently omitted. Framework/dependency declarations remain external to the repository graph.

Without a model, indexed files form one Swift module and one Kotlin module; Objective-C translation units are parsed separately. For multiple targets or platform SDKs, add repository-relative `polycodegraph.mobile.json` (or configure `mobile_project_path`):

```json
{
  "swift": [{
    "name": "App",
    "files": ["ios/App/*.swift"],
    "sdk": "/path/from/xcrun/iphonesimulator.sdk",
    "target": "arm64-apple-ios17.0-simulator",
    "bridging_header": "ios/App/Bridge.h",
    "import_paths": ["prepared/swift-modules"],
    "framework_paths": ["prepared/frameworks"],
    "defines": ["DEBUG"]
  }],
  "objectivec": [{
    "files": ["ios/App/*.h", "ios/App/*.m", "ios/App/*.mm"],
    "sdk": "/path/from/xcrun/iphonesimulator.sdk",
    "target": "arm64-apple-ios17.0-simulator",
    "include_paths": ["ios/App"],
    "framework_paths": ["prepared/frameworks"],
    "arc": true
  }],
  "kotlin": [{
    "name": "AndroidApp",
    "files": ["android/app/src/main/**/*.kt"],
    "classpath": ["/path/to/Android/Sdk/platforms/android-36/android.jar", "prepared/dependency.jar"]
  }]
}
```

Paths may be absolute or relative to the indexed repository. `files` uses slash-separated, case-sensitive glob patterns; `*` also spans directories. Each source belongs to at most one module; unassigned files retain a coverage diagnostic. When a model exists, each used language needs an entry. Unknown keys and executable/plugin/compiler-argument fields are rejected. Generated module/JAR outputs and target dependencies must be prepared separately; dependencies between configured Swift modules use prepared imports, not automatic builds. Default `.h` discovery treats headers as Objective-C; narrow includes/excludes for mixed C/C++ repositories.

For native Apple libclang, set Objective-C module `resource_dir` to the output of `xcrun clang -print-resource-dir` when builtin headers are needed.

Swift JSON AST is a compiler interface without a guaranteed stable format; runtime fingerprints invalidate cached extraction, and unsupported output fails visibly. Static USRs prevent same-name joins; protocol conformances and class overrides are available, but protocol witness-method mappings and runtime callback dispatch are not expanded. Objective-C uses the compiler's declared selector/receiver targets; `id`, forwarding and swizzling do not recover runtime dispatch. Kotlin uses compiler IR identities and explicit override chains; project plugins/generation and cross-platform `expect/actual` compilation are outside this JVM/Android adapter. Diagnostics expose missing modules, SDKs and compiler errors. Mobile model, Xcode/SwiftPM/Gradle configuration, source, provider and runtime edits invalidate indexing; unchanged external SDK/JAR contents require `index --force`.

### Python and Rust setup and precision

For a project using only these two languages:

```sh
dart run tool/setup_providers.dart --python --rust
dart run bin/polycodegraph.dart doctor --root /path/to/project
dart run bin/polycodegraph.dart index --root /path/to/project
```

Python declarations come from the Python AST; references and calls use [Jedi static resolution](https://jedi.readthedocs.io/en/latest/docs/api.html). Repository modules are parsed without importing/executing them. Runtime stdlib and adapter-environment packages are available for inference; use `python_search_paths` for other source roots or project dependency site-packages. Syntax support follows the selected Python runtime. Dynamic/ambiguous callbacks are omitted and counted under `unresolved_calls`. Duck-typed/structural Protocol implementations, monkey-patching and arbitrary decorator/runtime dispatch are not inferred. Explicit bases and resolved overridden methods participate in impact analysis.

Rust uses a [rust-analyzer project model](https://rust-analyzer.github.io/book/non_cargo_based_projects.html) built from indexed Cargo package roots, default local features and indexed path dependencies, including dependency aliases/workspace inheritance. Standalone `.rs` sources can be analyzed as separate crates. `rust_cfg` adds explicit build conditions. External registry/git crates are not downloaded/loaded automatically; they produce coverage diagnostics. To describe prepared external crate sources, provide a root `rust-project.json` with `crates`/`deps`, or set `rust_sysroot_src` for std/core sources. When custom features, targets, generated modules or build environments matter, describe them explicitly in that model; the default manifest reader is intentionally conservative.

[Build scripts and procedural macros](https://rust-analyzer.github.io/book/security.html) are disabled. Cargo, indexed `.cargo/config` wrappers, toolchain overrides, project runnables and proc-macro libraries are not executed. The model discards executable fields. Macro-expanded call graphs remain incomplete and are reported. `implementations` resolves Rust trait impls and overriding methods; calls retain their static HIR targets. Source positions, escaped file URIs, Unicode and Windows CRLF are covered by regression tests.

Edits rebuild the affected Python or Rust language scope; additions/deletions, `pyproject.toml`, requirements/lock files, `Cargo.toml`, `Cargo.lock`, `rust-project.json` and provider/runtime changes invalidate the cache. External dependency/source changes without a changed lock/config require `index --force`.

## MCP tools

All graph queries refresh the index first. `detect_changes` reports pending changes without indexing. A fixed root prevents an agent from changing the repository or reading arbitrary paths through tool arguments.

| Tool | Arguments | Purpose |
| --- | --- | --- |
| `index_repository` | `force?` | Refresh; report changed, deleted and reindexed files |
| `status` | none | Fresh graph health, diagnostics and counts |
| `detect_changes` | none | Pending edits and environment changes |
| `get_architecture` | `limit?` | Counts, tags, directories, relationship kinds and hubs |
| `search_symbol` / `search` | `query`, `kind?`, `tag?`, `file?`, `language?` | Case-insensitive substring symbol discovery |
| `callers` | `target` | Resolved incoming call sites |
| `callees` | `target` | Resolved outgoing call sites |
| `references` | `target` | Resolved incoming identifier/type references |
| `implementations` | `target` | Transitive subtypes or overriding members |
| `dependencies` | `target`, `direction?` | File-level directives and cross-file symbol dependencies |
| `neighbors` | `target`, `direction?`, `kinds?` | Adjacent graph nodes and source sites |
| `affected_by_change` / `blast_radius` | `target`, `depth?` | Conservative reverse closure, with reasons |
| `snippet` | `target?`, `file?`, `start_line?`, `end_line?`, `context?` | Bounded source window |

List-returning tools accept `offset` (default 0) and `limit` (default 50, capped by `max_results`). `get_architecture` defaults to 20 hubs. `search_symbol.file` is a relative path prefix; `kind`/`tag` are exact filters. Filter `language` with `dart`, `typescript`, `javascript`, `java`, `go`, `python`, `rust`, `swift`, `objectivec` or `kotlin`. An empty `query` lists symbols. Search favors exact names, then prefixes, then substrings. A `target` is a returned stable ID, an unambiguous qualified name/name, or an indexed relative file path. Ambiguous names return candidate IDs instead of guessing.

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

## Dart/Flutter accuracy and discovery

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

An edit invalidates the file and transitive dependents from both directives and resolved cross-file references. Additions/deletions conservatively trigger a full rebuild. Changes to pubspecs, analysis options, package configs, excluded source files, SDK/config fingerprints also rebuild. TypeScript/JavaScript changes rebuild the shared TS/JS scope conservatively; Java or Go changes rebuild that language across the root. This avoids stale implicit-package/interface bindings. Configuration/lock files, provider code/runtime changes, Go build environment and configured Java classpath contents participate in invalidation. Each Dart indexing batch creates fresh Analyzer contexts, so reused Analyzer sessions cannot supply stale bindings. A second scan detects concurrent source edits; unstable repositories retry up to three times without publishing a mixed snapshot.

Writers serialize with an in-process queue and an OS advisory lock. Snapshot replacement is atomic on the same filesystem; a crashed writer leaves the previous complete snapshot. Corrupt, incompatible or wrong-root caches rebuild automatically. No daemon/watch service is required: freshness is checked on every query. Keep the cache on a local filesystem that supports locking and atomic rename, and add `.polycodegraph/` to the indexed project's `.gitignore`.

## Suggested AGENTS.md harness integration

Copy the adaptable instructions from [docs/harness-AGENTS.md](docs/harness-AGENTS.md) into each project's harness. The intended loop is:

1. Read `status`/`get_architecture` and check diagnostics once.
2. Find stable symbol IDs with `search_symbol`.
3. Query `callers`, `implementations`, `dependencies` and `blast_radius` before changing an API.
4. Read only relevant `snippet` windows, expanding truncated windows explicitly.
5. Make the change, then call `index_repository` and inspect the updated graph.
6. Run the project's normal `dart analyze`/`flutter analyze` and tests; the graph does not replace them.

## Development harness

[AGENTS.md](AGENTS.md) defines the server's development invariants and agent workflow. [CONTRIBUTING.md](CONTRIBUTING.md) describes setup and the shared validation command, also used by CI. [Fixture contracts](docs/fixture-contracts.md) specify expected semantic edges and negative cases. Consumer harness integration above remains a separate template.

## Tests and fixture

```sh
dart run tool/check.dart
dart run tool/check.dart --providers --build
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

CI runs Dart validation, a required semantic polyglot job (TypeScript, JavaScript, Java, Go, Python and Rust), and a separate real Flutter integration job. `test/fixtures/polyglot/` and `test/fixtures/semantic/` verify static calls, unrelated same-name decoys, overloads, references, implementations, dependencies, impact and semantic cache invalidation. `test/semantic_test.dart` also checks Python callbacks, Rust path dependencies, nonexecution of build hooks, Unicode/CRLF and stale bindings. Combined native MCP tests index all ten languages; the mobile jobs require Swift/Objective-C/Kotlin and Android SDK tests on all three hosts, plus real UIKit/bridging-header analysis on macOS. Add `--dev` to adapter setup to include Ruff formatting/lint and strict mypy in provider checks. Optional language tests skip locally when adapters are unavailable; `--providers` requires them. See [docs/architecture.md](docs/architecture.md) and [docs/protocol.md](docs/protocol.md) for implementation and protocol contracts. See [VALIDATION.md](VALIDATION.md) for the checks performed on this checkout.

## Migration from dart-codegraph

The project, package and executable are now `polycodegraph`; update imports, MCP registration names and commands. The default config is `polycodegraph.yaml` and the cache is `.polycodegraph/`. Old caches are not migrated; rebuild them. The repository rename preserves Git history. Existing Dart symbol IDs are preserved for unchanged source; cache schema 2 invalidates previous snapshots.

## References

- [Lordymine/codegraph architecture](https://github.com/Lordymine/codegraph/blob/main/docs/ARCHITECTURE.md), the inspiration for compact queries and compiler-backed language adapters. The adapters here are implemented independently.
- [TypeScript compiler API](https://github.com/microsoft/TypeScript/wiki/Using-the-Compiler-API), [Go packages](https://pkg.go.dev/golang.org/x/tools/go/packages), and [javac Trees](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/util/Trees.html).
- [Dart Analyzer](https://pub.dev/packages/analyzer) and its [context collection API](https://pub.dev/documentation/analyzer/13.3.0/dart_analysis_analysis_context_collection/AnalysisContextCollection-class.html).
- [Jedi API](https://jedi.readthedocs.io/en/latest/docs/api.html), [rust-analyzer project models](https://rust-analyzer.github.io/book/non_cargo_based_projects.html) and [configuration](https://rust-analyzer.github.io/book/configuration.html).
- MCP [stdio transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports) and [tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).
- [Codex MCP configuration](https://developers.openai.com/codex/mcp/) and [Claude Code MCP](https://code.claude.com/docs/en/mcp).

Released under the [MIT license](LICENSE). No telemetry is implemented by this server.
