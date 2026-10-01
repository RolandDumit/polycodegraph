# Developing PolyCodeGraph

PolyCodeGraph is a local semantic code-intelligence MCP server. Read `docs/architecture.md` for module boundaries and `docs/protocol.md` for the transport/query contract. `docs/harness-AGENTS.md` is a template for consumers, not this server's development policy.

## Working loop

1. Inspect the affected module and relevant fixture expectations in `docs/fixture-contracts.md`. If this repository is indexed by PolyCodeGraph, use architecture/search/callers/blast_radius to narrow exploration; use source search when coverage is incomplete or the server is being changed.
2. Keep extraction, indexing, queries and MCP transport separate. Put language-specific logic in providers, with targets resolved by the supported semantic engines. Add regression tests for semantic or protocol changes; document precision limits.
3. Run `dart run tool/check.dart` before completing a change. Use `--providers` for the original semantic providers, `--mobile` for Swift/Objective-C/Kotlin, `--android` or `--ios` for SDK integration changes, and `--flutter` for Flutter discovery changes; use `--build` for CLI/packaging changes. See `CONTRIBUTING.md` for toolchain setup. Optional tests skipped for missing dependencies are not verified coverage.
4. Update user-facing docs when options, precision or runtime prerequisites change. Report the checks run, skipped checks and remaining limitations.

## Invariants

- Stable IDs use repository-relative file, qualified identity and kind. Overloaded members must not collide. Keep pagination and row ordering deterministic; return generation and explicit truncation/coverage indicators.
- Calls and references require semantic resolver evidence. Never join same-name methods across unrelated types. Type/callback/dynamic analysis limitations belong in diagnostics or documented precision, not fabricated edges. Flutter naming tags are hints.
- Preserve source/cache path confinement and symlink rejection. Never execute indexed source, annotation processors, repository package scripts or build hooks. Provider subprocesses use argument lists, bounded output and deadlines.
- MCP stdout contains protocol messages only. Send diagnostics to stderr. Retain framing limits, cancellation semantics, argument validation and equivalent compact text/structured results.
- Cache semantics include source content, environment/build configuration, provider versions and runtime configuration. Rebind dependents after semantic edits; publish a coherent snapshot atomically. Change the index schema version when stored contracts change.
- Test source edits in temporary fixture copies. Keep generated caches, compiler artifacts, node_modules and local SDK paths out of Git. Preserve the MIT attribution when adapting external code.

No agent model or external account configuration is imposed by this repository.
