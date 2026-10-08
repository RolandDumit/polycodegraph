# 0.10.0-dev.2 model screening — 2026-10-08

The new screening completed **24/24 solver turns**, with **12/12 static accepted
outcomes in both A and D**, using 556,969 of the separately authorized 1,000,000
uncached-input tokens. No extra solver attempts, preparation AI, judge AI or
external solver retries ran. Temporary credential copies were removed. Economic
cost and internal provider insertion remain unknown.

The candidate is annotated tag `v0.10.0-dev.2` at
`634b6dedf93651bdad98da5b63b7105d9c65d846`; program code is the same as tested
commit `2e40eceecce941aa96048c0bf02bd2614b1df55d`. All 20 platform jobs passed,
including actual Android and UIKit fixtures. The initial UIKit timeout and its
successful same-code recheck remain recorded in the deterministic report.

The user explicitly clarified that +15% total-token overhead belongs to 1.0,
not the 0.10 release milestone. The original savings screening gate still fails;
this does not change the implemented 0.10 milestone or historical results.

## Frozen protocol and actual treatment

[Preregistration](dev2-screening-proposal-20261008.md) preceded paid turns.
Manifest digest: `23979b993db2c9f97ee2d9d6ed7ed6df3f9a662a76a3ef96625b4dc374c62a94`.
Twelve known controlled TypeScript tasks, two per family, one fresh A/D pair
per task, alternating condition order, `gpt-6.1-sol` effort `high`, Codex CLI
0.159.2 app-server. A has ordinary bounded source tools and no PCG. D has the
actual task-specific workflow; neither condition has PCG on local tasks.

All eight dev.2 client modules, provider assets, guides, catalogs, native binary,
measurement tools, task snapshots and independent exact-byte/findings oracles
were frozen. Every native artifact is checked before each turn. No indexed
application code, plugins, package scripts, hooks or generators were executed.

A preparation failure happened before executor entry: copying its file lost the
executable bit, so the process wrapper failed at `os.execv`. No client home,
model session or model call existed. That failed manifest/journal/stderr remain
intact; a fresh preparation with executable checks preceded the 24 paid turns.
This is recorded separately from solver attempts and is not a solver retry.

D issued 28 model-facing workflow calls and 54 native intent requests; 51 native
pages were delivered successfully. Every native request used
`source_policy=intent` with view omitted. A/D made 67/79 model requests inside
their 12 solver turns. All errors and recovery within a turn enter its costs:
A recorded eight tool errors, D seven. Unknown provider transport retry counts
remain unknown. No compaction occurred.

## Product costs

[Complete results](dev2-screening-results-20261008.json) include all provider
input, cached input and output. Reasoning output is a subset of output, not an
additional charge in the total-token metric.

| Measure | A | D | D relative to A |
| --- | ---: | ---: | ---: |
| Accepted static tasks | 12 | 12 | Equal in this fixture scope |
| Total input + output tokens | 849,677 | 1,324,666 | +55.9% |
| Total tokens per accepted task | 70,806.4 | 110,388.8 | +55.9% |
| Uncached input tokens | 273,371 | 283,598 | +3.7% |
| Cached input tokens | 568,576 | 1,029,632 | Counted in total |
| Output tokens | 7,730 | 11,436 | Counted in total |

Exploratory paired-task bootstrap, 2,000 resamples: total-token ratio D/A
1.559, 95% interval **1.260–1.851**. Tasks share templates and there is one
replica; this is not a holdout or evidence of general quality noninferiority.
The runner retains `INCONCLUSIVE` because internal insertion attribution is
unavailable. The measured product totals still show no aggregate savings.

| Family, two tasks each | Total-token change D/A | Uncached-input change D/A |
| --- | ---: | ---: |
| Local | −0.04% | −24.0% |
| Rename | +70.2% | −7.4% |
| Signature | +69.1% | +59.6% |
| Bug | +19.7% | −21.6% |
| Flow | −15.7% | −21.1% |
| Review | +137.3% | +6.5% |

Local conditions expose identical graph-free surfaces; differing cache hits are
not evidence of a PCG optimization. Flow is promising only in these two known
tasks. No post-hoc exclusions or class routing changes were applied.

Compared descriptively with dev.1, D total usage is 1.8% lower, while its ratio
to its contemporaneous A is slightly worse (55.9% versus 54.3% overhead). Different
solver behavior and provider cache prevent attributing the difference to T3.
Historical data and gates remain unchanged.

## Reads and coverage of T3

[Boundary audit](dev2-screening-boundary-audit-20261008.json) and
[direct-read audit](dev2-source-read-audit-20261008.json) report actual host
receipts, including failed requests. D uses 204 direct-read calls versus A's
180 (+13.3%), but returns 30,823 versus 88,151 characters (−65.0%). Repeated
same-hash direct code characters are 956 versus 8,508 (−88.8%). These character
counts are not model tokens and exclude graph/direct-window overlap.

Rename reads are identical: 92 per condition. Signature reads increase from
47 to 86: both conditions read original source 45 times; D reads updated
postimages 41 times versus A's two. Whether each check was necessary is unknown.
Review direct reads fall from 18 to four, yet review total tokens increase.
Fewer direct characters do not imply smaller complete model cost.

Required inventory preservation and source hashes pass; the T3 acceptance
criterion of no systematic reread increase is **not closed**. T4 seed discovery
and ranking are not tested by these known targets; overlap remains available
and default. T5's contribution is not isolated. T6 retention is disabled in this
generic MCP campaign because actual retained model context cannot be observed.
Native binding retention/compaction correctness is tested separately; long-task
and post-compaction model savings remain unmeasured.

## Gate and release interpretation

[Current gate evaluation](dev2-gate-evaluation-20261008.json) records G0/G1 and
G2-product in the tested scope, qualified G2-mechanism, failed original G3 savings,
and unrun G5. Local total tokens are near A and no static rename/signature defect
was detected. Native TypeScript fixture runtime guards pass; whole-solver median
is 32.2 seconds for A and 40.6 for D, nearest-rank p95 42.3 and 76.6 seconds.
There is no broad regression-free claim.

The 24-turn authorization is consumed; unused token headroom does not authorize
extra turns. The dev.2 tag is published. Stable 0.10 has not been created.
Implementation and deterministic correctness are verified; independent G5,
T3 reread acceptance and T6 end-to-end retention savings remain distinct open
experimental evidence. Keep selective workflows opt-in, BM25 experimental and
generic MCP retention disabled; do not claim savings versus using no graph.
