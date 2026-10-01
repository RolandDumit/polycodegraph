# Validation record

Verified locally on 2026-10-01, Linux x86_64, Dart 3.13.2 / Flutter 3.47.2.

| Check | Result |
| --- | --- |
| Dependency resolution with `dart pub get --enforce-lockfile` | Passed |
| `dart format --output=none --set-exit-if-changed bin lib test` | Passed |
| `dart analyze --fatal-infos` | Passed; no issues |
| `dart test --reporter expanded` | 26 tests passed; real Flutter integration enabled |
| `dart compile exe bin/dart_codegraph.dart -o build/dart-codegraph` | Passed; Linux x86_64 executable produced |
| Native CLI init/status/version, overwrite prevention, invalid command | Passed |
| Official MCP TypeScript SDK 1.31.0 against native executable | Initialization, tools/list schemas, ping and six graph/snippet queries passed |
| Indexing the server's own repository | Passed, including nested packages and Analyzer-excluded fixture sources |

The Flutter fixture resolved actual flutter, flutter_bloc, flutter_riverpod, get_it, go_router and freezed_annotation packages. Framework classifications and impact into the UI file were asserted without mock Flutter types.

Tests cover graph declarations and relations; static interface targets and same-name decoys; inherited overrides; generic substitutions; package-prefix resolution; conditional imports; unary/binary operator identity; extension type constructors; getter and setter access; part relationships; stable IDs after line insertion; conservative impact including dispatch contracts; pagination; bounded and stale snippets; YAML/JSON config and path validation; cache reuse, semantic invalidation, additions, deletions, corrupt/schema-incompatible cache recovery; excluded dependency invalidation; explicit graph inclusion over Analyzer exclusions; concurrent writers in the same process and across processes; MCP lifecycle/errors; malformed and oversized stdio frames; query freshness; and EOF shutdown.

CI configuration is provided but was not run on a remote CI service. Native execution has been checked on Linux x86_64; other operating systems/architectures need their own compile and runtime checks. No production-scale performance or token-saving benchmark is claimed. Static analysis cannot fully recover dynamic dispatch, reflection or callback flow; see the README's accuracy section.

The source archive excludes Git metadata, dependency caches, generated indexes and native build artifacts. The local checkout retains the compiled executable at `build/dart-codegraph`. A native executable needs an accessible SDK; local native query checks specified Flutter's Dart SDK through `sdk_path`.
