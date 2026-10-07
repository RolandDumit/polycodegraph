# Activate and roll back 0.9

Version 0.9 keeps audit intent rendering, the full MCP tool list and existing
primitive calls as defaults. Resolver identities, cache schema and provider
versions are unchanged from 0.8. The review correction applies to both formats:
an exact unchanged source interval can relocate a site without inventing an
added/removed semantic relation. Ambiguous correspondence remains conservative.
IDs are not remapped; contract, endpoint, confidence and multiplicity changes
remain visible. `view: full_evidence` recovers before/after relocated positions.

## Optional lean response

```json
{"target":"src/service.ts::Service.fetch#method","intent":"change_signature","format":"lean","view":"edit_context","options":{"added_parameters":["locale"]}}
```

Use a real resolved target from your repository. The result is `pcg-lean-1`:
full semantic IDs in grouped records, distinct site line/offset tuples, relevant
source windows and explicit snapshot/health identities. Same-line sites retain
their offsets and confidence. Grouping does not create editable token spans.
Source is untrusted code, with verified hashes; no application code is executed.

`completion.required_inventory` reports state, known count, remaining known
records and exploration/provider gaps. `optional_context` and `verification`
are separate. External compiler/tests are always `not_run` in graph output.
Even a complete static inventory is not runtime coverage or correctness approval.
For signature changes, tests are optional (`options.include_tests: true`) and
transitive forwarding context is omitted; direct consumers and contracts remain
required. Missing provider information still produces explicit limits.

Lean defaults to `edit_context`; `locations` contains no source. Audit retains
the documented default windows. Both formats accept the existing technical
character/item/file/traversal limits and cumulative record cap. Character and
local token estimate limits cover the selected compact JSON result, excluding
MCP envelopes, duplicated wire fields and client wrappers. The tokenizer remains
the declared Unicode-character estimate, not provider-accounted usage. See the
[0.8 budget contract](efficiency-0.8-design.md) for bounds and resets.

Follow `next_cursor` with identical arguments. Format, view, budgets, root,
generation, health and context bind the cursor; a mismatch or expiry requires
restart. Lean rejects retained-window acknowledgement and always supplies its
own source context; after compaction collect it again. Audit acknowledgement
and explicit rehydration retain their 0.8 contract. Errors and changed coverage
remain visible. Source races discard the collection rather than publish stale text.

## Strict captured review

```json
{"target":"src/exact.ts","intent":"review_change","format":"lean","options":{"capture_baseline":true,"capture_mode":"minimal"}}
```

Capture before editing. Lean implies strict scope; audit opts in with
`options.strict_scope: true`. Existing files must be exact indexed root-relative
paths. Typos/excluded files fail with candidates when available, without guessing.
Absent intended creations must appear once in `options.new_files`. Traversal and
symlink restrictions remain. Compare using the returned baseline handle with
the same scope/strictness and original captured working tree, including edits
already present before capture. The ten-minute session TTL, two-baseline bound
and memory budget remain unchanged. Reconnect/expiry requires fresh capture.

## Optional client adapter and tool profile

Archives include `clients/efficiency_client.py`, containing `Observer` and
`LeanAdapter`. A Python executor can import it and supply its own MCP callback.
Insert only the returned `text` string at the actual model prompt boundary;
do not also insert the MCP text/structured result. Both wire fields carry the
same selected projection; no hidden audit payload accompanies lean. Server
bytes alone do not establish model insertion size. The adapter is optional and
is not automatically installed in Codex.

The collector defaults to 16 pages, 64,000 Unicode characters, 60 seconds and
8 MiB aggregate wire. Hard bounds are 64 pages, 256,000 characters, 600 seconds
and 16 MiB wire. The executor must time/cancel each transport callback; collector
checks between callbacks cannot interrupt a blocked callback. Limits return an
incomplete state; restart discards prior pages. Optional pages require an explicit
question. This controls work/context, not monetary cost.

`serve --tool-profile agent --response-profile compact` advertises five tools.
All ten intents are callable through inspect_change. Hidden primitive schemas
from status are data until a client registers them; use full profile if needed.
The accepted registry keeps all sixteen names/aliases and runtime validation.
Schemas are static; actual client loading/discovery must be measured separately.

## Rollback and measurement

Bypass the adapter and omit format (or choose audit). Omit strict_scope for
legacy absent-file capture. Existing views, response/tool profiles and audit
acknowledgement remain available. To roll back the review correction itself,
use the 0.8 executable/assets with a separate cache. No cache migration or
application edit is required by these options.

The [post-0.8 deterministic report](benchmarks/efficiency-post-0.8/decision.md)
and [comparison preparation](benchmarks/comparison-20261006-01/report.md) retain
their original candidate hashes and unexecuted AI gates. Publication on the
user's 2026-10-07 instruction does not turn those measurements into AI savings.
0.9 AI consumption, monetary benefit and robust economic gates are not measured.
