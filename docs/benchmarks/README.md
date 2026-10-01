# Performance evidence for 0.5.0

Run release builds with the pinned toolchain and the immutable `v0.4.0` oracle (`python tool/baseline.py`). No debug/release comparisons, provider substitutions or token-savings estimates are used.

## Workloads

`tool/benchmark.py` compares a deterministic 100,000-symbol / 500,000-relation graph and a 1 MiB source corpus. Both helpers generate the same IDs and relations, request the same incoming calls and apply SHA-256 source reconciliation. The old core constructs GraphQuery for every query; Rust constructs its graph once per generation. Each helper runs for at least 31 seconds with 100 ms pauses. Rust includes the initial and 30-second reconciliation in its query samples; Dart reconciles every query. Median, p95, mean and maximum are reported; rare reconciliation costs can disappear from median/p95, so consult all measures. The speed gate requires Rust median <= half the old median.

This isolates the repeated-query architecture. It excludes language extraction, MCP framing and database startup and must not be quoted as a whole-project speedup. The corpus is a synthetic graph, not 100,000 compiled declarations. A separate persistence run records cold JSON/SQLite write/read times, sizes and process-tree RSS; it does not affect latency-run RSS. Database indexes and duplicated durable record representations can cost more disk and memory than JSON.

`tool/end_to_end.py` separately measures native MCP round trips, cold indexing, an incremental source edit and repeated queries for 31 seconds on the compiler-backed polyglot and real Flutter fixtures. The Rust metrics split cumulative scan, extraction, storage and query time. This includes the complete server plus live provider descendants, and one periodic reconciliation. End-to-end numbers reflect these small fixtures and their prepared dependencies, not a large application.

Linux RSS is sampled every 25 ms from `/proc`, including descendants without double-counting threads. It is sampled peak resident memory, not allocations, precise transient maximum or a portable cross-OS memory metric. Cold indexing means an empty tool cache; OS/provider/compiler caches are shared/warm. Runs are sequential on the same machine. Hardware and raw results accompany the report. Rerun several times on representative projects before choosing deployment budgets.

## Recorded results

See [large graph results](v0.5.0-linux.json) and [end-to-end results](v0.5.0-end-to-end-linux.json). The synthetic median gate passes. The large-graph Rust process has a higher query-run RSS peak than the Dart baseline, so this release claims a measured repeated-query improvement for that workload and **does not claim a memory reduction**. Provider semantic limits remain unchanged.

```sh
python tool/baseline.py
cargo build --release --locked --workspace --bins --examples
python tool/benchmark.py --rust target/release/examples/benchmark --dart work/baseline/benchmark_dart --output work/benchmark.json
python tool/end_to_end.py --rust target/release/polycodegraph --dart work/baseline/polycodegraph --config work/sdk-config.json --output work/end-to-end.json
```

Use `.exe` on Windows; memory sampling currently requires Linux. The CI benchmark uploads its own report. Native package smoke tests are separate from performance measurements.
