# Post-0.8 efficiency checkpoint

This is development evidence toward a future release, not a release declaration.
The immutable baseline is final v0.8.0, commit
`64f7dfb0bfcae4f6471ee691dfdc896a34ac785f`. Historical rc.1 model runs
are neither measurements of that binary nor replicas of this experiment.

## Implemented interventions

Review now compares semantic attributes at proven corresponding sites. A bounded,
deterministic map uses exact unchanged lines, unique ordered line anchors and,
within a changed line, unique exact semicolon-terminated fragments. Equal-size
unchanged repeated intervals between anchors retain their ordinals. Crossing
anchors, unequal repeated intervals and indistinguishable duplicate fragments
are not paired arbitrarily. It does not infer symbol rename/move or normalize
whitespace as semantic equivalence. Work is charged against `max_traversal`;
source reads retain the existing byte cap and hash checks.

The provider position contract is absolute UTF-16 units for Dart, Java,
TypeScript/JavaScript; bytes for Go; Unicode code points for Python, Rust,
Swift, Objective-C and Kotlin (native compiler coordinates are converted by
their existing adapters). Lines are one-based. Original CRLF is preserved.
`Edge::key()` and provider identities are unchanged.

The internal comparison classifies unchanged, relocated, added, removed and
uncertain mappings. Relocations keep both positions in `full_evidence` and do
not enlarge the ordinary semantic change inventory. Source hash changes remain
visible. Ambiguous correspondence retains conservative before/current evidence,
with explicit uncertainty and net semantic multiplicity counts. These counts
cannot identify which indistinguishable duplicate survived. A mapping work limit
means incomplete comparison, never absence of changes. Narrow leading blank or
`//` comment edits can prune unchanged declaration context; imports and other
global edits keep the previous conservative context. This is a correctness fix,
not evidence explaining the old application pilot's cost.

Strict capture is opt-in in audit requests and automatic in lean requests.
Existing files must be indexed at the exact root-relative path. Missing files
require an explicit, unique `new_files` list. Failure names the requested scope
and up to three candidates without correction. Excluded files, traversal and
symlinks remain errors. Captures record existing/new counts. The comparison must
use the same scope and strictness as capture. Legacy missing-file capture remains
available without strict mode.

## One experimental integration

The chosen integration is the existing five-tool `agent` MCP profile, with typed
intent operations in the already invocable `inspect_change`, and
`efficiency_client.LeanAdapter`. There is no additional dispatcher catalog, LLM
router, daemon, persistent-schema migration or search redesign. Native stdio
tests invoke an advanced intent through the advertised tool, accept MCP metadata,
recover once from an unknown name, and reconnect. Hidden schemas returned by
`status` are data; clients cannot assume they become callable automatically.

`format: lean` projects the canonical plan deterministically as `pcg-lean-1`.
It keeps full IDs, semantic attributes, every site offset, confidence, verified
source windows and hashes, diagnostics and material precision limits. Common
relation attributes are grouped once; all sites remain listed. Source is
explicitly untrusted data. `locations` deliberately omits source; `edit_context`
is the lean default. Audit/full evidence remains available explicitly.

Required static inventory, optional context and external verification are
separate. Exhausted required pages/traversal, uncertainty and provider failures
remain incomplete. Compatibility cannot be certified by another graph query:
compiler/tests are always `not_run` here. In lean signature requests, discovered
tests are optional and collected only with `include_tests: true`, after required
work. Direct contracts, linked implementations and direct sites remain necessary;
automatic transitive forwarding exploration is excluded. Optional depth limits
do not change required completeness. Legacy behavior remains selectable.

Lean output is self-contained and rejects retained-window acknowledgements.
The observer records bounded exact-source identity observations; it never
suppresses text or claims that a model remembers it. Root/session/compaction
changes do not establish retention. Error and cursor restart envelopes retain
the legacy error contract; the adapter handles them before projection.

The adapter collects at most 16 pages and 64,000 Unicode characters by default,
within hard maxima of 64 pages/256,000 characters. Collection also checks a
60-second elapsed budget, an 8 MiB aggregate wire budget and cancellation between
callbacks (hard maxima 600 seconds/16 MiB). The transport callback must enforce
its own per-call timeout and in-flight cancellation; the collector cannot
preempt a blocking callback. It stops at the last required
page unless optional tests were requested. A changed generation/root/health or
restart discards the entire prior collection. It forwards errors once and keeps
their wire costs. It inserts one bounded collection string, never both MCP
`content` and `structuredContent`. The server's two wire fields both contain
the same selected projection; neither contains a hidden full audit result.
Native local insertion is tested. Codex prompt insertion and tool registration
are **not verified**: the adapter is not installed into Codex by these changes.

## Gates and limitations

F1 regressions and native reproductions are measured independently of AI cost.
F2 is an experimental native integration, not a completed real-model acceptance
gate. The client exposure experiment must confirm or revise this integration
before a paid comparison. Larger schemas can offset smaller answers.
`unicode_chars_div4_v1` remains a local estimate, never provider token usage.
No E1/E2 consumption data, causal savings, general advantage or amortization is
claimed. F3, E3 and holdout work remain conditional and were not implemented.

See [protocol](protocol.md), [deterministic results](deterministic-results.json),
[manifest](manifest.json) and [decision](decision.md). Raw traces, source copies,
SDK paths and build caches remain ignored locally.
