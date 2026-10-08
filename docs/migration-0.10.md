# 0.10 development: selective client integration

The first tranche implements T0–T2 from the [research plan](token-efficiency-research-plan-0.10.0.md).
It is opt-in client work, not a released 0.10 version or a measured AI saving.
The package is marked `0.10.0-dev.2`. Native defaults remain compatible; the
selected workflow integration opts into intent source selection. See the
[development milestones](development-0.10-dev2.md).

## T3: independent source selection

Native `inspect_change` accepts optional `source_policy: intent`. Without an
explicit `view`, rename selects locations, signature changes select contracts,
and other intents select edit context. An explicit view always wins, including
full evidence. Inventory, resolver confidence and distinct offsets are preserved.
Locations are an inventory; ambiguity, serialization/wire names and actual edits
can still require direct source reads. Bug diagnosis retains edit-context strings
and comments; no global comment removal is applied.

Optional `budget.max_source_chars` (0–100,000) caps the sum of emitted source
text characters per page, independently of inventory. Truncation stays visible;
hash validation remains unchanged. If the whole response does not fit, optional
source shrinks before the inventory page. Native omitted options retain old
behavior. Selected workflow schemas expose the policy and apply it explicitly
at collection; explicit views remain respected.

The client adapter optionally accepts `max_input_tokens`, `count_tokens` and
`tokenizer_id`. The caller supplies a tokenizer for the actual destination model;
the final insertion text must fit before insertion. This counts that text only,
excluding model request wrappers, schemas and prior history. There is no bundled
universal tokenizer. Native `max_tokens` remains a characters/4 estimate.

## T4: bounded seed discovery

Lexical `search_symbol`/`search` constructs the effective file/language scope
before applying source, line and term caps. The immutable graph owns a bounded
two-entry scope/config cache; generation/environment replacement discards it.
Excluded or partly indexed files have bounded reason previews and counts;
incomplete discovery reports a null total, never proof of absence.

Optional `group_by: anchor` groups matches before pagination, retaining exact
anchor IDs, a match count and up to three decisive line locations. Default `line`
keeps per-line results. Use `anchor` with line mode to page all that anchor's
matches. File-level unanchored matches remain lexical candidates.

An inverted term lookup preserves default overlap-IDF scoring. Optional
`ranking: bm25` is a binary-term-presence BM25 ablation with name/path weighting;
it does not claim full term-frequency BM25 or proven end-to-end superiority.
The overlap baseline remains the default. Retrieval scores never become semantic
confidence or create graph edges; bounded expansion uses existing resolver edges.

## T5: task coverage and global limits

Opt-in intent source policy also exposes `task_coverage` in lean output. It
separates delivered known inventory, bounded traversed-file previews and local
diagnostic/unresolved/provider limits from global health. An error observed in
a traversed file is relevant; an error elsewhere has unknown relevance, because
dependency/resolution effects cannot be excluded from its path alone.

Task coverage remains unknown when no provider-backed proof covers the question.
The existing conservative required-inventory completion is unchanged. Exhausted
pagination does not repair global coverage: explicit recovery guidance recommends
reporting the limit or inspecting relevant diagnostics, rather than repeating
pages. Root/generation/health/environment/source/baseline validation is unchanged.
The full/agent server catalogs, accepted primitive tools, audit/lean formats and
semantic resolver contracts remain available.

## Ordinary MCP clients

The package includes an optional stdio entrypoint, `clients/efficiency_mcp.py`,
requiring Python 3.11 or newer. Register it explicitly at task start with your
MCP client's usual server configuration. For a rename task requiring discovery:

```json
{
  "mcpServers": {
    "polycodegraph": {
      "command": "python3",
      "args": [
        "/absolute/install/clients/efficiency_mcp.py",
        "--root", "/absolute/project",
        "--profile", "rename",
        "--discovery"
      ]
    }
  }
}
```

Replace the example paths and Python command for your host. The installed relay
finds the adjacent native executable; when running `tool/efficiency_mcp.py` from
source, also provide `--binary /absolute/path/to/polycodegraph`. An optional
`--config` selects the ordinary native runtime configuration. Prepare trusted
provider assets beforehand; the relay runs native `serve`, never setup, project
scripts or application code. It does not edit persistent client settings.

Choose any canonical intent as `--profile`; omit `--discovery` for a known stable
target. Workflow profiles advertise one typed canonical `inspect_change`, use the
minimal initialization guide and collect lean pages into one text content block.
The returned format may be collection-1 when fusion is unprofitable. Full/agent
profiles preserve their canonical catalogs, original initialization guide and
direct native results by default. `--instructions original|minimal|none` and
`--collection collection-1|collection-2` support explicit ablations; `direct` is
also available for full/agent. These settings remain fixed for the session.

