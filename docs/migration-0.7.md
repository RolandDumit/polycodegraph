# Updating from 0.6 to 0.7.0

Download the native 0.7.0 package or build the Rust executable, and prepare the selected providers
with `setup --languages ...`. Updated Dart/Go workers and the trusted Kotlin
plugin must be rebuilt; copying only the new core onto old adapters leaves
intent capabilities unavailable. No additional LLM or embeddings service is used.
Native packages include the updated Dart/Go workers; other selected adapter assets
are prepared by setup. Rust is required only to build from source.

Use a separate executable, provider directory and cache for evaluation. Preserve
local SDK/module/classpath configuration and other MCP servers. Update the MCP
command or harness executable override to 0.7.0 and restart the client.
No automatic update to another project's installed package is performed.

Public symbol IDs, primitive calls, configured roots, compact/legacy profiles,
watcher behavior and SQLite schema 3 are preserved. Provider assets participate in
cache identity: the first 0.7 launch rebuilds derived records as necessary.
The new optional record metadata is stored inside existing file JSON records.
There is no database migration or historical baseline import.

Use `inspect_change(intent: ...)` as documented in [intents.md](intents.md).
Read `generation`, `health_fingerprint`, freshness, errors and omissions on every
page. Before a sensitive change, explicitly reconcile with `index_repository`.
Capture a review baseline before edits; handles cannot survive server restarts.
Existing primitive `inspect_change` still works without an intent. Response
profile remains opt-in; intent budgets work independently of profile.

Rollback restores the former executable/adapter paths and cache configuration,
then restarts MCP. Keep the official package and benchmark baseline intact.
Do not interpret smaller responses as established AI token/quota savings.
