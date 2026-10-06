# Efficiency design 0.8

Base: v0.7.0, `06e0a72741d2370b74888b86311709dfd9c3f286`.
New branch: work/efficiency-0.8. No previous candidate code is imported.
The historical protocols remain frozen. This document defines additive contracts
before implementation; validation and the activity ledger live in the new report.

## Presentation and collection

Absent `view` retains 0.7 source windows and ignores primitive `detail` for intents.
Explicit views: `locations` retains the entire site inventory without source;
`contracts` selects declaration headers; `edit_context` selects the main declaration
and containing AST statements at sites; `full_evidence` adds declaration ranges and
statement windows. Missing boundaries use bounded, labelled line/header fallbacks.
All site offsets and relationship kinds remain individually recoverable.
Required evidence is enumerated independently of optional understanding context.

`budget.max_tokens` is optional and uses **unicode_chars_div4_v1**, ceil(final
compact-JSON Unicode characters / 4), an estimate without a model tokenizer.
Both max_chars and the estimate limit apply to the entire server result. Neither
includes client wrappers, schemas or model usage. 512/1024/2048 are exploratory
benchmark settings, not limits for a required rename inventory.
`max_traversal` bounds internal work, `max_items/max_files` bound each page, and
optional `max_collection_items` bounds cumulative records in this collection.
Exhausting collection/work requires a new request with an explicit larger budget;
no automatic retry. All budgets/view/context acknowledgements bind cursors.

Legacy omitted/truncated keep their per-page meanings. New page_count and
remaining_after_page disambiguate progress. collection_complete refers only to
requested static collection; exploration_incomplete and source_windows_incomplete
are separate. An exhausted record budget never claims completeness or runtime
safety. Oversized records identify a useful recovery and do not return a cursor
that could repeat the same failure indefinitely.

## Review

Capture retains hash-checked UTF-8 text only for explicitly scoped files and shares
the semantic snapshot for historical consumers, within the existing session TTL/count/128 MiB bound. `capture_mode: minimal`
returns a handle/scope/identity/health rather than declaration context. It compares
with that captured working tree, never implicitly HEAD. Bounded line diff plus
smallest containing declaration selects seeds; body changes select dependencies
and tests, contract/global changes conservatively include consumers. Uncertain
mapping declares a file fallback. Byte/codepoint/UTF-16 offsets are not interchanged:
localization uses source line ranges, then retains provider-native site offsets.

## Context acknowledgement

An optional client context supplies epoch, root_id, generation, health_fingerprint,
environment_fingerprint, known_windows and rehydrate. Window keys also include file hash, environment,
view and range. Only explicitly retained source windows can be suppressed; the
site inventory and current health/diagnostics stay visible. A changed identity
falls back to a self-contained response. Compaction/new agent requires a new epoch
and empty acknowledgements or rehydrate. Clients without this protocol always
receive self-contained responses. Sending a response never implies acknowledgement.

## MCP and retrieval

Full advertised toolset remains default. Optional agent profile advertises status,
search_symbol, inspect_change, snippet and index_repository. All original tools
and aliases remain accepted with full runtime validation. status(section: tools)
discovers accepted schemas; no client lazy-loading support is presumed.
Opt-in lexical search finds content candidates, anchors to existing declarations,
and optionally expands resolved dependencies/callers. Retrieval scores are not
semantic confidence; content matches never create resolved edges.

## Runtime

Measure before invasive changes. A file index on SQLite edges and a transactional
storage revision are isolated candidates; provider persistence, AST interning and
incremental derived graph rebuilds require profiling before implementation.

## Deliberate limits

The lexical baseline uses bounded line documents and IDF-weighted term overlap,
not BM25. Declaration anchoring sweeps existing semantic intervals once; source
storage is bounded to 8 MiB, 100,000 documents and 16 MiB of term text (object
allocation overhead is additional). It does not infer relationships. This opt-in
path needs end-to-end relevance evaluation before becoming the default.
Acknowledgement currently suppresses exact source windows, not arbitrary overlapping
intervals or symbol inventories. Current identities/diagnostics remain self-contained.
The server cannot verify what a client still retains: truthful acknowledgement and
reset after compaction are client responsibilities.

Review shares the full immutable semantic snapshot to preserve historical consumers,
while copying text only for explicitly selected files. The 128 MiB limit accounts
serialized snapshot plus retained text conservatively, not exact heap size. Its
bounded line synchronization can fall back for ambiguous edits. Formatting recognition
preserves significant line breaks and literals, ignores empty lines outside literals,
and is disabled for indentation-sensitive Python. No language-specific parser is
substituted for semantic resolution. Contract/initializer/global uncertainty expands
conservatively; declaration moves remain explicit added/removed identities.

For review declarations longer than 80 lines, edit_context prioritizes the declaration line and actual changed hunks/containing AST statements, with labelled hunk-line fallback. Full_evidence remains an explicit bounded expansion. Other large primary declarations expose bounded/truncated ranges and precise snippet recovery.

Hashing telemetry distinguishes index source/dependency/provider asset work from intent capture/render verification. Primitive snippet and lexical verification work are currently outside these cumulative counters; lexical response reports its bounded index source bytes/build work. Counters are observability of these scopes, not an exhaustive process I/O audit. Client context accounting matches exact retained windows; partial interval overlap remains an explicit measurement limitation.
