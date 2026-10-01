# PolyCodeGraph code intelligence

Use the `polycodegraph` MCP server configured for this repository (Dart/Flutter, TypeScript/JavaScript, Java and Go).

- Start with `status` or `get_architecture`. Check provider health, diagnostic samples, skipped files and unresolved-call coverage. If imports fail to resolve, run the project's normal dependency setup (Dart/Flutter packages, Node dependencies, Go modules, or a configured Java classpath) and reindex. Use `index_repository` with `force: true` after dependency setup when lock/config files did not change.
- Use `search_symbol` to find stable IDs. Prefer returned IDs to ambiguous bare method names. Query with `language`, `kind`, `tag` and `file` filters when useful.
- Before changing a symbol, inspect `callers`, `implementations`, `dependencies` and `affected_by_change`. Calls point to static compiler targets; inspect implementations for interface dispatch. Treat blast radius as conservative and incomplete if depth/coverage limits are reported.
- Follow pagination while the generation is unchanged. Restart an exploration if the repository changes.
- Use `snippet` for focused source reads. If it reports truncation, request additional explicit line windows.
- After editing, call `index_repository`; subsequent queries refresh automatically too. Re-check important callers and affected files.
- Run the project's normal compiler/static analysis and tests. Use source search/manual inspection for dynamic calls, callbacks, reflection, runtime routing and missing generated code.
- Flutter tags help locate likely layers; verify the actual code before relying on a naming or annotation hint.

Keep `.polycodegraph/` out of version control. Never paste the entire cached graph into an agent prompt.
