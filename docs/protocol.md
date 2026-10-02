# MCP and graph contract

Transport is UTF-8 newline-delimited JSON-RPC 2.0 on stdin/stdout, with stderr reserved for diagnostics. No HTTP listener. Supported released revisions: `2025-11-25`, `2025-06-18`, `2025-03-26`. Unknown requested versions negotiate `2025-11-25`; clients decide whether to accept that version. Draft/RC protocol behavior is not advertised.

Send `initialize` with protocolVersion, capabilities and clientInfo, then `notifications/initialized`, then tools/list or tools/call. Ping works before initialization. Repeated initialization fails. Tool calls are serialized for coherent indexing; stdin continues to receive notifications while work runs. EOF drains pending calls and flushes stdout. Unknown notification methods are ignored.

A message is capped at 1 MiB. Oversized, invalid UTF-8, malformed JSON and unterminated frames yield a parse error; a following valid line remains readable. The request queue is capped at 64. Duplicate in-flight request IDs are rejected. Cancellation notifications suppress queued/cancelled responses; an active indexing/provider operation finishes its cache update safely rather than being forcibly interrupted. Thus cancellation does not roll back indexing.

Protocol errors use JSON-RPC error codes (`-32700`, `-32600`, `-32601`, `-32602`, `-32603`); lifecycle/queue errors use `-32000`. Known-tool execution/argument errors return `isError: true` content so an agent can recover. Execution failures return bounded tool error content; transport I/O failures terminate with a stderr diagnostic.

Tool lists have no pagination. Each tool's inputSchema is an object with no additional properties. Graph list results use `columns`, `rows`, `total`, `offset`, `next_offset`, and a generation hash. Text content is compact JSON; structuredContent carries the same object. The server advertises tools only, with no resources/prompts/sampling capabilities. Graph query annotations are read-only relative to source; queries may update the derived cache. `index_repository` explicitly advertises a non-read-only action.

Node IDs: `<relative-file>::<qualified-name>#<kind>`; file nodes: `<relative-file>::file`; external directive nodes: `uri::<uri>`. Getter and setter IDs use distinct kinds. Synthetic variable accessors normalize to their field/variable. Generic substitutions normalize to the original declaration. Unnamed/default constructors use `.new`; implicit constructors are tagged synthetic. Unnamed declarations may use offsets and have weaker ID stability.

Relations: `contains`, `imports`, `exports`, `part`, `part_of`, `extends`, `implements`, `with`, `on`, `references`, `calls`, `overrides`, `registers`. Reference/call rows include source locations and `resolved` confidence. `registers` represents a recognized typed GetIt registration, not arbitrary runtime DI resolution.

Version 0.5 adds inspect_change and status.freshness/metrics without changing the existing fifteen tools. inspect_change has target, depth (1–32, default 6), limit (default 20 per section), include_snippet (default false); every section uses the same generation and reports omissions/truncation. The server still serializes tool calls, while the reader handles cancellation independently. Periodic reconciliation runs while the server is idle.

Version 0.6.0 adds opt-in [response profiles](response-profiles.md): `detail`
per call and paged `status.section` details, using the same sixteen tool names.
Compact health identities are independent of source generation; restart pages
when either changes. `status(section: metrics)` exposes per-tool calls, errors
and UTF-8 bytes of one JSON result representation, excluding protocol envelopes,
tool schema and model tokens. The current metrics request is counted as a call;
its bytes are added after returning the response. No duplicate-response inference
or session result suppression is implemented.

Version 0.7 extends the existing inspect_change with optional typed intent/options,
budget and opaque cursor; no-intent calls retain the 0.6 contract. Shared evidence
tables, AST region constraints and explicit session review baselines are described
in [intents.md](intents.md). No resources, sampling, source-edit or build tools are added.
