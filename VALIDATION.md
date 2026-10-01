# Validation record

Verified locally on 2026-10-01 from the final checkout at `~/Projects/Personal/polycodegraph`, Linux x86_64, Dart 3.13.2 / Flutter 3.47.2, Node 26.7.0 / TypeScript 6.0.2, Go 1.27.1 and OpenJDK 25.0.3. Java adapter compilation was also checked with `--release 17`.

| Check | Result |
| --- | --- |
| Root and Flutter fixture dependency resolution with enforced lockfiles | Passed |
| `tool/setup-providers.sh` (pinned TS install, Go module verification/build) | Passed |
| `tool/check.sh --providers --flutter --build` | Passed: formatting, static analysis, **33 tests with no skips**, native compile/version |
| `go vet ./...` | Passed |
| Java adapter compilation with `javac --release 17` | Passed |
| Official MCP TypeScript SDK 1.31.0 against the native executable | Initialization, schemas, ping and six Dart graph/snippet queries passed |
| Official MCP SDK against the native polyglot fixture | Healthy language/status diagnostics, language search, callers, implementations, blast radius and snippet passed |

The polyglot fixture uses real compilers, not name-based resolver mocks. It verifies TypeScript alias imports, ES/CommonJS JavaScript calls, constructors shared by two tsconfig scopes, Java interface calls/overloads/constructors, Go structural implementations and receiver methods declared in a different file, positive and negative same-name targets, dependencies, references and impact. Semantic renames in TypeScript, Java and Go remove stale calls from unchanged consumers. Missing adapters report explicit diagnostics while Dart queries remain usable.

The Flutter fixture resolves actual flutter, flutter_bloc, flutter_riverpod, get_it, go_router and freezed_annotation packages. Framework classification and impact into the screen are asserted without mock Flutter types. Existing Dart and transport checks cover parts, accessors, operators, generics, package aliases, conditional imports, stable IDs, pagination, snippet limits/freshness, path confinement, schema/corrupt-cache recovery, dependency invalidation, same-process/cross-process writers, stdio lifecycle, malformed/bounded frames, cancellation and EOF.

The expanded CI runs Dart, required polyglot integration and real Flutter jobs. The preceding Dart-only revision passed GitHub CI; remote results for this revision are visible in the repository's Actions tab. Do not infer a remote pass from this local record.

Only Linux x86_64 native runtime has been checked. Other systems need their own compile/runtime verification. No production-scale throughput or token-saving benchmark is claimed. Static targets cannot fully recover reflection, arbitrary callbacks, dynamic runtime dispatch or cross-language RPC/FFI. Java Maven/Gradle dependencies require a configured classpath. Go dependencies must be prepared before indexing; the adapter disables downloads. See README precision and cache limits.

Git excludes dependency caches, generated indexes and native binaries. The checkout contains the compiled `build/polycodegraph`; a native deployment needs the provider assets/runtimes and an accessible Dart SDK for Dart/Flutter analysis.
