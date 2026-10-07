# Intent context — 0.9.0

The [0.10 development integration](migration-0.10.md) adds explicit environment
identity to lean snapshots and optional lossless client collection fusion.
Inventory/source/verification distinctions, cursor and baseline contracts below
remain applicable; fused completion is never a compiler or runtime proof.

Version 0.9 adds opt-in `format: lean` (`pcg-lean-1`) with separate
required inventory, optional context and unexecuted compiler/test verification.
Legacy/audit rendering remains the default. Lean capture implies exact strict
review scope; absent intended creations require `options.new_files`. Audit can
opt in with `options.strict_scope: true`. Capture and comparison must retain the
same scope and strictness. `change_signature.options.include_tests` requests
optional test exploration in lean mode; legacy collection is unchanged.
Exact text-based site relocation no longer produces a semantic added/removed
pair; full evidence preserves both positions and ambiguous mapping retains
explicit conservative evidence. See the [contract and limits](
benchmarks/efficiency-post-0.8/design.md) and [integration/rollback](
benchmarks/efficiency-post-0.8/integration.md). [Activation and rollback](migration-0.9.md) describe the released options. No new AI cost gate has passed.

`inspect_change` accepts an optional intent to collect focused context for a coding
agent. All ten intents apply to Dart/Flutter, TypeScript, JavaScript, Java, Go,
Python, Rust, Swift, Objective-C and Kotlin. These are read-only context services,
not automated refactorings or correctness approvals. Without `intent`, the 0.6
arguments, output, ordering and defaults remain unchanged. There are still sixteen
MCP tools.

## Calls

Use a reliable ID/unique target directly; search_symbol is needed only for discovery or ambiguity. Intent results include coverage/freshness:

```json
{"name":"inspect_change","arguments":{"target":"<stable-id>","intent":"rename","options":{"new_name":"recordedAt"},"budget":{"max_chars":12000,"max_items":40,"max_files":12},"detail":"compact"}}
```

| Intent | Typed options | Context and limits |
| --- | --- | --- |
| `rename` | `new_name?`, `scope?`, `include_impact=false` | Declaration, static uses, linked overrides/parameters/accessors, exports/parts. Homonyms excluded by identity; conflicts are candidates. No editable token spans or wire-key replacements. |
| `change_signature` | `added_parameters=[]`, `removed_parameters=[]`, `renamed_parameters={}`, `required?`, `return_type?`, `asynchronous?` | Contracts, callers, forwarding context and test candidates. Hypothetical compatibility stays conditional. |
| `find_tests` | `test_scope?`, `framework?` | Resolved paths to recognized test cases, or explicitly heuristic test files. Imports alone are excluded. Runner and runtime coverage stay unknown. |
| `review_change` | `files=[]`, `capture_baseline=false`, `capture_mode=minimal|context`, `baseline?` | Explicit before/after source hashes, symbols, edges and diagnostic changes. Missing baseline gives current context, not a fabricated diff. |
| `explain_symbol` | `focus=contract\|implementation\|dependencies` | Declaration/container, implementations, contract, direct dependencies and consumers. Explicit focus selects evidence, absent focus retains the broad recipe; other focuses are optional expansions. No generated business narrative. |
| `trace_flow` | `destination?`, `direction=out\|in` | Bounded directed calls and bidirectional override alternatives, with cycles/depth limits and qualified file-level unresolved frontiers. No runtime ordering or value dataflow. |
| `move_symbol` | `destination` | Consumers, contract, import/export/part context; destination indexed/proposed distinction. Build and private visibility compatibility unverified. |
| `remove_symbol` | `group=[]` | Internal versus external consumers, contracts, exports and candidate tests. `safe_to_delete` stays unknown. |
| `replace_dependency` | `replacement?` | Resolved construction/registration/implementation sites and contract/test context. Lifecycle and semantic equivalence unknown. |
| `extract_symbol` | `file`, `start_line`, `end_line`, `kind=function\|component` | Complete AST statement selection, bound local reads/writes, locals used afterward, static dependencies and control events. No extracted signature or lifetime/alias proof. |

