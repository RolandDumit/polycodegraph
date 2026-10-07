"""Bounded async native MCP transport; only the operator-selected PCG binary runs."""

from __future__ import annotations

import asyncio
import contextlib
import json
import math
import os
import signal
from pathlib import Path

REQUEST_BYTES = 1024 * 1024
RESPONSE_BYTES = 16 * 1024 * 1024


def reject_constant(value: str) -> None:
    """JSON-RPC uses strict JSON, not Python's non-finite extensions."""
    raise ValueError("Non-finite JSON number: " + value)


def parse_frame(data: bytes) -> dict:
    """Match native UTF-8/finite-number/depth limits before forwarding a frame."""

    def integer(text: str) -> int:
        number = int(text)
        if not -(2**63) <= number < 2**64:
            raise ValueError("JSON integer exceeds native range")
        return number

    def floating(text: str) -> float:
        number = float(text)
        if not math.isfinite(number):
            raise ValueError("JSON number exceeds finite range")
        return number

    value = json.loads(data.decode("utf-8"), parse_constant=reject_constant, parse_int=integer, parse_float=floating)
    stack = [(value, 0)]
    while stack:
        item, depth = stack.pop()
        if isinstance(item, (dict, list)):
            if depth >= 128:
                raise ValueError("JSON nesting exceeds native depth")
            stack.extend((child, depth + 1) for child in (item.values() if isinstance(item, dict) else item))
    return value


class RpcError(ValueError):
    """A backend protocol error retains its JSON-RPC code and message."""

    def __init__(self, error: dict) -> None:
        super().__init__(error.get("message", "Backend protocol error"))
        self.error = error


class NativeTransport:
    """One serialized backend request, bounded framing, cancellation-safe correlation.

    Cancelled request IDs are never reused. Native cancellation preserves the
    server's transactional indexing behavior; late replies are discarded by ID.
    No background thread performs RPC waiting. EOF/invalid frames fail pending
    requests and require a new session rather than silently losing baseline handles.
    """

    def __init__(self, process: asyncio.subprocess.Process) -> None:
        self.process = process
        self.pending: dict[int, asyncio.Future] = {}
        self.sequence = 0
        self.lock = asyncio.Lock()
        self.failure: str | None = None
        self.reader = asyncio.create_task(self._read())

    @classmethod
    async def start(cls, binary: Path, root: Path, config: Path | None = None) -> NativeTransport:
        """Start native serve without a shell, package setup or project execution."""
        command = [str(binary.absolute()), "serve", "--root", str(root.absolute())]
        if config is not None:
            command.extend(["--config", str(config.absolute())])
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=None,
            limit=RESPONSE_BYTES + 1,
            start_new_session=os.name != "nt",
        )
        return cls(process)

    async def _read(self) -> None:
        try:
            while True:
                line = await self.process.stdout.readline()
                if not line:
                    raise ConnectionError("Backend EOF; restart the MCP session")
                if len(line) > RESPONSE_BYTES or not line.endswith(b"\n"):
                    raise ConnectionError("Backend frame exceeds bound or is unterminated")
                value = parse_frame(line)
                if not isinstance(value, dict) or value.get("jsonrpc") != "2.0":
                    raise ConnectionError("Invalid backend response")
                response_id = value.get("id")
                if type(response_id) is not int:
                    continue  # Native notifications have no pending response.
                future = self.pending.get(response_id)
                if future is not None and not future.done():
                    future.set_result(value)
        except (OSError, ValueError, ConnectionError, RecursionError) as error:
            self.failure = str(error)
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(ConnectionError(self.failure))

    async def notify(self, method: str, params: dict | None = None) -> None:
        """Send one bounded notification; writes contain protocol data only."""
        await self._write({"jsonrpc": "2.0", "method": method, "params": params or {}})

    async def _write(self, value: dict) -> None:
        if self.failure or self.process.returncode is not None:
            raise ConnectionError(self.failure or "Backend stopped; restart the MCP session")
        data = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode() + b"\n"
        if len(data) > REQUEST_BYTES:
            raise ValueError("Backend request frame exceeds 1 MiB")
        self.process.stdin.write(data)
        await self.process.stdin.drain()

    async def request(self, method: str, params: dict) -> dict:
        """Await one correlated response, draining abandoned IDs after cancellation."""
        async with self.lock:
            self.sequence += 1
            request_id = self.sequence
            future = asyncio.get_running_loop().create_future()
            self.pending[request_id] = future
            try:
                await self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
                value = await future
                if "error" in value:
                    raise RpcError(value["error"])
                if "result" not in value:
                    raise ConnectionError("Backend response has no result")
                return value["result"]
            except asyncio.CancelledError:
                with contextlib.suppress(ConnectionError, OSError, TimeoutError):
                    async with asyncio.timeout(0.25):
                        await self.notify("notifications/cancelled", {"requestId": request_id})
                raise
            finally:
                self.pending.pop(request_id, None)

    async def close(self, grace_seconds: float = 2) -> None:
        """Drain native EOF, then reap the owned process tree within bounded grace."""
        if self.process.stdin is not None:
            self.process.stdin.close()
        try:
            await asyncio.wait_for(self.process.wait(), grace_seconds)
        except TimeoutError:
            try:
                await self._kill_tree()
            finally:
                if self.process.returncode is None:
                    with contextlib.suppress(ProcessLookupError):
                        self.process.kill()
                await asyncio.wait_for(self.process.wait(), 3)
        finally:
            self.failure = self.failure or "Backend session closed; restart the MCP session"
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(ConnectionError(self.failure))
            self.reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.reader

    async def _kill_tree(self) -> None:
        if self.process.returncode is not None:
            return
        if os.name == "nt":
            killer = await asyncio.create_subprocess_exec(
                "taskkill",
                "/PID",
                str(self.process.pid),
                "/T",
                "/F",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                await asyncio.wait_for(killer.wait(), 3)
            except TimeoutError:
                killer.kill()
                await killer.wait()
            if self.process.returncode is None:
                self.process.kill()
            return
        # Providers own separate process groups. Capture descendant IDs rather
        # than assuming the native server's group contains every compiler worker.
        probe = await asyncio.create_subprocess_exec(
            "/bin/ps",
            "-eo",
            "pid=,ppid=",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            limit=REQUEST_BYTES,
        )
        try:
            async with asyncio.timeout(3):
                output = await probe.stdout.read(REQUEST_BYTES + 1)
                if len(output) > REQUEST_BYTES:
                    raise ConnectionError("Process inventory exceeds cleanup bound")
                await probe.wait()
            parents = {int(parts[0]): int(parts[1]) for line in output.splitlines() if len(parts := line.split()) == 2}
            owned = [self.process.pid]
            for parent in owned:
                owned.extend(pid for pid, ppid in parents.items() if ppid == parent and pid not in owned)
            for pid in reversed(owned):
                with contextlib.suppress(ProcessLookupError):
                    os.kill(pid, signal.SIGKILL)
        finally:
            if probe.returncode is None:
                probe.kill()
                await probe.wait()
            if self.process.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    self.process.kill()
