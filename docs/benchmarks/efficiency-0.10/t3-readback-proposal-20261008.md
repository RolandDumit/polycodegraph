# Proposed T3 readback diagnostic — not authorized or executed

Purpose: test whether explicit use of successful edit receipts reduces the
refactoring readback behavior observed in dev.2. This is a narrow instruction
ablation on known fixtures, not a product savings confirmation or G5 holdout.

## Proposed comparison

- Four existing controlled tasks: `signature-1`, `signature-2`, `rename-1`,
  `rename-2`. One old-guide C and one corrected-guide D per task: eight new
  solver turns. Alternate paired order; no exclusions based on results.
- C and D use identical dev.2 native binary, prepared provider assets,
  task-specific schema, intent source policy, collection representation and
  ordinary bounded read/search/hash-checked replace tools. Only the targeted
  workflow guide differs. Freeze both module/guide identities before execution.
- Same `gpt-6.1-sol`, effort `high`, serial fresh workspaces and isolated client
  homes. Independent static postimage oracles stay outside solver workspaces.
  No indexed application execution, tests, scripts or build hooks.
- Requested additional budget: eight solver turns and 250,000 aggregate
  uncached input tokens, checked after each turn; the final turn can exceed the
  threshold. Economic cost is unverified. No preparation AI, model judges or
  external solver retries. Unknown/incomplete provider usage stops execution.

## Frozen diagnostic decision

Report all four pairs and failures. The primary behavioral diagnostic is
successful same-file reads returning a previously successful write's identical
hash, per independently accepted task. Failed/changed/unknown observations and
the complete ordinary read count are separate mandatory fields. Read necessity
remains unknown: do not retrospectively classify inconvenient reads away.

Support for the correction requires all static tasks accepted, fewer same-hash
post-edit reads in both signature pairs, and no increase in the total direct
read count across the four candidate tasks. This one-replica diagnostic is not
an estimate of general model quality or proof of a stable causal effect.

Report whole-task input, cached input, uncached input, output including reasoning,
requests, errors, timing, schema and actual guide insertion evidence. Include
all calls and failed turns; zero accepted tasks makes per-accepted costs undefined.
Do not compare C or D to historical A runs as if they were a fresh paired control.

The [subscription policy](../../codex-plan-consumption.md) applies to any economic
interpretation. Actual attributable included-plan quota is unknown unless
before/after observations share bucket/window/reset identities and exclude other
account usage with sufficient counter precision. Zero rounded change is not
free usage; bucket percentages must never be added. If quota is not attributable,
report it unknown and use explicitly labelled frozen-rate credit equivalents
only as supporting proxies, alongside all raw categories. No fee-to-token or
API-price conversion is a measurement of the user's included plan.

This proposal grants no AI budget. The previous 24-turn authorization is
consumed. Freeze commit, binary, adapters, instructions, schemas, ordinary host,
oracles, parser and stop policy in a new private campaign before any approved run;
never mutate the completed campaign. G5 sizing/holdout and T6's actual-context
binding experiment need separate protocols and budgets.
