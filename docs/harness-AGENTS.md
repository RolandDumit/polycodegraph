# PolyCodeGraph code intelligence

Use the `polycodegraph` MCP server configured for this repository (Dart/Flutter, TypeScript/JavaScript, Java, Go, Python, Rust, Swift, Objective-C and Kotlin).

- Check `status` once at task start; repeat only after changes to sources, environment, freshness or diagnostics. Inspect freshness and coverage, provider health, errors/warnings, skipped files and unresolved calls. With the experimental compact profile retrieve omitted diagnostics using `status(section: diagnostics, offset, limit)`; `detail: full` expands a call. If imports fail to resolve, run the project's normal dependency setup and reindex. Use `index_repository` with `force: true` after dependency setup when lock/config files did not change.
- Use `search_symbol` to find stable IDs, initially with limit 5–10. Prefer returned IDs to ambiguous names. Filter by language/kind/tag/file; file prefixes are relative to the graph root, including nested package prefixes.
- Before changing a symbol, use `inspect_change` for callers, implementations and impact in one snapshot (initial limit 10–20). Do not immediately repeat those included sections; expand with paged tools only when omissions or a specific question require it. For exploration use the relevant relation directly. Calls point to static semantic targets; inspect implementations for interface dispatch. Treat blast radius as conservative and incomplete if depth/coverage limits are reported.
- Follow pagination while the generation is unchanged. Restart an exploration if the repository changes.
- Use `snippet` for focused source reads, initially 20–40 lines. Expand truncation with explicit line windows. Use textual search for a specific gap in graph coverage, rather than repeating the entire exploration.
- After editing, call `index_repository`; subsequent queries refresh automatically too. Re-check important callers and affected files.
- Run the project's normal compiler/static analysis and tests. Use source search/manual inspection for dynamic calls, callbacks, reflection, runtime routing and missing generated code.
- For Python, inspect unresolved callback/dynamic coverage. For Rust, check external-crate/macro diagnostics and the active crate/cfg model; generated/build-script results require an explicitly prepared model.
- Flutter tags help locate likely layers; verify the actual code before relying on a naming or annotation hint.

Keep `.polycodegraph/` out of version control. Never paste the entire cached graph into an agent prompt.

- For Swift/Objective-C/Kotlin repositories, inspect `polycodegraph.mobile.json` for the active module/target, SDK, bridging header and prepared dependencies. iOS SDK analysis belongs on macOS/Xcode; Android JAR analysis is portable. Prepare builds/dependencies through the project's normal workflow, then force indexing when external artifacts changed. Do not interpret the graph as running Gradle, SwiftPM manifests, KAPT/KSP, macros or compiler plugins. Swift/Objective-C and Kotlin/Java cross-language calls remain incomplete; use source/SDK tooling at those boundaries.

Use the Rust executable as the MCP command. Watcher freshness can lag until reconciliation if events are missed; call index_repository before a sensitive impact assessment, or configure watch:false for per-query full scans. Neither the graph nor its freshness metadata replaces compiler checks/tests.
