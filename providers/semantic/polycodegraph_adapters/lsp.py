"""Bounded synchronous LSP client for a trusted native rust-analyzer binary."""

from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from typing import Any

Json = dict[str, Any]


class LspClient:
    """Own a server process, framed streams and one indexing deadline."""

    def __init__(self, executable: str, directory: str, timeout: float) -> None:
        self.process = subprocess.Popen(
            [executable], cwd=directory, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        self.deadline = time.monotonic() + timeout
        self.messages: queue.Queue[Json | Exception] = queue.Queue(maxsize=256)
        self.sequence = 0
        self.status: Json = {}
        self.diagnostics: dict[str, list[Json]] = {}
        self.errors = bytearray()
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._stderr, daemon=True).start()

    def _read(self) -> None:
        stream = self.process.stdout
        assert stream is not None
        try:
            while True:
                headers: dict[str, str] = {}
                header_size = 0
                while True:
                    line = stream.readline(8193)
                    header_size += len(line)
                    if not line:
                        raise EOFError("rust-analyzer closed its output")
                    if header_size > 8192:
                        raise ValueError("Oversized LSP header")
                    if line == b"\r\n":
                        break
                    key, value = line.decode("ascii").split(":", 1)
                    headers[key.lower()] = value.strip()
                length = int(headers.get("content-length", "0"))
                if not 0 < length <= 8 * 1024 * 1024:
                    raise ValueError("Invalid LSP message length")
                data = stream.read(length)
                if len(data) != length:
                    raise EOFError("Truncated LSP message")
                message = json.loads(data)
                if not isinstance(message, dict):
                    raise ValueError("Expected an LSP object")
                self.messages.put(message)
        except Exception as error:
            self.messages.put(error)

    def _stderr(self) -> None:
        stream = self.process.stderr
        assert stream is not None
        while chunk := stream.read(1024):
            self.errors.extend(chunk[: max(0, 8192 - len(self.errors))])

    def _send(self, message: Json) -> None:
        stream = self.process.stdin
        assert stream is not None
        data = json.dumps({"jsonrpc": "2.0", **message}, ensure_ascii=False).encode("utf-8")
        stream.write(f"Content-Length: {len(data)}\r\n\r\n".encode("ascii") + data)
        stream.flush()

    def notify(self, method: str, params: Json) -> None:
        """Send a client notification without allocating a request id."""
        self._send({"method": method, "params": params})

    def _next(self) -> Json:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("rust-analyzer indexing deadline exceeded")
        message = self.messages.get(timeout=remaining)
        if isinstance(message, Exception):
            raise RuntimeError(f"{message}: {self.errors.decode('utf-8', errors='replace')}") from message
        method = message.get("method")
        params = message.get("params", {})
        if method == "experimental/serverStatus":
            self.status = params
        elif method == "textDocument/publishDiagnostics":
            self.diagnostics[params["uri"]] = params.get("diagnostics", [])
        if method and "id" in message:
            result = [None for _ in params.get("items", [])] if method == "workspace/configuration" else None
            self._send({"id": message["id"], "result": result})
        return message

    def request(self, method: str, params: Json | None) -> Any:
        """Send a request and service intervening server notifications."""
        self.sequence += 1
        identifier = self.sequence
        self._send({"id": identifier, "method": method, "params": params})
        while True:
            reply = self._next()
            if reply.get("id") != identifier or "method" in reply:
                continue
            if "error" in reply:
                raise RuntimeError(f"{method}: {reply['error']}")
            return reply.get("result")

    def ready(self) -> None:
        """Wait for the project model and VFS to finish loading."""
        while not self.status.get("quiescent"):
            self._next()
        if self.status.get("health") == "error":
            raise RuntimeError(f"rust-analyzer project error: {self.status}")

    def close(self) -> None:
        """Release streams and ensure the native server cannot outlive its owner."""
        if self.process.poll() is None:
            try:
                self.deadline = min(self.deadline, time.monotonic() + 3)
                self.request("shutdown", None)
                self.notify("exit", {})
                self.process.wait(timeout=3)
            except (OSError, RuntimeError, TimeoutError, queue.Empty, subprocess.TimeoutExpired):
                self.process.kill()
                self.process.wait(timeout=3)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            if stream:
                stream.close()