Paths and scope directories are explicit, relative to the configured graph root.
Absolute paths, traversal, ambiguous names and incompatible/unknown options fail;
no prefix is silently corrected. Array/key limits are in `tools/list`. `scope`
restricts rename edit context but external consumers remain visible as
`out_of_edit_scope`; it does not change the configured index scope.

## Budget, shared evidence and expansion

Defaults: 12,000 **Unicode characters** of compact JSON serialization, forty
records, twelve files, depth two, 10,000 traversal steps. Hard ranges are
3,000–100,000 characters, 1–200 records, 1–32 files, depth 1–32 and 1–100,000
traversal steps. Existing configuration hard limits still apply. Provider/source
record limits also bound AST lookup; traversal limits bound graph exploration and
selected local/control/dependency evidence. `detail` does not remove these budgets.
Legacy `offset`, `limit`, `include_snippet` apply only without an intent.

Every response includes intent, target, generation, health fingerprint, freshness,
provider coverage, error previews, omitted diagnostics, limits and applied budget.
`ok` means successful context collection, never safe modification. `partial`,
`unsupported`, `not_found`, and explicit errors distinguish insufficient evidence
from empty results. Complete diagnostics are paged through `status`.

`symbols` and `evidence` share tables; source/target fields index the symbol table,
`site_file` indexes `files`, and `reason` indexes `rationales`. Sections reference
stable evidence IDs. The same complete relation/site is deduplicated; different
offsets on the same line are retained. `phase: before` distinguishes baseline
records, which never receive current-source snippets. Declaration ranges are
**not** editable name-token spans. Offsets use each provider's documented units.

Every section reports discovered counts, known totals or null, omitted records,
truncation, depth/exploration limits and expansion instructions. Snippet windows
are merged and separately bounded; hashes are verified before and after assembly.
A provider update error stays an error. Source edits during a read yield
`restart_required`, never old edges with new text. Follow every pertinent page and
expand truncated source with `snippet`; do not equate one short page with complete
context. Display whitespace added by a broker, JSON-RPC framing, duplicated
text/structured content and tool schemas are outside `max_chars` and must be
accounted for separately in client measurements.

See the additive [0.8 views, collection budgets and acknowledgement contract](efficiency-0.8-design.md). Legacy omitted/truncated remain per-page; use page_count, remaining_after_page and collection_complete to stop. Source windows and exploration incompleteness are separate.

Repeat identical arguments plus the returned `next_cursor`. Handles are opaque,
session-only, bound to arguments/budget/root/generation/health, and expire after
five minutes. At most sixteen handles and 64 MiB of accounted serialized plans
are retained; eviction requires restart. Changed health also invalidates a cursor
when source generation is unchanged. Exhausting traversal requires a new request
with a larger budget, not just another page.

## Explicit review baseline

```json
{"name":"inspect_change","arguments":{"target":"src/service.ts","intent":"review_change","options":{"files":["src/service.ts"],"capture_baseline":true}}}
```

Retain `facts.baseline.handle`; after editing and indexing, repeat with the same
file scope and `options.baseline`. Baselines expire after ten minutes, belong to
one server/root, and retain at most two immutable snapshots with a 128 MiB total
serialized-snapshot budget. Oversized snapshots fail explicitly. Deleted files
can still be reviewed with their captured baseline. Renamed/moved IDs remain
added/removed; no identity correspondence or Git historical indexing is guessed.
Source-hash changes are separate `source_changes` evidence with before/after hashes in `details`. Body-only edits can leave symbol/edge records unchanged. In 0.8 captured sources localize changed line ranges to containing declarations; file_context selects those seeds, with explicit file fallback for uncertain/global ranges. This is not a Git diff or behavioral approval.
Diagnostic changes include bounded previews and explicit omissions. Follow the
`diagnostic_changes` evidence pages: `details`, keyed by evidence ID, preserves
complete original new/resolved messages from both snapshots. Retain baseline
diagnostics separately only if needed after handle expiry.

## Language capability matrix

All ten intents were exercised over native MCP on each language fixture. The
following distinguishes available evidence from full refactoring support;
`partial` is an intentional precision limit, not an untested success claim.

