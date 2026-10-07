"""Transparent private MCP recording inside the executor's ownership namespace.

EOF from the backend ends the proxy even while the client's stdin remains open.
This recorder observes wire payloads, never model insertion or model tokens.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import threading
from pathlib import Path

INPUT_LIMIT = 1024 * 1024
OUTPUT_LIMIT = 16 * 1024 * 1024
RECEIPT_LIMIT = 64 * 1024 * 1024


def capture(
    argv: list[str], directory: Path, prefix: str, *, grace_seconds: float = 10
) -> int:
    """Forward frames unchanged; bounded private receipts survive abnormal backend exit."""
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,23}", prefix):
        raise ValueError("invalid receipt prefix")
    path = directory.absolute()
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_dir():
        raise ValueError("receipt directory must exist without symlinks")
    receipt = os.open(
        path / f"{prefix}-{os.getpid()}.jsonl",
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    lock = threading.Lock()
    closed = False
    written = 0
    failure = []
    process = None
    timer = None

    def stop() -> None:
        if process is not None:
            try:
                if os.name == "nt":
                    process.kill()
                else:
                    os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    with os.fdopen(receipt, "wb") as log:

        def record(direction: str, frame: bytes) -> None:
            nonlocal written
            value = json.loads(frame)
            encoded = (
                json.dumps(
                    {
                        "direction": direction,
                        "value": value,
                        "wire_bytes": len(frame),
                        "wire_sha256": hashlib.sha256(frame).hexdigest(),
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode()
            with lock:
                if closed:
                    raise ValueError("recorder closed")
                if written + len(encoded) > RECEIPT_LIMIT:
                    raise ValueError("private receipt exceeds 64 MiB")
                log.write(encoded)
                log.flush()
                written += len(encoded)

        process = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
            start_new_session=os.name != "nt",
        )

        def input_frames() -> None:
            nonlocal timer
            pending = bytearray()
            try:
                while chunk := os.read(sys.stdin.fileno(), 65536):
                    pending.extend(chunk)
                    while b"\n" in pending:
                        line, _, rest = pending.partition(b"\n")
                        pending = bytearray(rest)
                        frame = line + b"\n"
                        if len(frame) > INPUT_LIMIT:
                            raise ValueError("client frame exceeds 1 MiB")
                        record("original", frame)
                        process.stdin.write(frame)
                        process.stdin.flush()
                    if len(pending) >= INPUT_LIMIT:
                        raise ValueError("client frame exceeds 1 MiB")
                if pending:
                    raise ValueError("unterminated client frame")
                process.stdin.close()
                timer = threading.Timer(grace_seconds, stop)
                timer.daemon = True
                timer.start()
            except (OSError, ValueError) as error:
                failure.append(type(error).__name__)
                stop()

        # Only this daemon reads client stdin. Backend stdout/EOF drive the main
        # lifetime, so an unexpectedly dead native server cannot leave a waiting proxy.
        reader = threading.Thread(target=input_frames, daemon=True)
        reader.start()
        try:
            while frame := process.stdout.readline(OUTPUT_LIMIT + 1):
                if len(frame) > OUTPUT_LIMIT or not frame.endswith(b"\n"):
                    raise ValueError("backend frame exceeds bound or is unterminated")
                record("visible", frame)
                sys.stdout.buffer.write(frame)
                sys.stdout.buffer.flush()
            code = process.wait(timeout=grace_seconds)
            return code if code else int(bool(failure))
        finally:
            if timer is not None:
                timer.cancel()
            if process.poll() is None:
                stop()
                process.wait(timeout=3)
            with lock:
                closed = True
            process.stdout.close()
            with contextlib.suppress(OSError):
                process.stdin.close()
