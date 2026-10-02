# Intent context API decision — 0.7 development

Base: v0.6.0, `fff953388d089ae89ab0b260fec05a8326c02b69`.
The user explicitly requires all ten intents across all ten languages in 0.7.0,
superseding the initial four-intent tranche. Capabilities must remain honest: an
intent can return partial/unsupported where a provider lacks required evidence.

Extend `inspect_change` with optional `intent`, typed `options`, `budget`, `cursor`.
Without intent preserve the 0.6 response/defaults. Keep sixteen MCP tool names.
The planner uses graph functions/indexes on one reconciled snapshot, never MCP
subcalls. Intent output does not depend on the response profile; full/compact
primitive APIs remain available. Unknown/incompatible options fail before indexing.

Initial defaults: 12,000 Unicode characters (serialized result, including metadata),
40 evidence records, 12 files, depth 2; bounded traversal. Pages share symbol/edge
rows and merge snippet windows. Every distinct site retains its evidence record.
Cursor tokens are opaque session handles, bound to exact arguments, budget, root,
generation and health; TTL five minutes. Source text is hash-validated before
publishing every page; stale data requires restart. No silent partial publication.

Review baseline: explicit `options.capture_baseline: true` before editing;
subsequent `options.baseline` compares only explicit `options.files` (or target
file). Session-only immutable snapshots, TTL ten minutes, at most two baselines
and 128 MiB retained serialized-snapshot cost. Evicted/expired tokens require
restart. No automatic Git history, patches, build/test execution or acceptance.
Removed/added IDs remain distinct unless compiler evidence proves correspondence.

Capabilities: all ten catalog intents are exposed through this single entry point.
Rename, change_signature, find_tests and review_change operate on
resolved graph evidence for all ten languages. Parameter/accessor links, test-case
identity, exact rename spans and hypothetical type compatibility are separately
reported; absence is partial, never invented from names. Dart Analyzer may add
intent-only metadata, preserving primitive nodes/edges and IDs. Other providers
are generalized only with their language fixture verification. Naming-based test
candidates remain heuristic even when their graph path is resolved.

Verification: frozen 0.6 compact baseline and original Presenza sources; evidence
inventory before edits, no model runs. Account for all pages, snippets, errors,
schema growth and startup/search/status separately. Target: equivalent rename
context within three collection calls and at least 25% fewer serialized evidence
characters. Passing this gate does not establish token savings. The consumer
checkout/package stays untouched; deliver its integration as a reviewable patch.
No commit, push, PR or release is implied by this implementation task.
