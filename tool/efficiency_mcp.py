"""Opt-in static workflow MCP bridge. No model calls, installation or source execution."""

from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import os
import queue
import sys
import threading
from pathlib import Path
from typing import BinaryIO

from efficiency_binding import AsyncLeanBinding
from efficiency_client import LeanAdapter, Observer
from efficiency_transport import (
    REQUEST_BYTES,
    NativeTransport,
    RpcError,
    parse_frame,
)
from efficiency_workflow import workflow_arguments, workflow_surface

VERSION = "0.10.0-dev.2"
REVISIONS = ("2025-11-25", "2025-06-18", "2025-03-26")


def error_response(request_id: str | int | None, code: int, message: str) -> dict:
    """Build a protocol error without changing a known-tool execution failure."""
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def validate_params(params: object) -> dict:
    """Validate standard request metadata even on locally cached methods."""
    if not isinstance(params, dict):
        raise RpcError({"code": -32602, "message": "Params must be an object"})
    if "_meta" in params:
        meta = params["_meta"]
        if not isinstance(meta, dict) or (
            "progressToken" in meta and type(meta["progressToken"]) not in (str, int, float)
        ):
            raise RpcError({"code": -32602, "message": "Invalid request metadata"})
    return params


class WorkflowRelay:
    """Apply a static catalog and collection policy to one native MCP session.

    Full/agent default to direct canonical results and original initialization
    instructions. Intent profiles default to fused collection and the minimal
    guide. A local profile starts no native process and registers zero PCG tools.
    Prepared output is never recorded as model insertion or provider usage.
    """

    def __init__(
        self,
        binary: Path | None,
        root: Path,
        config: Path | None,
        profile: str,
        discovery: bool = False,
        instructions: str | None = None,
        collection: str | None = None,
        **budgets,
    ) -> None:
        self.binary, self.root, self.config = binary, root, config
        self.profile, self.discovery = profile, discovery
        self.instructions = instructions or ("original" if profile in ("full", "agent") else "minimal")
        self.collection = collection or ("direct" if profile in ("local", "full", "agent") else "collection-2")
        if self.instructions not in ("original", "minimal", "none") or self.collection not in (
            "direct",
            "collection-1",
            "collection-2",
        ):
            raise ValueError("invalid relay instruction or collection policy")
        if profile == "local" and (
            discovery or collection not in (None, "direct") or instructions not in (None, "none")
        ):
            raise ValueError("local profile has no graph discovery, collection or instructions")
        if profile not in ("local", "full", "agent") and self.collection == "direct":
            raise ValueError("workflow profiles require a collector for owned pagination")
        # Validate budgets before starting a child, even for direct/local paths.
        LeanAdapter(None, Observer(), **budgets)
        self.budgets = budgets
        self.observer = Observer()
        self.transport: NativeTransport | None = None
        self.surface = workflow_surface([], "local")
        self.initialized = self.ready = False
        self.calls = asyncio.Lock()
        self.emitted = self.emitted_chars = 0
        self.tool_requests_handled = 0
        self.schema_sha256 = self.instructions_sha256 = None

    async def handle(self, method: str, params: dict) -> dict:
        """Handle lifecycle or one advertised tool with canonical backend validation."""
        if method == "tools/call":
            self.tool_requests_handled += 1
        params = validate_params(params)
        if method == "ping":
            return {}
        if method == "initialize":
            if self.initialized:
                raise RpcError({"code": -32600, "message": "Already initialized"})
            if not isinstance(params.get("protocolVersion"), str) or not all(
                isinstance(params.get(key), dict) for key in ("capabilities", "clientInfo")
            ):
                raise RpcError({"code": -32602, "message": "Invalid initialization params"})
            self.initialized = True
            if self.profile == "local":
                revision = params["protocolVersion"]
                return {
                    "protocolVersion": revision if revision in REVISIONS else REVISIONS[0],
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "polycodegraph-workflow-local", "version": VERSION},
                }
            if self.binary is None:
                raise RpcError({"code": -32000, "message": "Native binary is required for graph profiles"})
            self.transport = await NativeTransport.start(self.binary, self.root, self.config)
            async with asyncio.timeout(self.budgets.get("max_seconds", 60)):
                original = await self.transport.request("initialize", params)
                await self.transport.notify("notifications/initialized")
                catalog = await self.transport.request("tools/list", {})
            self.surface = workflow_surface(catalog["tools"], self.profile, discovery=self.discovery, continuation=True)
            result = copy.deepcopy(original)
            result["serverInfo"]["name"] = "polycodegraph-workflow"
            if self.instructions != "original":
                result["instructions"] = self.surface["instructions"] if self.instructions == "minimal" else ""
            self.schema_sha256 = hashlib.sha256(
                json.dumps(self.surface["tools"], ensure_ascii=False, separators=(",", ":")).encode()
            ).hexdigest()
            self.instructions_sha256 = hashlib.sha256(result.get("instructions", "").encode()).hexdigest()
            return result
        if not self.ready:
            raise RpcError({"code": -32000, "message": "Initialize and send notifications/initialized first"})
        if method == "tools/list":
            if set(params) - {"_meta"}:
                raise RpcError({"code": -32602, "message": "Unknown tools/list parameter"})
            return {"tools": copy.deepcopy(self.surface["tools"])}
        if method != "tools/call":
            raise RpcError({"code": -32601, "message": "Method not found"})
        if set(params) - {"name", "arguments", "_meta"}:
            raise RpcError({"code": -32602, "message": "Unknown tools/call parameter"})
        name = params.get("name")
        if not isinstance(name, str):
            raise RpcError({"code": -32602, "message": "Invalid tool call"})
        if name not in {tool["name"] for tool in self.surface["tools"]}:
            raise RpcError({"code": -32602, "message": "Tool not registered for this workflow"})
        arguments = params.get("arguments", {})
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise RpcError({"code": -32602, "message": "Invalid tool call"})
        async with self.calls:

            async def call(tool: str, args: dict) -> dict:
                forwarded = {"name": tool, "arguments": args}
                if "_meta" in params:
                    forwarded["_meta"] = params["_meta"]
                return await self.transport.request("tools/call", forwarded)

            if name == "inspect_change" and self.collection != "direct" and "cursor" in arguments:
                try:
                    workflow_arguments(self.surface, arguments)
                except (ValueError, TypeError) as error:
                    return self._tool_error(str(error))
                call_id = self.observer.begin_call(name, arguments)
                async with asyncio.timeout(self.budgets.get("max_seconds", 60)):
                    result = await call(name, arguments)
                self.observer.observe_wire(result, name, arguments, call_id)
                if len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()) > self.budgets.get(
                    "max_wire_bytes", 8 * 1024 * 1024
                ):
                    return self._tool_error("continuation wire budget exceeded; request a smaller native page")
                text = result.get("content", [{}])[0].get("text", "")
                if len(text) > self.budgets.get("max_chars", 64000):
                    return self._tool_error("continuation context budget exceeded; request a smaller native page")
                result = {"content": [{"type": "text", "text": text}], "isError": bool(result.get("isError"))}
            elif name == "inspect_change" and self.collection != "direct":
                binding = AsyncLeanBinding(
                    call,
                    self.observer,
                    self.surface,
                    collection_format="pcg-lean-" + self.collection,
                    **self.budgets,
                )
                try:
                    collected = await binding.collect(arguments)  # Prepare only; client prompt is unobservable here.
                except (ValueError, TypeError) as error:
                    return self._tool_error(str(error))
                result = {
                    "content": [{"type": "text", "text": collected["text"]}],
                    "isError": collected["reason"] in ("tool_error", "collector_error_budget"),
                }
            else:
                call_id = self.observer.begin_call(name, arguments)
                async with asyncio.timeout(self.budgets.get("max_seconds", 60)):
                    result = await call(name, arguments)
                self.observer.observe_wire(result, name, arguments, call_id)
            return self._record_result(result)

    def _record_result(self, result: dict) -> dict:
        text = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
        self.emitted += 1
        self.emitted_chars += len(text)
        self.observer._event(
            "relay_response_prepared",
            chars=len(text),
            text_sha256=hashlib.sha256(text.encode()).hexdigest(),
            insertion_observed=False,
            is_error=bool(result.get("isError")),
        )
        return result

    def _tool_error(self, message: str) -> dict:
        self.observer.errors += 1
        self.observer._event("relay_tool_error", message_sha256=hashlib.sha256(message.encode()).hexdigest())
        return self._record_result(
            {"content": [{"type": "text", "text": json.dumps({"error": message[:512]})}], "isError": True}
        )

    async def notify(self, method: str) -> None:
        """Outer lifecycle readiness is separate from the private backend session."""
        if method == "notifications/initialized" and self.initialized:
            self.ready = True

    async def close(self) -> None:
        """End the private native session; source state is never reused implicitly."""
        if self.transport:
            await self.transport.close()

    def summary(self) -> dict:
        """Report relay preparation without inferring client retention or model use."""
        return {
            "mode": "static-workflow-mcp-relay-v1",
            "profile": self.profile,
            "collection": self.collection,
            "advertised_tools": [t["name"] for t in self.surface["tools"]],
            "responses_prepared": self.emitted,
            "tool_requests_handled": self.tool_requests_handled,
            "response_chars": self.emitted_chars,
            "relay_model_calls": 0,
            "external_model_runs": None,
            "provider_usage": None,
            "provider_prompt_insertion": None,
            "advertised_schema_sha256": self.schema_sha256,
            "offered_instructions_sha256": self.instructions_sha256,
            "observer": self.observer.summary(),
        }


