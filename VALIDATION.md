# Validation record

PolyCodeGraph 0.4.0 was verified locally on 2026-10-01 at `~/Projects/Personal/polycodegraph`, Linux x86_64, with Dart 3.13.2 / Flutter 3.47.2, Node 26.7.0 / TypeScript 6.0.2, Go 1.27.1, OpenJDK 25.0.3, Python 3.14.7 / Jedi 0.20.0 / Parso 0.8.7, and rust-analyzer 0.3.3065 (official 2026-09-28 release), Swift 6.2, Kotlin K2 2.3.10, libclang 18.1.1 and a real Android platform JAR.

| Check | Result |
| --- | --- |
| Pinned TypeScript setup and Go module verification/build | Passed |
| Python isolated environment, hash-verified runtime wheels and rust-analyzer release | Passed |
| Ruff lint/format and strict mypy | Passed |
| `dart run tool/check.dart --providers --mobile --android --flutter --build` | Formatting, static analysis, **54 tests passed; the macOS-only UIKit test skipped locally**, native compilation and version passed |
| Native stdio MCP | All ten languages indexed; typed Python/Rust calls and snippets, Dart query/part relations, refresh and EOF passed |

The combined native MCP fixture exercises Dart, TypeScript, JavaScript, Java, Go, Python, Rust, Swift, Objective-C and Kotlin together. Mobile semantic cases cover compiler identities, overloads, overrides, header imports, stable IDs after leading comments, missing runtimes, Unicode/CRLF, read-only target models and contract edits. Android analysis uses the actual installed SDK; UIKit verification is required on the macOS CI runner, not claimed from Linux. Semantic fixtures check alias imports, typed interface/trait calls, constructors, same-name decoys, fields, references, implementations, dependencies and impact. Contract renames remove stale bindings from unchanged consumers. Warm caches avoid work; language manifests, project models, configuration and provider assets participate in invalidation.

Python/Rust tests also cover dynamic-call diagnostics, local Cargo path dependencies and aliases, Cargo default features, Unicode/percent-escaped paths, astral characters, CRLF and snippets. Indexed Python source, Cargo build scripts, rustc wrappers, nonexistent toolchain overrides, proc-macro libraries and project runnables must not execute. Missing adapters preserve file nodes with explicit coverage diagnostics. Strict runtime-path/list configuration validation is covered.

The Flutter fixture resolves actual flutter, flutter_bloc, flutter_riverpod, get_it, go_router and freezed_annotation packages. Framework classification and impact into the screen are asserted without mock Flutter types. Existing Dart and transport checks cover parts, accessors, operators, generics, aliases, conditional imports, stable IDs, pagination, snippet limits/freshness, path confinement, cache recovery, dependency invalidation, concurrent writers, initialization, framing, cancellation and EOF.

CI has a twelve-job matrix, adding mobile/native MCP and real Android SDK checks on all hosts and real UIKit/bridging on macOS: Dart/native MCP, mandatory polyglot/native MCP and real Flutter on **Linux, macOS and Windows**. The polyglot jobs prepare the seven original-language adapters; mobile jobs prepare the three mobile adapters and require language integration tests; core-only jobs explicitly skip unavailable optional adapters. The previous Python/Rust revision passed all nine jobs ([run](https://github.com/RolandDumit/polycodegraph/actions/runs/36857337134)); results for the current revision are available in [Actions](https://github.com/RolandDumit/polycodegraph/actions/workflows/ci.yml).

Static targets do not fully recover dynamic dispatch, reflection, arbitrary callbacks or cross-language RPC/FFI. Python dependencies may need explicit search paths. External Rust crates, custom features/targets, generated modules and macro expansion require a prepared project model and remain visible as reduced coverage. External dependency changes without changed locks/configuration require forced indexing. No production-scale throughput or token-saving benchmark is claimed.

Dependency caches, generated indexes, Python environments, native tooling and binaries stay out of Git. Native deployment requires provider assets, host-specific runtimes and a Dart SDK for Dart/Flutter analysis. Recreate environments/binaries for the destination host.
