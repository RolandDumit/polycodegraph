# Response profiles (0.6.0)

Compact responses are opt-in; whole-task AI token savings remain unverified. `response_profile: legacy`
is the default. `response_profile: compact` (YAML/JSON), or the CLI override
`--response-profile compact`, selects smaller MCP responses. No provider setup,
source coverage, invalidation, impact depth or explicit limits change.

Every tool accepts `detail: compact|full`; `full` uses the legacy response and
defaults for that call. Search defaults to 10 rows, relationship lists to 20,
architecture to 5, and implicit snippets to at most 30 lines in compact mode.
Explicit line windows retain the configured hard budgets. Tables retain stable
IDs, sites/confidence, generation, total/offset/next_offset and report omissions.

Compact status and index_repository return outcome (`ok|issues|unchanged`),
generation, freshness, counts, coverage and a health fingerprint independent of
generation. Health includes diagnostic severities, skipped/unresolved/dropped
counts and availability of the providers used by indexed files. An unchanged
index still reconciles all tracked source/environment hashes. It never means
that the index is healthy. New/changed errors have bounded previews and counts;
diagnostic omissions and message truncations are explicit.

Details are available over the existing MCP `status` tool: `section` accepts
`diagnostics`, `skipped`, `providers`, `update`, `metrics`, or `architecture`.
Diagnostics/skipped/update accept `offset` and `limit` (20 by default in compact
mode). Every page has generation, health fingerprint, total and next_offset.
Restart paging when either identity changes. `update` pages each of changed,
deleted and reindexed files from the most recent performed update (including an
explicit unchanged scan), with its own generation. `providers` and `detail: full`
are explicit opt-ins to runtime details which may contain local paths. Diagnostics
pages return `items: [{file, diagnostic}]` with the original diagnostic object
including complete messages and unknown fields; envelope metadata never
overwrites a provider's own `file` field. Preview omission does not discard the original.

Search `file` is a slash-separated indexed path prefix relative to the graph
root, not to a nested package. Nonexistent prefixes return an empty table with
`file_filter.valid: false` and a warning. A unique suffix match may suggest an
indexed corrected prefix, never apply it. Ambiguous matches have no suggestion.
Valid prefixes with no name/type matches return `file_filter.valid: true`.
Absolute/traversing paths are rejected; no paths outside the root are read.

Schema extensions are explicit and unknown arguments still fail safely. Existing
legacy outputs are preserved except invalid path warnings/rejection. Compact
coverage metadata records static precision limits; smaller pages do not assert
completeness. `inspect_change` already includes callers, implementations and
impact: request those again only for additional pages/limits or changed evidence.
Session duplicate/overlap tracking is deferred until traces justify its cost.

Rollback: remove the profile override or set `response_profile: legacy`, then
restart the client's MCP process. The presentation profile is excluded from the
index fingerprint and does not force extraction after the new configuration
hashing has been established. The first reconciliation from a 0.5 cache may
reindex once: graph configuration inputs now hash effective semantic options
rather than raw YAML/JSON bytes. Profile/comment/format edits within an existing
config file then keep semantic identity. Concurrent config edits abort publication
and require retry. CLI compact status stays read-only and exposes `index_current`
and source-change counts; MCP status refreshes before reporting.
When upgrading, use the 0.6.0 native package and restart the client’s MCP process.
To revert core behavior, restore the 0.5.0 package and restart; its derived cache
can be rebuilt if needed.

Byte measurements include one broker-consumed representation (structured JSON
or equivalent text); they do not establish end-to-end AI token savings. The
acceptance experiment requires six fresh runs A/B/C then C/B/A, at least 20%
less uncached input vs no graph, correctness in every run, and no more than 5%
extra cached input/output on average. Absent that evidence compact remains opt-in.
