# EduRoma smoke repair and fresh-run preregistration

Prepared 2026-10-07 after the [first four smokes](eduroma-smoke-20261007.md).
The prior 92,475 uncached input tokens remain recorded separately. This document
does not authorize additional AI execution.

## Completed repairs

- The same client configuration enables `code_mode` and `code_mode_host` in every
  condition. Shell, plugins, hooks, browser, multi-agent and application execution
  remain disabled. Only bounded source search/read and the selected PCG tools are
  available.
- `limits.executor_file_size_bytes` explicitly permits owned derived files up to
  512 MiB for this Linux fixture. The historical default remains 8 MiB. POSIX
  `RLIMIT_FSIZE` enforces the selected allowance; Windows has no equivalent
  verified enforcement in this launcher.
- Executor stdout and stderr are each independently spooled with an **8 MiB
  limit**. Overflow terminates the process group; increasing the cache allowance
  does not increase these response/diagnostic limits. Unread stdin, executor
  timeout and inherited pipes have bounded cleanup.
- The transparent private wire recorder exits when the backend exits, even if
  client stdin is still open. Client EOF drains responses within its allowance.
  It retains frame hashes/byte counts and private payloads, forwards original
  bytes, rejects oversized frames and caps each receipt at 64 MiB. It observes
  protocol traffic, not model insertion or tokens.
- Ordinary source reads default to 120 lines starting at the requested line.
  The range, source hashes, allowlist and symlink checks remain enforced.
- Delivered native pages are counted separately from intent requests. A valid
  collection-2 response is recognized through its `page_states` and snapshot;
  the old erroneous singular `dictionary` test is not used. Empty timeout
  collections do not satisfy actual treatment-use acceptance.

The new optional budget `reservation_policy: remaining_positive` permits another
attempt while known uncached budget remains positive. It requires explicit
`final_attempt_overshoot_accepted: true` and the existing after-attempt approval.
Old manifests retain `full_attempt` reservation. Unknown usage still stops the
campaign, and every failed attempt remains in its append-only journal.

## Fresh campaign

All four conditions receive the same repaired tools, isolation, file/stream
budgets, source snapshot, authentication task, independent oracle and model.
A omits PCG; B is exact 0.9 full/audit; C is exact 0.9 agent/lean/collection-1;
D is the frozen 0.10 workflow/automatic-collection candidate. Actual server
schemas and retained guides are frozen independently for each condition.

The fixed order is A, B, D, C, with one attempt per condition, serial execution
and a new client home/context/cache for each. No old observation is replayed.
This is one known task and one replica; even four successful smokes establish
wiring rather than a general token-saving or noninferiority result.

Proposed additional authorization: **four solver turns**, `gpt-6.1-sol` with
effort `high`, **100,000 aggregate uncached input tokens**, checked after each
run with possible final-run overshoot. No external retries, preparation AI or
judge AI. Economic cost is unverified. Each attempt additionally has a 900-second
timeout, at most 40 measured model usage increments, 40,000 uncached input,
600,000 total input and 30,000 output tokens; token/request guards are observed
after the attempt. All proposed values require approval before execution.

## Validation and precision

The repaired zero-AI app-server preflight passed for A/B/C/D, with respectively
0/16/5/1 registered PCG tools. B returned native audit, C collection-1, and D
collection-2. Actual registration matches the captured native MCP catalogs.
The same bounded launcher allowed the native cache to exceed the old 8 MiB
threshold. No source/application code was executed.

76 Python tests passed, including regressions for cache/output independence,
output overflow, unread stdin, descendant-held pipes, backend death, EOF draining
and authorized budget reservation. `cargo xtask check` passed with 88 Rust tests.
Configured Python lint/format checks passed on the six changed measurement/test
modules. Source-reader defaults, range limits and protected-path rejection were
also checked without AI.

Provider incompleteness remains visible. A source-task answer may be independently
accepted while `collection.complete=false` and `provider_incomplete=true` remain
true. Those flags cannot become a claim of complete semantic inventory, compiler
correctness, runtime behavior or rename safety. Exact per-request provider context
and insertion, economic cost and cross-platform SDK coverage remain unverified.

The [repair source manifest](smoke-runner-fix-source-manifest.json) records the new
measurement identity. Native binaries, the seven shipped client modules and
provider implementation/semantic contracts were not changed by these repairs.
Historical manifests/reports retain their original hashes and measurements.
