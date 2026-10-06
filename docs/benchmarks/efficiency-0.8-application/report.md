# Application pilot — 2026-10-06

All 18 fresh task executions were independently accepted. The registered primary
metric is provider-accounted uncached input per accepted task, not money. In this
pilot rc.1 uses **13.7% less than 0.7**, but **89.7% more than no graph**. The local
task also increases 54.5% despite zero graph calls. G2 fails on incomplete client
telemetry, so these descriptive ratios do not establish robust or causal savings.

[Public aggregates](results.json) contain the checked usage totals and identities.
Private application sources, task prompts, SDK paths, conversations, patches,
oracles and logs remain ignored. The source campaign manifest SHA256 is
`64547b0d5785032abf6f9c0866ba2f7112bd89c8e1752b5d78fdd09864cdeb1b`.
The release coordinator recomputed all 18 usage receipts with the frozen cumulative
parser and checked every aggregate component and per-task primary against them.

## Conditions and scope

A has no graph MCP/schema/instructions. B uses the exact local locked v0.7.0
build, compact responses, 16 tools and its original harness. C uses the frozen
0.8.0-rc.1 build, compact/agent, five tools and updated routing. Binary digests
and result-source hashes are in the aggregates. The final 0.8.0 fixes request
metadata compatibility and documentation; it has not been remeasured as AI C.

The model is gpt-6.1-sol, effort high, Codex CLI 0.159.2. Six task classes use
ABC, ACB, BAC, BCA, CAB, CBA, one replica per cell and at most 20 minutes.
Copies/context are fresh; graph caches are cold. Bubblewrap mount/proc probes
verify filesystem/process isolation and A's graph exclusion. Network is shared
for model authentication. Prompt cache is observed, not controlled. Three task
pipelines run concurrently; summed durations are not campaign wall time.

The same B/C adapter removes only request-envelope `_meta.progressToken` for
tool discovery. It preserves schemas, cursors, arguments and responses. It was
needed by both tested binaries; final 0.8 accepts this metadata directly. This
product correction does not retrospectively change pilot results.

## Accepted tasks and uncached input

| Task | Accepted A/B/C | A | B | C | C/A | C/B |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Known local edit | 1/1/1 | 5,715 | 37,448 | 8,832 | 1.545 | 0.236 |
| Ambiguous rename | 1/1/1 | 29,320 | 46,466 | 45,421 | 1.549 | 0.978 |
| Public signature | 1/1/1 | 19,790 | 51,467 | 78,647 | 3.974 | 1.528 |
| Symptom bug | 1/1/1 | 22,476 | 53,763 | 25,388 | 1.130 | 0.472 |
| Branched flow | 1/1/1 | 37,768 | 71,130 | 46,262 | 1.225 | 0.650 |
| Large-file review | 1/1/1 | 36,764 | 73,516 | 83,438 | 2.270 | 1.135 |

| Aggregate | A | B | C |
| --- | ---: | ---: | ---: |
| Accepted tasks | 6 | 6 | 6 |
| Uncached input / accepted | 25,305.5 | 55,631.7 | 47,998.0 |
| Input total | 1,010,585 | 3,178,206 | 1,788,788 |
| Input uncached | 151,833 | 333,790 | 287,988 |
| Input cached | 858,752 | 2,844,416 | 1,500,800 |
| Output | 19,311 | 30,862 | 29,676 |
| Reasoning (subset of output) | 3,632 | 6,285 | 7,297 |
| Model requests | 47 | 81 | 58 |
| MCP tool calls | 0 | 114 | 25 |
| MCP errors | 0 | 11 | 2 |
| Cursor pages | 0 | 46 | 6 |
| Summed task duration, s | 540.8 | 1,103.3 | 951.1 |

Cache creation is zero as exposed by these counters; monetary cost is unavailable.
Errors/internal corrections remain in usage. Prior invalid campaigns are retained
separately: one has unknown costs, another 147,620 observed uncached tokens.
Adding that to this pilot gives a partial operational subtotal of 921,231; it
excludes unknown costs and unmetered coordination/verification/preparation. It is
not a per-condition experimental mean. No character/token/quota conversion is made.

## Gates and correctness

G0 passes identity checks; G1 passes the relevant application/Linux subset only.
Independent verification covers rename consumers and wire keys, signature forwarding,
bug behavior, trace evidence/branches, captured review baseline and local edit scope.
Existing lint issues remain; full Flutter analysis and native iOS/backend/device
coverage are not verified in this pilot. Release platform CI is a separate gate.

G2 **fails**: per-response usage and isolation pass, but complete schemas at each
model request and comparable new/repeated/rehydrated external/source-window ledgers
are unavailable. Code-mode response transformations are partially observed rather
than inferred from duplicate transport objects. Unknown counters remain null.
G3/G4 are **not_measured**. The numeric target versus A and local non-regression
condition fail descriptively; a qualified economic gate is not passed.

## Next optimization questions

Signature and review regress versus B as well as A. The signature run added an
accessory review and large budget expansion; review first captured an empty scope
from a short path, then recovered the proper root-relative path. Trace initially
called the wrong advertised tool before recovering. These costs are included.

Priorities are complete client telemetry, source/path feedback, selective accessory
review, and initial schema/instruction overhead for known local work. A future
comparison should freeze one intervention at a time and preregister replicas and
holdout. This pilot cannot attribute the local overhead solely to graph schemas,
harness, prompt caching or solver variability. No new ablation was run for release.
