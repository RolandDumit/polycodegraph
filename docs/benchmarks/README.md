# Performance evidence for 0.5.0

Later evidence: [0.9 release validation](../releases/v0.9.0.md),
[post-0.8 deterministic experiments](efficiency-post-0.8/decision.md), and
[comparison preparation without AI execution](comparison-20261006-01/report.md).
These dated experiments retain their identities and unmeasured economic gates.

[0.10 first-tranche implementation](efficiency-0.10/report.md) records T0–T2
client integration, lossless native replay, artifact identities and the separate
preregistered continuation. It is the frozen pre-AI snapshot.
[EduRoma real-client smoke, 2026-10-07](efficiency-0.10/eduroma-smoke-20261007.md)
records four separately authorized AI turns, their complete usage and observed
client/resource failures. The comparison remains invalid; no token-saving claim
is made.
[Smoke runner repairs and fresh-run preparation](efficiency-0.10/eduroma-smoke-rerun-20261007.md)
record the corrected common client/resource limits and zero-AI checks. Repeated
AI smokes require a separate explicit budget; old failed runs remain recorded.
[Four fresh smokes after the repairs](efficiency-0.10/eduroma-smoke-rerun-results-20261007.md)
record the separately authorized rerun: A/B/D accepted, C exceeded its attempt
guard despite a verified source answer, and the final aggregate overshoot is
recorded. General token-saving acceptance remains pending.
[Gate continuation status](efficiency-0.10/gates-status-20261007.md) distinguishes
the historical pre-AI manifests from current evidence, platform follow-up and
the separately approved 24-run screening.
[Completed 24-turn screening](efficiency-0.10/screening-results-20261007.md)
records complete static acceptance and a failed savings gate: D used 54.3% more
total tokens and 42.8% more uncached input than A.

Run release builds with the pinned toolchain and the immutable `v0.4.0` oracle (`python tool/baseline.py`). No debug/release comparisons, provider substitutions or token-savings estimates are used.

## Workloads

`tool/benchmark.py` compares a deterministic 100,000-symbol / 500,000-relation graph and a 1 MiB source corpus. Both helpers generate the same IDs and relations, request the same incoming calls and apply SHA-256 source reconciliation. The old core constructs GraphQuery for every query; Rust constructs its graph once per generation. Each helper runs for at least 31 seconds with 100 ms pauses. Rust includes the initial and 30-second reconciliation in its query samples; Dart reconciles every query. Median, p95, mean and maximum are reported; rare reconciliation costs can disappear from median/p95, so consult all measures. The speed gate requires Rust median <= half the old median.

This isolates the repeated-query architecture. It excludes language extraction, MCP framing and database startup and must not be quoted as a whole-project speedup. The corpus is a synthetic graph, not 100,000 compiled declarations. A separate persistence run records cold JSON/SQLite write/read times, sizes and process-tree RSS; it does not affect latency-run RSS. Database indexes and duplicated durable record representations can cost more disk and memory than JSON.

`tool/end_to_end.py` separately measures native MCP round trips, cold indexing, an incremental source edit and repeated queries for 31 seconds on the compiler-backed polyglot and real Flutter fixtures. The Rust metrics split cumulative scan, extraction, storage and query time. This includes the complete server plus live provider descendants, and one periodic reconciliation. End-to-end numbers reflect these small fixtures and their prepared dependencies, not a large application.

Linux RSS is sampled every 25 ms from `/proc`, including descendants without double-counting threads. It is sampled peak resident memory, not allocations, precise transient maximum or a portable cross-OS memory metric. Cold indexing means an empty tool cache; OS/provider/compiler caches are shared/warm. Runs are sequential on the same machine. Hardware and raw results accompany the report. Rerun several times on representative projects before choosing deployment budgets.

## Recorded results

See [large graph results](v0.5.0-linux.json) and [end-to-end results](v0.5.0-end-to-end-linux.json). The synthetic median gate passes. The large-graph Rust process has a higher query-run RSS peak than the Dart baseline, so this release claims a measured repeated-query improvement for that workload and **does not claim a memory reduction**. Provider semantic limits remain unchanged.

### Recorded native MCP fixture run (Linux x64)

| Fixture | Engine | First index ms | Median ms | p95 ms | Edit/update ms | Peak process tree MiB |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| polyglot | dart-v0.4.0 | 1511.7 | 2.210 | 2.669 | 21.5 | 412.7 |
| polyglot | rust | 1491.5 | 0.247 | 0.318 | 256.7 | 417.9 |
| flutter_fixture | dart-v0.4.0 | 2929.0 | 1.874 | 2.216 | 2877.0 | 479.5 |
| flutter_fixture | rust | 2997.3 | 0.248 | 0.317 | 3155.2 | 527.3 |

These runs improve repeated query medians by about 7.6–9.0×. First indexing is comparable; updates include the Rust watcher debounce and do not improve in these fixtures. Neither the fixture runs nor the synthetic query run demonstrates a memory reduction. All timings include the configured reconciliation policy.

```sh
python tool/baseline.py
cargo build --release --locked --workspace --bins --examples
python tool/benchmark.py --rust target/release/examples/benchmark --dart work/baseline/benchmark_dart --output work/benchmark.json
python tool/end_to_end.py --rust target/release/polycodegraph --dart work/baseline/polycodegraph --config work/sdk-config.json --output work/end-to-end.json
```

Use `.exe` on Windows; memory sampling currently requires Linux. The CI benchmark uploads its own report. Native package smoke tests are separate from performance measurements.

[0.7 intent replay and validation](intents-0.7/report.md) records complete evidence, schema costs, zero model runs and skipped host checks.

[0.8 efficiency candidate](efficiency-0.8/report.md) has its own preregistered
protocol, six-task manifest, deterministic/native replays and runtime measurements.
Historical protocols above remain frozen. AI cost gates are reported separately;
missing model usage/isolation is never replaced with payload characters.

[Application AI pilot, 2026-10-06](efficiency-0.8-application/report.md) reports all 18
accepted cells and actual usage: rc.1 improves descriptively over 0.7, remains more
expensive than no graph, and fails G2 on incomplete client telemetry. This is a
separate pilot, not a revision of the historical fixture protocols.
