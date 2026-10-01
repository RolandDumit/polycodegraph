# Contributing

Use Dart 3.11+ (CI pins 3.13.2). Resolve the root package with `dart pub get`. For all language providers, install Node.js 22+, Go 1.25+ and a full JDK 17+, then run:

```sh
bash tool/setup-providers.sh
bash tool/check.sh --providers --build
```

The setup script installs only the pinned TypeScript compiler dependency with package scripts disabled, and builds the Go adapter from its locked module dependencies. Java uses the standard compiler API and needs no external library. These tools analyze project source; they do not run project applications. The graph server never installs dependencies automatically.

`bash tool/check.sh` checks Dart formatting, static analysis and the test suite. `--providers` requires all semantic adapters and runs the mandatory multi-language integration tests; without it, unavailable-provider integration cases explicitly skip. `--build` also compiles and smoke-tests the native CLI. Optional Flutter coverage requires:

```sh
(cd examples/flutter_fixture && flutter pub get)
bash tool/check.sh --flutter
```

`--flutter` fails if the fixture is unconfigured. You can combine flags. `DART`, `NODE`, `JAVA` and `GO` select local executables for the check/setup scripts. For the running server, use config `node_path`, `java_path`, `go_path` and `providers_path`. The native binary is distributed with the `providers/` directory, including the installed TypeScript dependency and built Go adapter.

Follow [AGENTS.md](AGENTS.md). Add a minimal fixture with expected semantic relationships when changing resolution. Test both intended edges and unrelated same-name decoys. For invalidation, change a declaration without editing its consumer and verify that stale bindings disappear. Avoid asserting only node counts.

CI checks Dart, all semantic adapters and a separate real Flutter fixture. Keep each language's required runtime and coverage limits documented. Do not describe optional or skipped tests as passing semantic verification.
