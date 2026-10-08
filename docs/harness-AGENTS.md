# PolyCodeGraph code intelligence

Use the configured native PolyCodeGraph MCP server when the task needs structural
or semantic evidence. It supports Dart/Flutter, TS/JS, Java, Go, Python, Rust,
Swift, Objective-C and Kotlin. The server does not run application code/build hooks.

## Route to the question

| Task | First useful operation |
| --- | --- |
| Known file/position, local edit | Focused file read; zero graph calls are allowed |
| Reliable stable ID or unique target | Use that target directly; no preliminary search required |
| Ambiguous rename | Resolve identity, then rename intent with `view: locations`; retain all required sites and review DTO/wire keys separately |
| Public signature | change_signature with requested parameter/return/async options and `view: contracts` or edit_context; retain consumers/contracts |
| Bug described by symptom | Content search or search_symbol(mode: lexical); anchor_id can go directly into an intent; expand only the needed relation |
| Flow toward a component | trace_flow with destination and explicit direction/depth; qualified static path, not runtime ordering |
| Dynamic/generated boundary | Static evidence plus focused search/SDK checks for the declared gap |
| Review | Capture exact files before editing, capture_mode: minimal and strict_scope: true; compare the captured working tree with the same scope after refresh |

Intent results include generation, health_fingerprint, freshness, provider coverage
and errors. If the first useful operation supplies these, a separate status call
is unnecessary. Use status for changed health or detailed omitted diagnostics.
For sensitive impact assessments reconcile explicitly with index_repository, or
use watch:false for per-query full hash scans. Watcher events can be lost until
periodic reconciliation; freshness is not a compiler/test result.

## Select and expand

Optional `format: lean` returns `pcg-lean-1`: preserve all `records`/`sites`,
`completion.required_inventory`, limits and snapshot identities. A client with
an explicit insertion adapter may collect required pages and insert its one text
representation. Ordinary MCP clients can request lean directly and handle pages;
this server option does not install an adapter or prove what reaches the model.
Omit format or use audit for the default canonical response. Lean is self-contained,
rejects retained-window acknowledgement and defaults to edit_context. Include
optional signature tests only for a concrete question (`include_tests: true`).
For strict review, absent intended creations must be declared in `new_files`;
retain capture/comparison scope and strictness. A typo is an error, not a new file.
Relocated sites are inspectable with full_evidence; ambiguous mappings stay visible.
Compiler/test verification remains not_run until performed outside the graph.


Use `locations` for usage manifests without source, `contracts` for declaration
headers, `edit_context` for a primary declaration and AST/site windows, and
`full_evidence` when deeper verification needs it. Missing boundaries are labelled
fallbacks: use snippet with precise file/line windows for the gap. Without view,
0.7 intent source windows remain available; primitive detail: compact/full is
separate. Default budgets are 12000 characters, 40 records, 12 files, depth two.
max_tokens is a declared local estimate, never provider-accounted model usage.

Read audit evidence until remaining_after_page is zero and collection_complete
is true. For lean, use completion.required_inventory.remaining_known and state;
record any static gap or limit and follow its precise recovery.
Optional pages/sections need a concrete question. Do not fetch primitive callers,
implementations, impact or snippets already supplied by the intent. Expand for a
missing necessary site, pertinent source truncation, or a specific uncertainty.
Legacy omitted means absent from this page, even on the final page. Check the new
completion fields and source_windows_incomplete separately. Static collection
completion never proves full runtime coverage, safe deletion or correct behavior.

Repeat identical arguments plus next_cursor. Root, view, budgets, generation,
health and client context bind handles; changed identity/expired handles require
restart. A collection cap requires a new explicit larger collection, not an
automatic retry loop. New errors must remain visible during delta responses.

A client implementing acknowledgement may send only windows it actually retains.
Reset epoch and known_windows after compaction, new agent/root or lost state;
rehydrate forces full source restoration. Ordinary clients use self-contained
responses. Never infer retained context merely from a previous server response.

After edits, the next graph query applies the configured freshness policy; avoid
an additional index when that already meets the task's needs. Explicit scans are
still appropriate for sensitive impact or after prepared dependencies change;
use force:true when external artifacts changed without a tracked lock/config edit.
Use exact hash-checked source and successful edit receipts already returned.
Read back a changed file for a concrete missing fact, truncation, a failed edit
or changed source identity; avoid a full readback of every edited file by habit.
Write receipts establish that the edit happened, not that it is correct.
Complete the project's authorized compiler/static analysis/tests. Empty static
results do not establish absence of consumers/tests/effects. Inspect dynamic calls,
callbacks, reflection, macros, FFI and runtime routing at declared boundaries.

## Provider and tool access

Use IDs from search when names are ambiguous. Prefixes are indexed root-relative,
including nested packages. Retrieval scores/tags are discovery hints; semantic
relations keep provider confidence and distinct same-line offsets. Declaration
ranges/reference sites are not automatically editable name spans.

For mobile, inspect the prepared module/SDK/classpath model. UIKit belongs on
macOS/Xcode; Android JAR analysis is portable. Indexed Gradle/SwiftPM manifests,
plugins, KAPT/KSP and macros are not executed. Python dynamic callbacks, Rust
external crates/cfg/build results, and cross-language mobile calls remain qualified.
Extraction requires complete AST statements; bound locals/control exits are
constraints, not a proposed signature, lifetime proof or automatic refactoring.

Optional `tool_profile: agent` advertises status, search_symbol, inspect_change,
snippet and index_repository. Original tools/aliases stay accepted. All ten intents remain available through the advertised inspect_change. Hidden
primitive schemas from status(section: tools, tool: "neighbors") are data; a
client must register them before model invocation, or use the full profile. The full
profile is default. Client discovery/loading behavior must be measured; do not
assume the server alone controls the model's actual schema prompt.

Keep .polycodegraph caches and raw traces out of Git. Never paste the whole graph
into a prompt. See [intent contracts](intents.md), [0.9 activation/rollback](migration-0.9.md)
and the [efficiency protocol](benchmarks/efficiency-0.8/protocol.md).
