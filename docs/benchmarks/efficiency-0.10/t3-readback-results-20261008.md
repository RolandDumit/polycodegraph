# T3 readback correction — measured diagnostic

The preregistered instruction correction passes on the four known refactoring
tasks. All eight static postimages are accepted. Successful reads returning the
preceding edit's identical file hash fall from **85 to zero**; all successful
direct reads fall from **178 to 87**. This closes the narrow correction diagnostic,
not a general claim about every intent, source policy or repository.

[Machine-readable results](t3-readback-results-20261008.json) retain all attempts,
errors, usage, receipt classifications and identities. The frozen
[proposal](t3-readback-proposal-20261008.md) describes the pre-execution state;
the user subsequently authorized proceeding with its eight-turn/250,000
uncached-input limits. No historical A/D result is changed.

| Task | Old/new successful direct reads | Old/new same-hash post-edit reads | Old/new total tokens |
| --- | --- | --- | --- |
| signature-1 | 40 / 19 | 19 / 0 | 153,263 / 108,877 |
| signature-2 | 46 / 22 | 22 / 0 | 153,205 / 133,943 |
| rename-1 | 40 / 20 | 19 / 0 | 139,837 / 138,936 |
| rename-2 | 52 / 26 | 25 / 0 | 176,198 / 143,981 |

Both signature pairs improve and the aggregate read count does not increase,
satisfying the frozen decision. Hash equality is an observation, not proof that
a particular read was unnecessary or that a model retained the source. Receipt
classification is complete, with no eviction, unknown or changed post-edit hash.

## Cost and quality limits

| Usage, all four tasks per condition | Old guide C | Corrected guide D |
| --- | --- | --- |
| Input, including cached | 617,009 | 521,923 |
| Cached input | 505,728 | 394,624 |
| Uncached input | 111,281 | 127,299 |
| Output, including reasoning | 5,494 | 3,814 |
| Total input + output | 622,503 | 525,737 |
| Model requests | 35 | 31 |
| Tool errors, included in cost | 8 | 7 |

Total tokens decrease **15.54%**; uncached input increases **14.39%**. The paired
task bootstrap's exploratory 95% total-token ratio interval is 0.751–0.941,
using 2,000 resamples and seed 20261008. Four known tasks and one replica do not
establish a stable causal effect, independent confirmation or general quality.
The oracle verifies exact permitted bytes and findings, not application runtime.

Under the [subscription policy](../../codex-plan-consumption.md), included-plan
consumption and actual economic cost are **unknown**. Fewer raw total tokens do
not by themselves demonstrate that the monthly Codex allowance lasts longer.
There is no fresh no-graph A control in this diagnostic.

## Execution identity

The two conditions share native binary SHA-256
`8b0cbf56bd3cc71e1289a4521ece25422e3ec5fcdab23456dd7b5d0338143874`,
seven non-instruction client modules, prepared TypeScript providers, workflow
schemas, ordinary tools and isolated fresh workspaces. Only the instruction
module and its targeted developer/MCP initialization text differ. Internal
provider prompt materialization remains unobservable. The source/measurement
checkpoint is `ca722c77a9fc56e9eaf90f9d8726e539f0690b32`, with
`gpt-6.1-sol`, effort `high`, Codex app-server 0.159.2.

The campaign used **238,580 uncached input tokens** across eight solver turns;
there was no final overshoot, external retry, preparation AI or model judge.
All temporary credentials were removed. Indexed application code, scripts,
hooks, tests and builds were never executed. G5 remains a separate untuned
holdout; T6 requires actual model-context ownership.
