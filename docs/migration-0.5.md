# Migrating to 0.5.0

1. Build/install the Rust executable and retain adjacent provider assets.
2. Replace the MCP command that invoked Dart with the native executable. Keep `serve --root` and existing graph configuration; add `providers_path` if assets are relocated.
3. Run `setup --languages ...` for needed adapters, then `doctor` and `index`. Dart/Flutter still needs its SDK. Non-Dart projects no longer require Dart for the server/setup.
4. The first run creates `.polycodegraph/index.sqlite`; the legacy JSON snapshot remains untouched. Cache format/generation fingerprints change, while stable public symbol IDs and query schemas are retained.
5. Adopt `inspect_change` in AGENTS.md and inspect `status.freshness`. Watcher events plus 30-second reconciliation are now the default; choose `watch: false` for full verification on every query. `index_repository` forces a hash scan; `force: true` also forces extraction.

The public Dart core library/CLI is retired. Dart lives only in the Analyzer provider. Language precision boundaries, including omitted cross-language/runtime edges, remain unchanged.