| Language | Graph context / explicit review | Rename / signature binding enrichment | Test discovery | Extraction constraints |
| --- | --- | --- | --- | --- |
| Dart | Supported static evidence | Analyzer field/formal, super-parameter, accessor and named-label links; signature compatibility partial | Resolved recognized test cases plus explicit candidates | Partial: Analyzer statements and bound locals |
| TypeScript | Supported static evidence | Partial: existing compiler symbols/overrides; no parameter-contract enrichment | Partial: resolved paths to named test-file candidates | Partial: compiler statements and lexical bindings |
| JavaScript | Supported static evidence | Partial: existing compiler symbols; dynamic sites unresolved | Partial: resolved paths to named test-file candidates | Partial: compiler statements and lexical bindings |
| Java | Supported static evidence | Partial: javac symbols/overrides; no parameter-contract enrichment | Partial: resolved paths to named test-file candidates | Partial: javac Trees and bound locals |
| Go | Supported static evidence | Partial: go/types symbols and existing interface relationships | Partial: resolved paths to named test-file candidates | Partial: Go AST/go/types local identities |
| Python | Supported static evidence | Partial: Jedi targets; dynamic contracts unresolved | Partial: resolved paths to named test-file candidates | Partial: AST/symtable namespaces and Jedi definitions |
| Rust | Supported static evidence | Partial: rust-analyzer targets; no hypothetical trait/type checking | Partial: resolved paths to named test-file candidates | Partial: syntax plus rust-analyzer definitions |
| Swift | Supported static evidence; UIKit requires macOS host validation | Partial: compiler targets; protocol witness mappings unavailable | Partial: resolved paths to named test-file candidates | Partial: compiler AST plus SourceKit locals; incomplete without compatible SDK library |
| Objective-C | Supported static evidence; UIKit requires macOS host validation | Partial: Clang canonical/override links; dynamic messaging unresolved | Partial: resolved paths to named test-file candidates | Partial: Clang statements and canonical local cursors |
| Kotlin | Supported static evidence; Android SDK fixture verified | Partial: K2 IR targets/overrides; no hypothetical signature check | Partial: resolved paths to named test-file candidates | Partial: PSI statement bounds and IR local identities |

Graph context covers `explain_symbol`, `trace_flow`, `move_symbol`,
`remove_symbol` and `replace_dependency`: only relationships actually emitted by
that provider are available. Every language keeps unknown visibility/lifecycle,
dynamic dispatch, external consumers and execution semantics qualified. Explicit
`review_change` compares captured hashes/records/diagnostics without type/test
approval. `extract_symbol` never promises complete dataflow, signature generation
or a safe patch; missing AST metadata returns `unsupported`. A failed/missing
provider remains visible in coverage and health. See the
[verification matrix](benchmarks/intents-0.7/report.md) for host checks and skips.

## Extraction precision

The providers retain intent-only AST information without modifying primitive
symbols or edges. Dart uses Analyzer; TS/JS compiler bindings; Java javac Trees;
Go AST/go/types; Python CPython lexical namespaces plus Jedi definition locations;
Rust syntax plus rust-analyzer definitions; Objective-C canonical Clang cursors;
Kotlin source PSI boundaries plus K2 IR identities. Swift combines compiler AST
boundaries with SDK SourceKit declaration offsets. Without a compatible SourceKit
library, Swift local bindings are incomplete and reported as such. Compiler
plugins/build hooks of indexed projects are never loaded.

Select complete statements in one block/scope. An unavailable AST capability
returns unsupported; invalid selections fail explicitly. Read/write bindings and
control events are constraints, **not complete dataflow**. Aliases, pointers,
closure escape, reflection, definite assignment, exceptions, async ordering,
Rust borrows/lifetimes and a hypothetical extracted function/component remain
unverified. Initializer declarations used afterward are reported as possible
outputs. Small fact previews have counts/omissions and evidence/snippet expansion;
no reliable `suggested_signature` is generated. Always run the project's normal
compiler and tests after any change.

See [0.8 additive migration](migration-0.8.md), [historical 0.7 migration](migration-0.7.md), [provider contract](providers.md),
[consumer harness](harness-AGENTS.md) and [measured validation](benchmarks/intents-0.7/report.md).