def read_frame(stream: BinaryIO) -> bytes | None:
    """Read/drain one frame with bounded storage; None is clean EOF."""
    line = stream.readline(REQUEST_BYTES + 2)
    if not line:
        return None
    if len(line) > REQUEST_BYTES + 1 or not line.endswith(b"\n"):
        while line and not line.endswith(b"\n"):
            line = stream.readline(65536)
        return b""  # Parse error; a following valid frame remains readable.
    return line


async def serve(relay: WorkflowRelay, stream: BinaryIO, emit) -> None:
    """Bounded JSON-RPC frontend, with independent cancellation and EOF draining."""
    incoming: queue.Queue = queue.Queue(maxsize=64)

    def read() -> None:
        try:
            while (line := read_frame(stream)) is not None:
                incoming.put(line)
        finally:
            incoming.put(None)

    threading.Thread(target=read, daemon=True).start()
    active: dict[str, asyncio.Task] = {}
    jobs: set[asyncio.Task] = set()
    serial = asyncio.Lock()

    def finished(task: asyncio.Task, key: str | None) -> None:
        jobs.discard(task)
        if key is not None and active.get(key) is task:
            active.pop(key)
        if not task.cancelled() and task.exception() is not None:
            print("workflow relay request failed: " + type(task.exception()).__name__, file=sys.stderr)

    async def dispatch(value: dict, key: str | None) -> None:
        try:
            async with serial:
                if key is None:
                    await relay.notify(value["method"])
                    return
                result = await relay.handle(value["method"], value.get("params", {}))
                await emit({"jsonrpc": "2.0", "id": value["id"], "result": result})
        except RpcError as error:
            await emit({"jsonrpc": "2.0", "id": value["id"], "error": error.error})
        except (TimeoutError, ConnectionError, OSError, ValueError) as error:
            await emit(error_response(value["id"], -32000, str(error)[:512]))
        finally:
            if key is not None:
                active.pop(key, None)

    try:
        while (line := await asyncio.to_thread(incoming.get)) is not None:
            try:
                value = parse_frame(line)
            except (ValueError, UnicodeError, RecursionError):
                await emit(error_response(None, -32700, "Parse error or oversized message"))
                continue
            if (
                not isinstance(value, dict)
                or value.get("jsonrpc") != "2.0"
                or not isinstance(value.get("method"), str)
                or ("id" in value and value["id"] is not None and type(value["id"]) not in (str, int))
            ):
                await emit(error_response(None, -32600, "Invalid Request"))
                continue
            if "id" not in value:
                if value["method"] == "notifications/cancelled":
                    params = value.get("params", {})
                    if isinstance(params, dict):
                        task = active.get(json.dumps(params.get("requestId")))
                        if task and not task.cancelling():
                            task.cancel()
                else:
                    if len(jobs) < 64:
                        task = asyncio.create_task(dispatch(value, None))
                        jobs.add(task)
                        task.add_done_callback(lambda done: finished(done, None))
                continue
            key = json.dumps(value["id"])
            if key in active:
                await emit(error_response(value["id"], -32600, "Request id already in flight"))
            elif len(jobs) >= 64:
                await emit(error_response(value["id"], -32000, "Relay queue full"))
            else:
                task = asyncio.create_task(dispatch(value, key))
                active[key] = task
                jobs.add(task)
                task.add_done_callback(lambda done, key=key: finished(done, key))
        if jobs:
            await asyncio.gather(*jobs, return_exceptions=True)
    finally:
        for task in tuple(jobs):
            task.cancel()
        if jobs:
            await asyncio.gather(*jobs, return_exceptions=True)
        await relay.close()


