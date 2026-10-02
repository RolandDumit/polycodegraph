# 0.7 intent validation — local development candidate

Validated on Linux x64, 2026-10-02. Frozen native 0.6 reference:
`fff953388d089ae89ab0b260fec05a8326c02b69`. All ten intents are included across all
ten languages, as explicitly requested after the initial tranche proposal.
No new model/executor runs, private-source publication, consumer package changes,
drift baseline reset, commit, push or release were performed by this validation.

## Deterministic Flutter rename replay

[Aggregate measurements and provenance](rename.json) come from
`tool/intent_benchmark.py`, using the original 385-file manifest, frozen source
snapshot, pre-edit compact 0.6 trace and existing Presenza rename oracle. Raw source,
configuration, SDK locations and responses remain ignored/local. Both executables
use separate prepared provider assets and caches. Original hashes are checked
before and after the replay; no source edit or inferred baseline is used.

| Measurement | 0.6 compact primitive collection | 0.7 rename intent plus expansion |
| --- | ---: | ---: |
| Collection calls | 13 | 3 |
| Result characters | 36,167 | 21,047 |
| Result UTF-8 bytes, same JSON representation | 36,167 | 21,047 |
| Full resolved reference edges retained | 19 | 19 |
| Intent evidence records | — | 24 |
| Tool-list characters, counted separately | 10,277 | 15,219 |

The intent uses two evidence pages and one explicit DTO snippet. All 17 original
file/line patterns across seven edit files are present. The oracle's 21 changed
occurrences remain a patch requirement, **not 21 automatically editable spans**.
Independent DTO homonyms/wire keys are not classified as domain rename sites.
The primitive references match complete source/target/kind/file/line/offset/confidence
tuples, including distinct same-line sites. No required reference is lost.

Collection characters decrease **41.81%**, satisfying the ≤3-call/≥25% gate.
Characters measure one JSON result with the observed broker's default whitespace,
without protocol envelopes or duplicate text/structured content. The 4,942-character
schema increase is visible: including one tool list on each side reduces the
combined difference to about 21.9%. Startup is separate: the original trace also
contains two status calls, two searches and one index call. Those are not silently
counted as evidence savings.

The two intent page latencies were 1.80 ms and 0.57 ms in this single local replay;
these are individual observations, not median/p95 claims. Between the measured
intent pages, scan/extraction/graph-build deltas are all zero. Broader source
windows needed by a particular task still require explicit expansions. There were
**zero AI runs**: no claim about model tokens, subscription quota, patch correctness
or total AI task latency follows from these character measurements.

The first AST-enabled full Dart index initially exceeded the existing 64 MiB
provider output limit. Lossless interned AST transport solved that failure without
raising the limit. AST extraction/storage adds work to initial indexing; no net
end-to-end speed improvement is claimed. The replay does not re-run the old patch
validator or an AI executor; it verifies collection evidence against its existing
oracle.

## Verification matrix

- `cargo xtask check`: format, Clippy with warnings denied, 52 Rust tests. Includes
  watcher loss/overflow, transactional failures, concurrent source/config changes,
  confinement, Unicode/CRLF, transport cancellation/EOF, cursor/root/health/expiry,
  baseline eviction, explicit review diagnostics, extraction, packed AST integrity,
  interface dispatch/cycles, focused explanation ranking and body-only source changes.
- Dart provider: format, static analysis and four provider tests. Analyzer remains
  pinned at 13.3.0. Local tests used already cached test tooling (test 1.31.2); the
  committed dependency lock was preserved. Exact locked test-tool versions must
  also pass CI, rather than being called verified locally.
- Native MCP: all ten intents across ten language fixtures (200 symbols, 438
  relations), including bound locals, compound mutations and return events.
  Primitive no-intent differential checks compare against 0.6. Full primitive
  fixture replay also checks every selected symbol, architecture/search and updates.
- Real Flutter fixture: all ten intent calls, Flutter classification and primitive
  differential checks (24 symbols, 75 relations); updated widget body exercises
  local extraction constraints. No app execution/code generation required.
- Android SDK: prepared platform JAR analysis passes (five symbols, six relations).
  Trusted Kotlin plugin compiled with pinned K2 2.3.10; PSI environment emits a
  compiler deprecation warning, recorded rather than suppressed.
- Adapter checks: Ruff/mypy, javac compilation, Go test/vet and syntax checks.
  TypeScript native MCP/intent operation verified with no Dart SDK on PATH.
- Four existing token-accounting unit tests pass; no new model usage experiment.

macOS/UIKit and Windows execution are **not verified on this Linux host**. CI is
extended with intent checks in Dart/polyglot/Flutter/mobile jobs on all three
systems, plus native 0.6 compatibility builds. Linux relocation checks pass with the prepared Dart/Go workers and TypeScript runtime assets in a directory with spaces, exercising all ten intents for those three languages. Packaging/host CI must pass before publication. SourceKit library discovery and ABI require those host checks; when
unavailable Swift reports incomplete bindings. Extraction coverage of lambdas,
advanced patterns, aliases, async behavior and lifetimes remains qualified by the
provider limits. No automatic extracted signature or safe deletion is promised.

## Reproduction and integration

Run `cargo xtask check`, prepare selected trusted adapters, then run
`tool/intent_smoke.py --group mixed|dart|polyglot|mobile|flutter --binary ... --config ...`.
`tool/intent_baseline.py` builds the pinned 0.6 core; supply its executable through
`--baseline`. Separate baseline adapter configuration strengthens differential
checks and is supported by `--baseline-config`.

`tool/intent_benchmark.py --help` lists explicit snapshot, manifest, trace, oracle,
root-prefix and binary/config inputs. It publishes only aggregate JSON, validates
complete reference tuples and original file/line oracle snippets, and never
invokes a model. Reusing another project's sources requires its authorized local
inputs; they are not bundled here.

The consumer changes are a reviewable [unapplied patch](../../harness-integration-0.7.patch); its applicability was checked without modifying the consumer.
The official installed executable, consumer source tree and its drift baseline
remain untouched. See [migration](../../migration-0.7.md) for candidate/rollback paths.
