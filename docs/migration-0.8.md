# Activating and reverting PolyCodeGraph 0.8

Version 0.8.0 promotes the tested `0.8.0-rc.1` feature set and accepts standard MCP
request metadata, fixing direct tool discovery with clients that send progress tokens.
The application pilot measured rc.1, not this final metadata fix. Existing primitive
calls and intent calls without `view` keep their documented source-window defaults.
`detail` still selects primitive profiles; it is not silently reinterpreted for intents.
Restart the MCP process to load a new binary/schema. Leave `tool_profile: full`
(the default) for an unchanged advertised registry, or choose `agent` explicitly:

```json
{"response_profile":"compact","tool_profile":"agent"}
```

The CLI equivalent is `serve --tool-profile agent`. Five tools are advertised:
status, search_symbol, inspect_change, snippet, index_repository. All sixteen
accepted tool names, including search/blast_radius aliases, retain validation.
Schema discovery does not index source files. Discover a specific advanced schema with `status(section: tools, tool: callers)`;
clients that cannot load discovered tools should keep the full profile. Discovery
has a round trip and its returned schema also costs context; smaller tools/list
alone proves no AI saving.

Update the consumer [harness](harness-AGENTS.md). A known local edit can use zero
graph calls. An unambiguous target goes directly to an intent. Start with explicit
`locations` for required site inventories, `contracts` for declaration headers,
`edit_context` for the main declaration/containing statements, and `full_evidence`
for deeper source evidence. Headers/statements use provider boundaries when
available and labelled bounded fallbacks otherwise. AST records are not certified
editable token spans. Optional understanding context can be expanded for a concrete
question; required inventories must remain enumerable.

```json
{
  "target":"lib/domain.dart::Repository.fetch#method",
  "intent":"change_signature",
  "options":{"added_parameters":["locale"]},
  "view":"edit_context",
  "budget":{"max_chars":12000,"max_items":40,"max_files":12,"max_traversal":10000}
}
```

Capture review state *before* editing with `intent: review_change`, a file target
(or explicit options.files), and `options: {capture_baseline: true, capture_mode:
minimal}`. Retain facts.baseline.handle, then compare with options.baseline and
the identical file scope. This captures the current working tree, even when already
modified. It is never implicitly HEAD. Handles are session local, at most two,
expire after ten minutes, and together have a conservative 128 MiB accounting bound.
Only scoped source text is copied; historical semantic snapshots are shared.
Absent capture_mode retains the previous context capture. Missing/scoped/expired
handles request a new explicit baseline; they cannot recreate an old state.

Old omitted/truncated mean “absent from this page”. Use evidence.page_count,
remaining_after_page and next_cursor for progress. The last page has zero remaining
discovered records. collection_complete additionally requires no work/depth/collection
limit, and applies to the requested static scope, never runtime safety. Inspect
exploration_incomplete, source_windows_incomplete and limit_causes separately.
A too-large record/metadata returns a useful error without advancing a cursor:
start a new request with a suitable view/budget, or retrieve source/diagnostics
precisely. Do not loop on the same failed request.

Optional max_tokens uses `unicode_chars_div4_v1`: ceil(Unicode characters of the
entire compact JSON result / 4). This is an estimate without a model tokenizer;
256–32,000 are accepted. max_chars (3,000–100,000) remains a technical guard and
both constraints apply. 512/1,024/2,048 are benchmark points; a small estimate may
not even fit metadata. Neither field includes schemas, client wrappers or model
usage. max_collection_items (1–100,000) caps cumulative evidence records across
pages; its exhaustion is explicit and needs a new request with a larger cap.
No cumulative *token* guarantee or subscription quota accounting is provided.
Changing any budget, view, options or acknowledgement set requires a new request;
cursors bind root, generation, health and all arguments and expire after five minutes.

Clients may acknowledge exact retained source windows. Copy root_id, generation,
health_fingerprint and environment_fingerprint from response.context, add a nonempty
epoch and known_windows IDs (at most 256). Only source text is suppressed, never
site identities or new diagnostics. Source views include source_hash for client
measurement; locations without acknowledgement does not add unused window metadata.
After compaction/new agent/conversation reset epoch and acknowledgements, or send
rehydrate:true. Invalid identities fall back to self-contained context. The server
cannot detect a dishonest/stale acknowledgement at unchanged identities. Older
clients always receive self-contained results. Arbitrary overlapping intervals,
symbol inventories and headers are not deduplicated across requests in this version.

Opt into content discovery with `search_symbol(query: ..., mode: lexical, expand:
none|dependencies|callers)`. Default name/ID lookup is unchanged. Queries are limited
to 8,192 bytes/64 distinct terms. The bounded line-document/IDF baseline handles
camelCase, snake_case and paths, and anchors to existing semantic declarations.
Matches/relevance never create resolved edges; expansions retain provider confidence
and offsets. Use an anchor directly for an intent rather than another search cycle.

SQLite schema 4 reads schema 3 and adds an idempotent edges(file) index. Every write
has an independent transactional revision, including health-only changes. To roll
back to 0.7, restart its binary and restore its original harness/configuration, removing
new options. Use a separate derived-cache directory: older releases will reject or
rebuild schema 4. Source files and previous branches/stash need no transformation.

See [measurement protocol](benchmarks/efficiency-0.8/protocol.md) and
[actual gates/results](benchmarks/efficiency-0.8/report.md). Payload estimates and
server runtime do not establish cheaper accepted AI tasks.

Review source views currently render current-state text; removed declarations/files retain before IDs, sites and hashes, but captured historical source text is not exposed as a separate source retrieval API. Line synchronization/classification and missing provider enrichment remain conservative limits, not language-level semantic equivalence proofs.
