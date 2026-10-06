# Preregistered efficiency pilot (0.8)

Registered 2026-10-05 before any candidate AI run. Deterministic product replays may inform implementation; they are not this pilot. Historical 0.6/0.7 protocols are
unchanged. Primary fallback metric: provider-accounted uncached input per accepted
task, including failed attempts and retries. If all cells expose comparable actual
monetary costs, register a new protocol revision *before* executing its candidate
and use total money / accepted tasks. Never replace missing usage with characters.
Target: C/A <= 0.80 and C/B < 1, equal correctness; report all components and task
classes, including a separate local-task regression check. Zero accepted tasks
has undefined cost per accepted task, never zero cost.

Six fresh tasks: local change (TS), ambiguous rename (Dart), signature (TS),
symptom bug (Dart), branched flow (TS), local review in a large file (Dart).
Their fixed orders are respectively ABC, ACB, BAC, BCA, CAB, CBA. One attempt per
cell unless the registered executor policy explicitly permits a bounded retry;
all failed attempts remain accounted. Stop after these 18 executions. Do not infer
significance or robust savings from one replica. Holdout/extended sampling and
ablations require a separate preregistration driven by observed uncertainty.

A excludes PolyCodeGraph, schemas, instructions and context artifacts. B is the
frozen 0.7 build with its committed compact harness. C uses the frozen candidate,
explicit views and selective routing. Task prompt/snapshot, model, effort,
unrelated tools, dependencies, oracle and limits are identical across cells.
Each task starts from an isolated source copy and a fresh model context. Record
executor-enforced filesystem/tool/network isolation; prompt-only restrictions fail
G2. Oracle/reference patches/other runs stay outside executor reach.

Before launch, freeze executable digests, dirty-source diff digest, provider
assets/configuration, harness hashes, actual schemas, model/effort/client identity,
dependencies, task source hashes, prompt, oracle identity, index cold/warm policy,
retry/time limits and client representation. Missing required identities blocks
launch, but does not block deterministic product validation.

Log the exact schema and graph instructions actually loaded, MCP text/structured/
transformed representation injected, external reads, model requests and usage,
errors/retries, windows newly read/repeated/rehydrated, pages, expansion and
compaction. Raw messages/sources stay ignored. Timing, process/provider RSS,
preparation and server work are separate measures. Prompt cache, graph cache and
client retained context are distinct states. Both MCP representations on the wire
do not prove both reach the model. Local estimates cannot pass G2/G3.

Use independent validators: identity-preserving rename with homonym/wire-key
checks, signature consumers/implementations, bug behavior/regressions, grounded
trace/limits, review actual changes/uncertainty, and local edits without unrelated
changes. Exact patch matching alone is insufficient when multiple solutions work.

G0 identities; G1 relevant compatibility/regressions; G2 verified accounting and
isolation; G3 all 18 pilot cells with per-task C/A and C/B; G4 preregistered extended
corpus/replicas/holdout. Each gate is passed/failed/not_measured with a reason.
No reliable executor currently registered: **no model run is authorized to be
reported as measured merely because local response replays pass**. Runner supports
an externally supplied executor; no mandatory paid API or invented usage.

Server tools/list hashes and harness-file hashes are recorded independently from the actual model schema/instruction insertion hashes. The latter must be frozen by a real executor before launch; wrapper transformations are not presumed identical. The runner recomputes per-request usage, validates order/source inventories and preserves failures. Independent isolation/oracle proofs remain executor prerequisites. Exact-window client accounting needs identity callbacks for older server payloads; unidentified context blocks G2. Partial overlaps need executor instrumentation beyond the built-in exact-window ledger. Raw execution output belongs in ignored work/ or outside the repository.

## Runner and executor contract

From the repository, inspect readiness without calling a model:

```sh
python tool/efficiency_benchmark.py check --manifest docs/benchmarks/efficiency-0.8/manifest.json --output docs/benchmarks/efficiency-0.8/readiness.json
python tool/efficiency_benchmark.py prepare --manifest docs/benchmarks/efficiency-0.8/manifest.json --work work/efficiency08-pilot --output work/efficiency08-pilot/preparation.json
```

Preparation rejects occupied cell directories and verifies the complete snapshot
inventory, including symlink rejection. Register a trusted executor executable,
independent oracle executable, actual model/effort/client identities, isolation
verifier and actual inserted schema/instruction hashes before `run`. Freeze the
new manifest and prepare fresh copies after any identity change. Launch verifies
binary/config/harness/schema and prepared provider artifact digests. Provider/SDK
preparation costs remain separately recorded; indexing during the task belongs to
the task cost. The portable public configuration is distinct from the hashed local
native configuration and its ignored SDK paths.

The executor receives one JSON request on stdin: run/task/condition identity,
prompt, workspace, fresh context identity, graph artifact metadata, limits and
client measurement policy. Artifact metadata is for trusted orchestration; it is
not automatically model context. It returns one JSON object on stdout containing
run_id, attempt, answer, usage_events **or** codex_usage_metadata,
client_measurement, isolation and optional monetary_cost/server metrics. Per-request
events require request_id/provider/model/effort and original usage fields. Codex
metadata retains only turn-context model/effort and cumulative/last token counters;
the frozen historical parser checks deduplication, resets and consistency. Messages
and indexed sources never enter published usage aggregates.

Use efficiency_client.Observer at actual prompt insertion: observe_wire alone
does not count model input. Text uses the actual parsed text, structured uses its
inserted object, and both counts repeated windows from both representations.
Primitive snippets and external reads require content/range identity callbacks.
For transformed responses supply prompt_windows with file/root_id/source_hash,
start_line/end_line/text for the actual retained windows, or an explicit empty
inventory if none was inserted. Missing inventories/unidentified source block G2.
Record model requests, expansion, retries and compaction at their actual boundaries;
the adapter cannot discover these automatically.

The independent oracle receives task/workspace/answer/criteria and returns accepted
as a boolean plus a reason_code. It must support valid alternative solutions and
obey the repository prohibition on indexed application code, plugins/build hooks.
Oracle/reference/other-cell access must be prevented and independently probed by
the registered executor isolation mechanism. The runner itself is not a sandbox.
Unix subprocess groups and output files are bounded; Windows descendant/output
enforcement requires the registered executor and has not been validated here.

With registered executable paths, `run --executor ... --oracle ...` writes raw
results under ignored `--work`; use its ignored `--output` JSON as `--runs` for
`evaluate`. Only evaluation aggregates belong in the public results file. A timeout
or missing partial usage remains a failed attempt with invalid measurement, never
an inexpensive accepted task. Current readiness intentionally blocks AI execution.
