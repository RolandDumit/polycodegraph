# T6 — model verification prerequisite and protocol

The implemented retention contract has deterministic insertion, acknowledgement,
identity, compaction, rehydration and fallback tests. End-to-end model savings
after compaction and in long tasks are **not verified**. The generic MCP relay
continues to return self-contained responses with retention disabled.

## Installed Codex client audit

The experimental JSON schema was exported from installed Codex CLI 0.159.2
without authentication or model turns. Its inspected artifact hashes and
findings are recorded in [the capability audit](t6-client-capability-20261008.json).
`thread/compact/start` accepts a thread ID; the compaction notification reports
thread/turn identifiers, not surviving exact source windows. Reading thread
turns/items exposes recorded history. `thread/inject_items` appends raw items;
`turn/start.additionalContext` supplies fragments but does not certify their
continued exact presence after backend history processing.

The `thread/resume.history` field is explicitly labelled by the installed schema
`[UNSTABLE] FOR CODEX CLOUD - DO NOT USE.` It is not used to implement an assumed
context owner. No compaction endpoint was invoked: backend compaction may make
additional model calls and no such budget was authorized.

Inference from these available contracts: the normal app-server/MCP harness
does not offer the actual retained-set acknowledgement required by T6. A log,
successful tool transmission, fragment submission or model statement is not a
replacement. This is a limitation of the inspected client integration, not a
claim that every future Codex client lacks such a capability.

## Required executable experiment

A supported client binding must own or inspect the complete actual model input
at the insertion boundary, including backend masking and compaction. It must
verify full source bytes/window identity in that input before acknowledgement,
reset the epoch on any removal or compaction, and revalidate references at final
insertion. If that boundary is unavailable, run self-contained collections and
record the retention experiment as unsupported; do not manufacture acknowledgements.

Once such a binding is available, freeze two long controlled tasks distinct
from G5 and compare three treatments: self-contained collections; acknowledged
references with full history; deterministic masking of old observations with
explicit self-contained rehydration. Use fresh contexts and balanced order with
replicas. Include initial offers, every repeated collection, all later requests,
cache loss, reasoning/output, retries/errors and rehydration in whole-task cost.
Every model turn and any model-generated compaction summary requires its own
explicit budget before launch; no permanent summary call is implied.

The timeline must cover repeated unchanged windows; source changes; new
generation/health/environment/root; changed review baseline; explicit eviction;
and compaction between preparation and insertion. Static independent oracles
must detect stale code and wrong edits. After every invalidation, the response
must be self-contained or reference only source actually present in the new epoch.
Compare accepted whole-task attributable allowance first, retaining the raw
usage categories and request counts; absent quota attribution stays unknown.

This is a prepared specification, not a launched model campaign or passed gate.
There is no new T6 AI allocation. Finishing G5 does not close T6, and a stable
release must explicitly retain this unverified experimental limitation unless
the required binding and model campaign are completed.
