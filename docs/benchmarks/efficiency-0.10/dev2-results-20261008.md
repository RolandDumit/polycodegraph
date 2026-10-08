# 0.10.0-dev.2 implementation and validation — 2026-10-08

T3–T6 implementation continues on `codex/0.10-token-efficiency`; the annotated
`v0.10.0-dev.1` tag freezes the previous checkpoint at `90eec26`. Tested program
commit: `2e40eceecce941aa96048c0bf02bd2614b1df55d`.

The user clarified that at most 15% additional total tokens relative to A is a
1.0 objective. The historical dev.1 savings screening remains failed. The new
candidate completed a separately authorized 24-turn screening: all static edits
passed, but total tokens were 55.9% above A. See [the AI results](dev2-screening-report-20261008.md). It cannot claim aggregate model-token savings.

## Implemented tranche

- T3: explicit intent source policy and independent source-text budgets. Required
  sites remain intact; explicit views prevail. Optional client tokenizer budgets
  apply to final insertion text only. Guidance requests concrete missing context
  and avoids full-source copies before direct file reads.
- T4: effective file/language scope before index caps, bounded two-entry cache,
  explicit exclusions, inverted lookup, anchor grouping before pagination and
  match-detail recovery. Overlap remains default; binary-term BM25 is an opt-in
  name/path ranking ablation, not a proven end-to-end improvement.
- T5: known inventory, local observed limits and unknown question coverage remain
  separate. Global health is preserved. Stable metadata is shared across pages;
  global problems do not invite repeated exhausted pagination.
- T6: explicit binding retention acknowledgement, bounded hash-only state,
  insertion confirmation, epoch reset, exact identity/source/baseline validation
  and self-contained fallback. Generic MCP retention stays disabled.

## Recorded deterministic evidence

[Validation identities](dev2-validation-20261008.json) record 93 Rust tests,
90 Python tests, configured lint, native ten-language/ten-intent workflows,
primitive differential checks against the rebuilt frozen 0.6 tag, rename
evidence, source-hash checks, cursor recovery, review baselines and relocation.
The relocated package passes with its native binary, eight client modules and
adjacent workflow entrypoint. Indexed application code is never executed.

Platform CI for the tested commit is tracked at
[the dev.2 run](https://github.com/RolandDumit/polycodegraph/actions/runs/37757087818).
All 20 jobs passed after a same-code recheck of the macOS mobile job. Its
initial UIKit timeout is preserved; the recheck verified 13 UIKit-fixture
symbols and 23 edges, and Android verified 5 symbols and 6 edges. No timeout
or product limit was relaxed. Conditional skipped steps do not establish
coverage. UIKit took approximately 170 seconds; the TypeScript runtime guards
below are not a general UIKit latency claim.

An initial native cursor recovery failure exposed missing policy forwarding;
the corrected relay passes both the unit regression and real continuation smoke.
The first CI also exposed a health test depending on locally installed providers;
the fixture now controls availability without invoking a provider. Local setup
failures (Go PATH, Swift compatibility libraries and npm cache location) and the
old contaminated local baseline are retained in ignored logs. The successful
differential uses the actual frozen 0.6 source and identical current adapters.

## Source projection measurements

[Native policy measurements](dev2-policy-retention-20261008.json) collect all pages
for ten known controlled TypeScript tasks, preserve full record/site/provenance
inventories, and record schema and instruction sizes separately.

| Family | Selected intent-policy characters versus explicit full evidence |
| --- | --- |
| Rename | −32.1% to −33.5% |
| Signature | −34.2% to −35.6% |
| Bug | +11.6% |
| Flow | +10.9% |
| Review current context | +2.2% |

These are **Unicode characters of complete selected insertion text**, not model
tokens or end-to-end task costs. The negative cases include additional policy and
coverage metadata. Review here has no before/after baseline and proves no review
token improvement. Source budget zero preserves inventories with explicit source
truncation. This does not establish that agents perform fewer subsequent reads.

The native binding retention probe emits 5,324 characters initially, 3,100 on a
confirmed repeated window, and 5,324 after compaction: **13,748 across all three
insertions**. Inventory remains equal. First-offer metadata and rehydration are
included; no inference follows about provider cache, history masking, additional
model requests or actual end-to-end model costs.

## Runtime guards

[Runtime measurements](dev2-native-runtime-20261008.json) include complete cursor
collections and 20 warm samples per condition on four known TypeScript tasks.
The candidate's warm p95 is 22.3–386.1 ms and maximum sampled descendant RSS is
319.1 MiB, within the recorded 5-second/512-MiB fixture guards. Cold query costs
are separate. Native 0.9 inventories match, but the relay is generally slower
and uses more RSS; no runtime or memory reduction is claimed.

This Linux measurement uses shared OS caches and 25-ms RSS sampling, not peak
allocation accounting. The native baseline uses its default lean edit context;
the candidate uses its explicit intent policy. It is not the same source-view
experiment as the historical dev.1 locations-only runtime measurement.

## Remaining experimental acceptance

The implementation and deterministic checks do not close the source-reread,
seed-search or retention end-to-end AI acceptance criteria. The authorized 24-turn A/D comparison is complete, with 556,969 uncached input
tokens, 24 accepted static outcomes and no additional authorized solver turns.
See [the screening report](dev2-screening-report-20261008.md). T3 direct-read
counts increased, chiefly after signature edits; its no-reread acceptance is
not closed. Product savings and independent confirmation remain unproved. The generic relay cannot validate T6 model retention; that requires a
client with actual retained-context observation. T4 ranking stays opt-in and its
baseline remains available. This repeated known-task screening is not independent confirmation. The
previous 24-turn screening budget remains fully consumed.

The development checkpoint does not create a stable release or change the
historical screening results. See [the milestone criteria](../../development-0.10-dev2.md).
