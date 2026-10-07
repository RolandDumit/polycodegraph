# Experimental integration and rollback

Start the candidate with the existing prepared provider configuration and
`serve --root ROOT --tool-profile agent --response-profile compact`. Provider
installation and SDK locations remain local configuration, not checked-in
experiment files. Do not use baseline build/cache directories for the candidate.

Register exactly the five tools actually returned by `tools/list`. Route
`inspect_change` through `efficiency_client.LeanAdapter` in an isolated executor
that owns the prompt insertion boundary. Example arguments:

```json
{"intent":"change_signature","target":"EXACT_SYMBOL_ID","options":{"added_parameters":["locale"]}}
```

The adapter supplies `format: lean` and manages identical-argument cursors. Insert
only its `text` string. Do not also insert the original MCP content or structured
result. Record wire counts and the actual inserted representation separately with
the observer; populate actual schema/instruction hashes from the model boundary,
not server output. The native test measures this local transformation without a
model attached; Codex forwarding remains an unexecuted acceptance test. Until
verified, no E1/E2 result can attribute savings to that boundary.

Use `options.include_tests: true` only for a concrete signature test question.
`completion.required_inventory` distinguishes pending sites/static gaps from
`optional_context` and compiler/test work. A complete inventory is not correctness
approval. The server cannot set external checks verified. Source hashes/windows
refer to actual bounded reads, marked as untrusted code. Truncation, provider
limits and uncertainty remain visible. Default collector caps are 16 pages /
64,000 Unicode characters, 60 seconds and 8 MiB aggregate wire. The transport
callback must be timed/cancellable during each call; collection checks elapsed
time and cancellation between callbacks. Caps are context/work budgets, not measured tokens.

Review capture in lean format is strict:

```json
{"intent":"review_change","target":"src/exact.ts","format":"lean","options":{"capture_baseline":true,"capture_mode":"minimal"}}
```

An absent intended creation must appear in `options.new_files`; duplicates are
invalid. Compare with the returned session handle and the same scope/format.
Do not convert an existing legacy non-strict capture to strict midway. Captures
expire according to the unchanged session contract and cannot be reused after
reconnect. Use `view: full_evidence` for relocated before/after positions or
`format: audit` for the canonical representation.

Rollback: bypass the adapter and omit `format` (or choose `audit`). Keep using
the original response/tool profiles. Omit `strict_scope` to retain legacy missing
file capture; lean always implies strict. The deterministic review fix remains
active; roll back its isolated patch to reproduce the old positional behavior.
No persistent-schema migration/cache destruction or application edit is needed.
The profile is not promoted to default, no version number/tag/push is created.

Before paid execution, set concrete executor, oracle, client and artifact
identities plus authorized run/request/uncached-input limits, verify enforcement,
and register any supported E1 matrix change. `efficiency_benchmark.py --help`
provides check/prepare/run/evaluate. Raw files belong to ignored `work/` or an
external directory. `prepare` creates fresh solver copies without invoking a
model or indexing/application code.
