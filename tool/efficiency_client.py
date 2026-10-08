"""Client-boundary instrumentation for external executors; wire != model prompt.

Call observe_wire for MCP transport; call inject only at the actual prompt insertion
point, and record external reads/compaction explicitly. Raw text never enters the
published summary. This module neither calls a model nor guesses client behavior.
"""

from __future__ import annotations

import hashlib
import json
import time

from efficiency_collection import CollectionConflict, select_collection, source_windows
from efficiency_ledger import ContextLedger, source_key

__all__ = ["ContextLedger", "LeanAdapter", "Observer", "source_key"]


def compact(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class Observer:
    def __init__(self, source_identity=None) -> None:
        # Optional callback(file) -> (root_id, current_file_hash) for older servers.
        # The executor must obtain these identities without inferring model retention.
        self.source_identity = source_identity
        self.ledger = ContextLedger()
        self.schema_hash = None
        self.instructions_hash = None
        self.mcp_calls = self.pages = self.expansions = 0
        self.model_requests = self.errors = self.retries = 0
        self.wire_bytes = self.injected_bytes = self.injected_chars = 0
        self.representations: set[str] = set()
        self.wire_duplicate_objects = 0
        self.context_inventory_verified = True
        self.insertion_boundary_complete = True
        self.source_ledger: list[dict] = []
        self.source_ledger_omitted = 0
        self.events: list[dict] = []
        self.events_omitted = 0
        self.pending_calls: list[int] = []
        self.pending_insertions: list[int] = []
        self.event_sequence = 0
        self.binding_mode = None
        self.collection_mode = None
        self.collection_id = None

    def start_collection(self) -> None:
        """Separate discarded attempts from the next collection's insertion correlation."""
        self.collection_id = self._event("collection_start", prior_uninserted_result_ids=list(self.pending_calls))
        self.pending_calls.clear()

    def _event(self, kind: str, **fields) -> int:
        self.event_sequence += 1
        if len(self.events) < 8192:
            self.events.append(dict(id=self.event_sequence, kind=kind, epoch=self.ledger.epoch, **fields))
        else:
            self.events_omitted += 1
        return self.event_sequence

    def request_model(
        self,
        request_id: str,
        actual_prompt_schema: str | None = None,
        actual_instructions: str | None = None,
    ) -> None:
        """Observe a real outgoing request, correlating insertions and materialized surface.

        Missing request materialization stays unknown even if a startup schema hash
        exists. Only hashes/sizes are recorded; source, prompts and credentials are not.
        """
        if not isinstance(request_id, str) or not request_id:
            raise ValueError("missing model request identity")
        self.model_requests += 1
        tool_names = None
        if actual_prompt_schema is not None:
            try:
                schema = json.loads(actual_prompt_schema)
                specs = schema.get("tools", []) if isinstance(schema, dict) else schema
                if isinstance(specs, list) and len(specs) <= 512:
                    tool_names = [spec.get("name", spec.get("function", {}).get("name")) for spec in specs]
                    if any(not isinstance(name, str) or len(name) > 128 for name in tool_names):
                        tool_names = None
            except (ValueError, TypeError, AttributeError):
                pass
        self._event(
            "model_request",
            request_id_sha256=hashlib.sha256(request_id.encode()).hexdigest(),
            insertion_ids=list(self.pending_insertions),
            schema_sha256=None
            if actual_prompt_schema is None
            else hashlib.sha256(actual_prompt_schema.encode()).hexdigest(),
            instructions_sha256=None
            if actual_instructions is None
            else hashlib.sha256(actual_instructions.encode()).hexdigest(),
            schema_chars=None if actual_prompt_schema is None else len(actual_prompt_schema),
            tool_names=tool_names,
            binding=self.binding_mode,
            collection=self.collection_mode,
        )
        self.pending_insertions.clear()

    def load_schema(self, actual_prompt_schema: str) -> None:
        self.schema_hash = hashlib.sha256(actual_prompt_schema.encode()).hexdigest()

    def load_instructions(self, actual_instructions: str) -> None:
        self.instructions_hash = hashlib.sha256(actual_instructions.encode()).hexdigest()

    def begin_call(self, tool: str, arguments: dict) -> int:
        """Count an attempted call even if timeout/EOF prevents a result."""
        self.mcp_calls += 1
        return self._event(
            "tool_call",
            tool=tool,
            collection_id=self.collection_id,
            arguments_sha256=hashlib.sha256(compact(arguments).encode()).hexdigest(),
        )

    def observe_wire(
        self,
        result: dict,
        tool: str | None = None,
        arguments: dict | None = None,
        call_id: int | None = None,
    ) -> None:
        if call_id is None:
            self.mcp_calls += 1
        self.wire_bytes += len(compact(result).encode())
        event_id = self._event(
            "tool_result",
            tool=tool,
            call_id=call_id,
            collection_id=self.collection_id,
            arguments_sha256=None if arguments is None else hashlib.sha256(compact(arguments).encode()).hexdigest(),
            wire_bytes=len(compact(result).encode()),
            is_error=bool(result.get("isError")),
        )
        if len(self.pending_calls) < 8192:
            self.pending_calls.append(event_id)
        else:
            self.events_omitted += 1
        if result.get("isError"):
            self.errors += 1
        if "structuredContent" in result and result.get("content"):
            try:
                if json.loads(result["content"][0]["text"]) == result["structuredContent"]:
                    self.wire_duplicate_objects += 1
            except (ValueError, KeyError, IndexError):
                pass

    def _window(self, file: str, window: dict, root_id=None, file_hash=None) -> None:
        if "text" not in window:
            return
        if window.get("truncated"):
            self.ledger.unidentified_chars += len(window["text"])
            self.context_inventory_verified = False
            return
        if self.source_identity and (not root_id or not file_hash):
            root_id, file_hash = self.source_identity(file)
        if root_id and file_hash and "start_line" in window and "end_line" in window:
            state = self.ledger.range(
                root_id,
                file_hash,
                window["start_line"],
                window["end_line"],
                window["text"],
                phase=window.get("phase", "current"),
            )
        elif window.get("window_id"):
            key = window["window_id"]
            state = self.ledger.window(key, window["text"])
        else:
            self.ledger.unidentified_chars += len(window["text"])
            return
        entry = {
            "file": file,
            "root_id": root_id,
            "source_hash": file_hash,
            "start_line": window.get("start_line"),
            "end_line": window.get("end_line"),
            "text_sha256": hashlib.sha256(window["text"].encode()).hexdigest(),
            "origin": "graph",
            "state": state,
            "epoch": self.ledger.epoch,
        }
        if len(self.source_ledger) < 8192:
            self.source_ledger.append(entry)
        else:
            self.source_ledger_omitted += 1
            self.context_inventory_verified = False

    def _source(self, value: dict) -> None:
        for source in value.get("sources", []):
            for window in source.get("windows", []):
                self._window(
                    source["file"],
                    dict(
                        window,
                        phase=source.get("phase", window.get("phase", "current")),
                    ),
                    value.get("snapshot", {}).get("root_id"),
                    source.get("source_hash"),
                )
        for file in value.get("files", []):
            for window in file.get("snippets", []):
                self._window(
                    file["file"],
                    window,
                    value.get("context", {}).get("root_id"),
                    file.get("source_hash"),
                )
        # Primitive snippet and inspect_change(include_snippet) are source too.
        if "file" in value and "text" in value:
            self._window(value["file"], value, value.get("root_id"), value.get("source_hash"))
        if isinstance(value.get("snippet"), dict):
            self._source(value["snippet"])

    def inject(
        self,
        result: dict,
        representation: str,
        transformed: str | None = None,
        prompt_windows: list[dict] | None = None,
    ) -> str:
        values = []
        if representation == "text":
            text = result["content"][0]["text"]
            try:
                values.append(json.loads(text))
            except ValueError:
                self.ledger.unidentified_chars += len(text)
                self.context_inventory_verified = False
        elif representation == "structured":
            text = compact(result["structuredContent"])
            values.append(result["structuredContent"])
        elif representation == "both":
            text = compact(
                {
                    "content": result["content"],
                    "structuredContent": result["structuredContent"],
                }
            )
            values.append(result["structuredContent"])
            for block in result["content"]:
                if block.get("type") == "text":
                    try:
                        values.append(json.loads(block["text"]))
                    except ValueError:
                        self.ledger.unidentified_chars += len(block["text"])
                        self.context_inventory_verified = False
        elif representation == "transformed" and transformed is not None:
            text = transformed
            # Only the executor at insertion can declare transformed source windows.
            # An explicit empty inventory means no source, not automatic retention.
            if prompt_windows is None:
                self.ledger.unidentified_chars += len(text)
                self.context_inventory_verified = False
            else:
                for window in prompt_windows:
                    self._window(
                        window["file"],
                        window,
                        window.get("root_id"),
                        window.get("source_hash"),
                    )
        else:
            raise ValueError("actual client response representation must be explicit")
        self.representations.add(representation)
        self.injected_bytes += len(text.encode())
        self.injected_chars += len(text)
        insertion = self._event(
            "insertion",
            tool_result_ids=list(self.pending_calls),
            representation=representation,
            collection_id=self.collection_id,
            text_sha256=hashlib.sha256(text.encode()).hexdigest(),
            chars=len(text),
            utf8_bytes=len(text.encode()),
            binding=self.binding_mode,
            collection=self.collection_mode,
        )
        self.pending_calls.clear()
        if len(self.pending_insertions) < 8192:
            self.pending_insertions.append(insertion)
        else:
            self.events_omitted += 1
        if any(isinstance(value, dict) and value.get("intent") for value in values):
            self.pages += 1
        for value in values:
            if isinstance(value, dict):
                self._source(value)
        return text

    def summary(self) -> dict:
        return {
            "actual_schema_sha256": self.schema_hash,
            "loaded_graph_instructions_sha256": self.instructions_hash,
            "response_representation": sorted(self.representations),
            "model_requests": self.model_requests,
            "mcp_calls": self.mcp_calls,
            "external_reads": self.ledger.external_reads,
            "new_context_chars": self.ledger.new_chars,
            "repeated_context_chars": self.ledger.repeated_chars,
            "rehydrated_context_chars": self.ledger.rehydrated_chars,
            "pages": self.pages,
            "expansions": self.expansions,
            "compactions": self.ledger.compactions,
            "errors": self.errors,
            "retries": self.retries,
            "wire_bytes": self.wire_bytes,
            "injected_bytes": self.injected_bytes,
            "wire_measurement_scope": "compact MCP result serialization; excludes JSON-RPC framing and transport whitespace",
            "injected_chars": self.injected_chars,
            "insertion_boundary_complete": self.insertion_boundary_complete,
            "wire_duplicate_objects": self.wire_duplicate_objects,
            "unidentified_context_chars": self.ledger.unidentified_chars,
            "context_identity_complete": self.ledger.unidentified_chars == 0
            and self.context_inventory_verified
            and self.insertion_boundary_complete
            and self.ledger.complete,
            "source_ledger_entries": len(self.source_ledger),
            "source_ledger_omitted": self.source_ledger_omitted,
            "ledger_entries": len(self.ledger.seen),
            "ledger_omitted_entries": self.ledger.omitted_entries,
            "boundary_events": len(self.events),
            "boundary_events_omitted": self.events_omitted,
            "boundary_accounting_complete": self.events_omitted == 0 and self.insertion_boundary_complete,
            "binding_mode": self.binding_mode,
            "collection_mode": self.collection_mode,
            "measurement_scope": "source windows and partial line overlaps at explicit client insertion; characters are not model usage",
        }


class LeanAdapter:
    """One opt-in MCP integration for an executor with an actual insertion callback.

    register the server's advertised tools, route inspect_change through collect,
    and insert only its returned string. This is not a Codex client installation.
    The adapter never retains/suppresses source and never loads hidden tool schemas.
    """

    def __init__(
        self,
        call,
        observer: Observer,
        max_pages=16,
        max_chars=64000,
        max_seconds=60,
        max_wire_bytes=8 * 1024 * 1024,
        cancelled=None,
        collection_format="pcg-lean-collection-1",
        deadline_call=None,
        defer_insertion=False,
        max_input_tokens=None,
        count_tokens=None,
        tokenizer_id=None,
    ):
        if (
            any(type(value) is not int for value in (max_pages, max_chars, max_wire_bytes))
            or type(max_seconds) not in (int, float)
            or not 1 <= max_pages <= 64
            or not 3000 <= max_chars <= 256000
            or not 1 <= max_seconds <= 600
            or not 1024 <= max_wire_bytes <= 16 * 1024 * 1024
        ):
            raise ValueError("collector budget out of range")
        self.call = call
        self.observer = observer
        self.max_pages = max_pages
        self.max_chars = max_chars
        self.max_seconds = max_seconds
        self.max_wire_bytes = max_wire_bytes
        self.cancelled = cancelled or (lambda: False)
        if collection_format not in ("pcg-lean-collection-1", "pcg-lean-collection-2"):
            raise ValueError("unknown collection format")
        if collection_format == "pcg-lean-collection-2" and deadline_call is None:
            raise ValueError("fused collection requires a binding-enforced deadline_call")
        self.collection_format = collection_format
        self.deadline_call = deadline_call
        self.defer_insertion = defer_insertion
        self.pending_insertion = None
        if max_input_tokens is not None and (
            type(max_input_tokens) is not int
            or not 1 <= max_input_tokens <= 1000000
            or not callable(count_tokens)
            or not isinstance(tokenizer_id, str)
            or not 1 <= len(tokenizer_id) <= 128
        ):
            raise ValueError("exact insertion budget requires an explicit tokenizer and identity")
        self.max_input_tokens = max_input_tokens
        self.count_tokens = count_tokens
        self.tokenizer_id = tokenizer_id

    def _tokens_fit(self, text: str) -> bool:
        if self.max_input_tokens is None:
            return True
        count = self.count_tokens(text)
        if type(count) is not int or count < 0:
            raise ValueError("tokenizer must return a nonnegative integer")
        return count <= self.max_input_tokens

    def _inject(self, result: dict, representation: str, transformed=None, prompt_windows=None) -> str:
        text = transformed if transformed is not None else result["content"][0]["text"]
        if not self._tokens_fit(text):
            raise ValueError("prepared insertion exceeds exact tokenizer budget; nothing inserted")
        if self.defer_insertion:
            self.pending_insertion = (
                result,
                representation,
                transformed,
                prompt_windows,
            )
            return transformed if transformed is not None else result["content"][0]["text"]
        return self.observer.inject(result, representation, transformed, prompt_windows)

    def commit_insertion(self) -> None:
        """Record a deferred representation only after the actual insertion succeeded."""
        if self.pending_insertion is None:
            raise ValueError("no prepared insertion")
        self.observer.inject(*self.pending_insertion)
        self.pending_insertion = None

    def _call(self, arguments: dict, deadline: float) -> dict:
        self.call_id = self.observer.begin_call("inspect_change", arguments)
        try:
            if self.deadline_call is not None:
                return self.deadline_call(
                    "inspect_change",
                    arguments,
                    deadline=deadline,
                    cancelled=self.cancelled,
                )
            return self.call("inspect_change", arguments)
        except Exception as error:
            self.observer.errors += 1
            self.observer._event("tool_failure", call_id=self.call_id, error_kind=type(error).__name__)
            raise

    def collect(self, arguments: dict) -> dict:
        self.observer.collection_mode = self.collection_format
        self.observer.start_collection()
        deadline = time.monotonic() + self.max_seconds
        if arguments.get("format") == "audit":
            raw = self._call(arguments, deadline)
            self.observer.observe_wire(raw, "inspect_change", arguments, self.call_id)
            text = (
                compact(raw.get("structuredContent"))
                if raw.get("structuredContent") is not None
                else "".join(c.get("text", "") for c in raw.get("content", []) if c.get("type") == "text")
            )
            if len(text) > self.max_chars or not self._tokens_fit(text):
                inserted = self._inject(
                    {},
                    "transformed",
                    compact(
                        {
                            "complete": False,
                            "limit": "collector_context_budget",
                            "requested_format": "audit",
                        }
                    ),
                    prompt_windows=[],
                )
                return {
                    "text": inserted,
                    "complete": False,
                    "reason": "collector_context_budget",
                }
            return {
                "text": self._inject(raw, "text"),
                "complete": False,
                "reason": "explicit_audit",
            }
        if not arguments.get("intent") or "context" in arguments or "cursor" in arguments:
            raise ValueError("lean adapter requires intent and owns pagination; no retention context")
        arguments = dict(arguments, format="lean")
        request = dict(arguments)
        want_optional = arguments.get("options", {}).get("include_tests") is True
        values = []
        identity = None
        stopped = None
        started = time.monotonic()
        wire_bytes = 0
        for _ in range(self.max_pages):
            if self.cancelled():
                stopped = "cancelled"
                break
            if time.monotonic() - started >= self.max_seconds:
                stopped = "collector_time_budget"
                break
            try:
                raw = self._call(arguments, deadline)
            except TimeoutError:
                stopped = "collector_time_budget"
                break
            except InterruptedError:
                stopped = "cancelled"
                break
            self.observer.observe_wire(raw, "inspect_change", arguments, self.call_id)
            wire_bytes += len(compact(raw).encode())
            if self.cancelled() or time.monotonic() - started >= self.max_seconds or wire_bytes > self.max_wire_bytes:
                stopped = (
                    "cancelled"
                    if self.cancelled()
                    else "collector_wire_budget"
                    if wire_bytes > self.max_wire_bytes
                    else "collector_time_budget"
                )
                break
            if raw.get("isError"):
                # Errors remain in the cost/sequence and are returned once.
                if len(raw["content"][0]["text"]) > self.max_chars:
                    return {
                        "text": self._inject(
                            {},
                            "transformed",
                            compact({"complete": False, "limit": "collector_error_budget"}),
                            prompt_windows=[],
                        ),
                        "complete": False,
                        "reason": "collector_error_budget",
                    }
                return {
                    "text": self._inject(raw, "text"),
                    "complete": False,
                    "reason": "tool_error",
                }
            page = raw["structuredContent"]
            if page.get("restart_required"):
                stopped = "restart_required"
                values.clear()
                break
            if page.get("format") != "pcg-lean-1":
                raise ValueError("server did not return the registered lean contract")
            if identity is None:
                identity = page["snapshot"]
            elif page["snapshot"] != identity:
                stopped = "snapshot_changed"
                values.clear()
                break
            if self.collection_format == "pcg-lean-collection-2":
                try:
                    # Validate before either the size decision or the legacy fallback.
                    candidate = select_collection(values + [page], {}, request)
                except CollectionConflict as conflict:
                    stopped = str(conflict)
                    values.clear()
                    break
                candidate_chars = len(compact(candidate))
            else:
                candidate_chars = len(compact({"pages": values + [page]}))
            candidate_text = (
                compact(candidate)
                if self.collection_format == "pcg-lean-collection-2"
                else compact({"pages": values + [page]})
            )
            if candidate_chars + 512 > self.max_chars or not self._tokens_fit(candidate_text):
                stopped = (
                    "collector_context_budget" if candidate_chars + 512 > self.max_chars else "collector_token_budget"
                )
                break
            values.append(page)
            if not page["next_cursor"] or (
                not want_optional and page["completion"]["required_inventory"]["remaining_known"] == 0
            ):
                break
            arguments = dict(arguments, cursor=page["next_cursor"])
        else:
            stopped = "collector_page_budget"
        complete = (
            stopped is None and bool(values) and values[-1]["completion"]["required_inventory"]["state"] == "complete"
        )
        windows = [
            dict(
                window,
                file=source["file"],
                root_id=page["snapshot"]["root_id"],
                source_hash=source["source_hash"],
            )
            for page in values
            for source in page["sources"]
            for window in source["windows"]
        ]
        collection = {
            "complete": complete,
            "limit": stopped,
            "max_pages": self.max_pages,
            "max_chars": self.max_chars,
            "max_seconds": self.max_seconds,
            "max_wire_bytes": self.max_wire_bytes,
        }
        if self.collection_format == "pcg-lean-collection-2":
            selected = select_collection(values, collection, request)
            windows = source_windows(selected)
            text = compact(selected)
        else:
            text = compact(
                {
                    "format": "pcg-lean-collection-1",
                    "pages": values,
                    "collection": collection,
                }
            )
        if len(text) > self.max_chars or not self._tokens_fit(text):
            complete = False
            stopped = "collector_context_budget" if len(text) > self.max_chars else "collector_token_budget"
            text = compact(
                {
                    "format": self.collection_format,
                    "collection": {"complete": False, "limit": stopped},
                }
            )
            windows = []
        self.observer.pages += len(values)
        inserted = self._inject({}, "transformed", text, prompt_windows=windows)
        return {"text": inserted, "complete": complete, "reason": stopped}
