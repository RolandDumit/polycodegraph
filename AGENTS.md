# Developing PolyCodeGraph

The CLI/MCP/index/query core is Rust. Read docs/architecture.md and docs/protocol.md; docs/harness-AGENTS.md is the consumer template.

- Preserve semantic resolver evidence, stable IDs, deterministic pagination, compact output and visible precision limits across all ten providers.
- Keep transport, storage, filesystem, indexing and query logic separate. Rust code follows ownership-based sharing, typed errors and bounded concurrency; do not hold shared state locks during provider awaits.
- Run `cargo xtask check`. For semantic/provider changes, prepare relevant adapters and run native MCP smoke/differential tests. For mobile changes include Android and macOS UIKit SDK checks. Optional skipped tests are not verified coverage.
- Dart changes additionally require formatting, static analysis and provider tests in providers/dart. Keep Analyzer pinned and do not replace semantic resolution with name matching.
- Verify watcher loss/overflow, transactional publication, source edits during analysis and invalidation boundaries. Changed scopes must retain context for unchanged symbols.
- Never execute indexed application code, project plugins, package scripts, build hooks or code generation. Keep subprocess budgets, path confinement and symlink rejection.
- stdout is protocol-only during serve. Diagnostics go to stderr. Preserve cancellation, framing/queue limits and EOF draining.
- Update configuration/docs/provider contracts when behavior changes. Record actual benchmarks, tests, skipped checks and limitations. Keep caches, binaries, SDK paths and environments out of Git.