For a local task, omit the PCG registration entirely. A `local` relay profile is
available for protocol checks: it starts no native process, advertises no tools
and returns no PCG guide. Registering even an empty server can have client costs;
its absence is the no-graph campaign condition.

If collection stops at a cap, repeat the original arguments with the returned
`cursor` in the same session. This explicit recovery returns one canonical
`pcg-lean-1` page, as one text block, preserving its next cursor and limits. It
does not claim that all earlier/later pages are present. Root, snapshot, health
and cursor expiry still have native validation. Review baseline handles remain
in that same private native session across source edits.

The frontend caps input frames at 1 MiB and admitted work at 64 jobs. Calls are
serialized while cancellation remains readable; EOF drains admitted calls.
Backend frames are capped at 16 MiB, request IDs are never reused, and late
cancelled replies are discarded. Backend EOF/invalid framing requires a new
session, preserving the visibility of lost baseline state. Shutdown first
allows native EOF draining, then bounds cleanup of its owned process tree.
Protocol output goes only to stdout; diagnostics go to stderr.

Optional `--telemetry /private/new-receipt.json` creates an exclusive private
hashed receipt, with bounded events and no raw arguments/source/prompts. It
records advertised schema, offered guide and prepared responses. Actual model
registration, provider insertion, usage and external model runs remain unknown:
emitting an MCP response does not observe its later prompt materialization.

## T0: accounting and boundaries

`Observer` records bounded collection, call, result, insertion and outgoing model
request events. Call `request_model` only at the real outgoing request boundary,
with the actually materialized schemas/instructions when available. A startup
hash does not establish a later request's surface. Unknown materialization is
`null`. Events contain hashes, sizes, tool names and correlation IDs, not source,
instructions, arguments or credentials. Publish summaries; keep receipts and
correlation events in ignored campaign storage.

The source ledger accounts for partial overlaps by line bodies and separators,
preserving Unicode and CRLF. Compaction explicitly clears retained identities;
later observations are rehydrated. It never suppresses source. The ledger stores
at most 8,192 identities by default (hard configurable ceiling 65,536), and
events/source entries are separately capped at 8,192. Overflow and truncated or
unidentified text make accounting incomplete; they never become zero cost.
Line prefix overlaps in truncated source are unknown, rather than an exact count.

`comparison-v2` uses `total_tokens_per_accepted_task`: every attempt's total
provider input (including cache reads/creation as defined by that provider) plus
output, divided by accepted cells. `uncached_input_per_accepted_task` is mandatory
supporting output. Reasoning remains a subset of output. Zero accepted cells or
unknown attempt usage produces `null`, not zero. `usage-v2` preserves unavailable
cache creation as `null`. Cumulative Codex receipts use the existing frozen parser,
including duplicate/reset validation; complete usage must be explicit in v2.
Historical comparison-v1/post08-v1/token parsers and their primary metric stay
selectable. The existing runner's authorization, serial schedule, journal,
isolation, oracle and after-attempt budget checks still apply.

Free replay reuses `tool/efficiency_replay.py --lean-pages FILE --output FILE`.
Multiple `--lean-pages` inputs compare collection-1, fused and selected sizes,
inventory equality and static schema/instruction ablations. These are local
Unicode characters/UTF-8 bytes. No exact tokenizer or provider usage is inferred.

## T1: static workflow exposure

`efficiency_workflow.workflow_surface(actual_catalog, profile)` derives schemas
from the actual `tools/list` result. `profile="local"` returns no PCG tools and
an empty PCG guide; do not connect/register a PCG server or load its instructions
for that task. An internally serialized empty list is not a graph tool schema.

`full`/`agent` retain the original tool specs. Any of the ten intent names selects
one canonical `inspect_change`, with only that intent's typed options. Its intent
and lean format are fixed by enum; collector-owned cursor/context and legacy
pagination arguments are absent by default. The relay opts into `continuation=True`
to expose the canonical cursor for explicit recovery. `discovery=True` adds canonical `search_symbol`
at task start only when target discovery is needed. Required fields, bounds and
options come from the canonical catalog; the server remains the authoritative
argument validator. There is no new server `tool_profile` value, dynamic
registration claim or generic CLI query command.

The executor must actually register the selected surface and apply its returned
minimal guide, preserving the repository's own instructions. Merely creating a
surface dictionary does not prove model exposure. Clients unable to replace
schemas/instructions retain their fixed overhead; use ordinary MCP and report it.
See the [minimal consumer guidance](harness-workflow.md).

