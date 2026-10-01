# Development

Install pinned Rust 1.99.0 with rustfmt/clippy. Build with `cargo build --release --locked`; run `cargo xtask check`.

Prepare adapters with the native CLI's `setup --languages dart,typescript,javascript,java,go,python,rust,swift,objectivec,kotlin --dev` after installing their host runtimes. Use only the languages relevant to your change. The setup scripts never prepare indexed target projects.

Dart Analyzer development: `cd providers/dart`, `dart pub get --enforce-lockfile`, `dart format --output=none --set-exit-if-changed bin lib test`, `dart analyze --fatal-infos`, `dart test`.

Native validation: `python tool/smoke.py --group dart`, `--group polyglot`, `--group mobile`, `--group flutter`. Flutter requires prepared examples/flutter_fixture dependencies. Use `--baseline` with the v0.4.0 compiled server for differential checks. `tool/sdk_smoke.py` covers real Android and macOS UIKit dependencies.

`cargo xtask package` builds the host distribution in dist/polycodegraph; run setup for Dart/Go before packaging to include native adapters. Packages exclude virtual environments, node_modules and downloaded Kotlin/rust-analyzer assets; setup prepares them on the destination. Publish only after tests and platform package smoke checks.

See docs/benchmarks/README.md for reproducible performance comparisons. Benchmark compilation uses the v0.4.0 package configuration; no legacy core is carried in current production source.