def main() -> None:
    """Explicit task-start opt-in; never install a client or launch a model."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--binary",
        type=Path,
        default=Path(__file__).resolve().parent.parent / ("polycodegraph.exe" if os.name == "nt" else "polycodegraph"),
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--discovery", action="store_true")
    parser.add_argument("--instructions", choices=("original", "minimal", "none"))
    parser.add_argument("--collection", choices=("direct", "collection-1", "collection-2"))
    parser.add_argument("--max-pages", type=int, default=16)
    parser.add_argument("--max-chars", type=int, default=64000)
    parser.add_argument("--max-seconds", type=float, default=60)
    parser.add_argument("--max-wire-bytes", type=int, default=8 * 1024 * 1024)
    parser.add_argument("--telemetry", type=Path, help="Create a private hashed receipt; existing paths are rejected")
    args = parser.parse_args()
    receipt = None
    relay = WorkflowRelay(
        args.binary,
        args.root,
        args.config,
        args.profile,
        args.discovery,
        args.instructions,
        args.collection,
        max_pages=args.max_pages,
        max_chars=args.max_chars,
        max_seconds=args.max_seconds,
        max_wire_bytes=args.max_wire_bytes,
    )
    if args.telemetry is not None:
        if any(parent.is_symlink() for parent in args.telemetry.absolute().parents):
            parser.error("telemetry ancestors must not be symlinks")
        receipt = os.open(args.telemetry, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)

    output_lock = asyncio.Lock()

    async def emit(value: dict) -> None:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"

        def write() -> None:
            sys.stdout.write(text)
            sys.stdout.flush()

        async with output_lock:
            await asyncio.to_thread(write)

    try:
        asyncio.run(serve(relay, sys.stdin.buffer, emit))
    finally:
        if receipt is not None:
            with os.fdopen(receipt, "w", encoding="utf-8") as output:
                json.dump({"summary": relay.summary(), "events": relay.observer.events}, output)


if __name__ == "__main__":
    main()