## T2: fused collection

`pcg-lean-collection-2` is an opt-in client format. The server still returns
`pcg-lean-1`. Native lean snapshots now additionally expose
`environment_fingerprint`; this is additive identity metadata, not a resolver or
storage change. Older snapshots lacking it remain identifiable only through their
existing root/generation/health fields; explicit environment identity is unknown.

The fused envelope contains common metadata once, grouped `records`, merged
`sources`, `page_states` for varying metadata, last-page `completion`, aggregate
source incompleteness/limit causes and the final `next_cursor`. All unknown future
metadata is retained. A `request` preserves the original typed arguments.

An optional `dictionaries` object holds complete symbol IDs, files and reasons.
Only record `source`/`target`, `file`, and `reason` become integer indexes into
their respective dictionaries. Target/facts/detail handles stay canonical.
Use `expand_records` to decode or `normalized_inventory` to compare collections;
never send a dictionary index to a server as a stable ID or detail handle.

Grouping requires equality of every non-site attribute, including confidence,
phase, sections, reason and provenance. Every site tuple, offset, detail handle
and repeated occurrence is retained. No top-k filter is applied to required sites.
Page offsets, record counts and cumulative required counts must agree.

Source merging requires the same snapshot, file/hash, phase/view and compatible
window metadata. Only complete compatible overlapping/adjacent windows merge;
truncated windows remain explicit. Contradictory visible overlap bytes, changed
source hash, snapshot/view or conflicting detail handles discard the entire
partial collection. Before/current windows and homonyms remain distinct.
Missing hashes cannot justify source merging. Source hashes were checked by the
server; this client does not reread files or execute indexed application code.

The selector compares Unicode serialization lengths for collection-1, inline
fused and dictionary fused, including their envelopes. It picks the shortest;
collection-1 wins ties and remains the fallback for small/unprofitable responses.
Consumers must dispatch on the returned `format`, not the requested optimization.
No silent changes are made to either old format.

## Binding, limits and rollback

For an async executor with a cancellation-safe MCP transport:

```python
surface = workflow_surface(actual_tools_list["tools"], "rename")
# Register surface["tools"] and apply surface["instructions"] at task start.
observer = Observer()
binding = AsyncLeanBinding(async_mcp_call, observer, surface)
result = await binding.collect(
    {"target": stable_id, "intent": "rename", "format": "lean"},
    insert_one_text_into_client_context,
)
# At the actual subsequent request, observe the materialized surface, not a guess:
observer.request_model(request_id, actual_schema_text, actual_instruction_text)
```

`async_mcp_call` must cancel/drain abandoned IDs or disconnect on coroutine
cancellation. Wrapping a blocking RPC in an uncancellable background thread is
insufficient. The binding enforces the deadline during the call, serializes one
collection, and records insertion only after the synchronous insertion callback
succeeds. Caller cancellation inserts nothing. A timeout produces an explicit
incomplete result. Native smoke transport also enforces deadlines while waiting
for a response and requires reconnect after an abandoned request.
Async insertion callbacks are rejected before collection. The callback must
return `None`; failure or an incompatible return marks insertion-boundary
accounting incomplete, without committing source as inserted.

Defaults are 16 pages, 64,000 insertion characters, 60 seconds and 8 MiB received
wire serialization; hard ranges are 1–64 pages, 3,000–256,000 characters, 1–600
seconds and 1 KiB–16 MiB. All raw pages count against the wire budget, even when
their fused form is smaller. Stored pages, transforms and ledgers are bounded
by those caps; this is not an independently measured Python heap/RSS ceiling.
The time budget bounds RPC waiting, with cooperative cancellation between
deterministic transformations; synchronous transformation/insert CPU is not a
preemptive deadline. Errors and expired handles remain visible and counted.

Collection ends when required sites are exhausted unless signature tests were
explicitly requested; provider/exploration gaps still make inventory incomplete.
A page/character/wire cap needs an explicit new collection with a larger client
budget, or a canonical MCP continuation with the full original arguments. The
workflow collector owns pagination and rejects caller-supplied cursors by default;
the relay's explicit recovery path forwards a single canonical page. It does
not automatically retry, increase caps or claim compiler/test verification.

Rollback: use ordinary server full/agent MCP, audit/lean directly, or the existing
`LeanAdapter` collection-1 default. Fused use requires `deadline_call` or the async
binding. These modules are packaged together in `clients/`; no runtime is installed
into Codex or any other client by the server. End-to-end usage, real model use of
the treatment, rereads, holdout and macOS UIKit remain separate release gates.
