# Contributing

Use Dart 3.11+ (CI pins 3.13.2). Resolve the root package with `dart pub get`. For all language providers, install Node.js 22+, Go 1.25+, a full JDK 17+ and Python 3.11+, then run:

```sh
dart run tool/setup_providers.dart --dev
dart run tool/check.dart --providers --build
```

The setup script installs only the pinned TypeScript compiler dependency with package scripts disabled, and builds the Go adapter from its locked module dependencies. Java uses the standard compiler API and needs no external library. Python uses pinned Jedi/Parso wheels in an isolated virtual environment. Rust setup verifies a pinned official rust-analyzer binary for the host; `RUST_ANALYZER` can select an existing native installation. It needs Python for the LSP driver and does not invoke Cargo or indexed build hooks. `--dev` installs pinned Ruff/mypy for provider lint, formatting and strict type checks; these run under `--providers` when prepared. These tools analyze project source; they do not run project applications. The graph server never installs dependencies automatically.

`dart run tool/check.dart` checks Dart formatting, static analysis and the test suite. `--providers` requires all semantic adapters and runs the mandatory multi-language integration tests; without it, unavailable-provider integration cases explicitly skip. `--build` also compiles and smoke-tests the native CLI. Optional Flutter coverage requires:

```sh
cd examples/flutter_fixture
flutter pub get
cd ../..
dart run tool/check.dart --flutter
```

`--flutter` fails if the fixture is unconfigured. You can combine flags. `DART`, `NODE`, `JAVA`, `GO`, `PYTHON` and `RUST_ANALYZER` select local executables for the check/setup scripts. For the running server, use config `node_path`, `java_path`, `go_path`, `python_path`, `rust_analyzer_path` and `providers_path`. The native binary is distributed with the `providers/` directory, including the installed TypeScript dependency and built Go adapter.

Follow [AGENTS.md](AGENTS.md). Add a minimal fixture with expected semantic relationships when changing resolution. Test both intended edges and unrelated same-name decoys. For invalidation, change a declaration without editing its consumer and verify that stale bindings disappear. Avoid asserting only node counts.

CI runs each of the Dart/native MCP, semantic adapter and real Flutter jobs on Linux, macOS and Windows. All setup/check commands work without Bash. Native builds use `.exe` on Windows. Keep each language's required runtime and coverage limits documented. Do not describe optional or skipped tests as passing semantic verification.
