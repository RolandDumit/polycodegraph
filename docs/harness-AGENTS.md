# Dart/Flutter code intelligence

Use the `dart-codegraph` MCP server configured for this repository.

- Start with `status` or `get_architecture`. Check diagnostics, skipped files and unresolved-call coverage. If imports fail to resolve, run the project's normal package setup and reindex.
- Use `search_symbol` to find stable IDs. Prefer returned IDs to ambiguous bare method names. Query with `kind`, `tag` and `file` filters when useful.
- Before changing a symbol, inspect `callers`, `implementations`, `dependencies` and `affected_by_change`. Calls point to static Analyzer targets; inspect implementations for interface dispatch. Treat blast radius as conservative and incomplete if depth/coverage limits are reported.
- Follow pagination while the generation is unchanged. Restart an exploration if the repository changes.
- Use `snippet` for focused source reads. If it reports truncation, request additional explicit line windows.
- After editing, call `index_repository`; subsequent queries refresh automatically too. Re-check important callers and affected files.
- Run the project's normal analysis and tests. Use source search/manual inspection for dynamic calls, callbacks, reflection, runtime routing and missing generated code.
- Flutter tags help locate likely layers; verify the actual code before relying on a naming or annotation hint.

Keep `.dart-codegraph/` out of version control. Never paste the entire cached graph into an agent prompt.
