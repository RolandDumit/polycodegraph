"""Wire preservation and native death regressions, with no model calls."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from efficiency_capture import INPUT_LIMIT


class WireCapture(unittest.TestCase):
    def proxy(self, root: Path, backend: str) -> subprocess.Popen:
        # macOS tempfile roots may be spelled through /var -> /private/var.
        # Pass the canonical trusted fixture root; the recorder still rejects links.
        root = root.resolve(strict=True)
        source = (
            "from efficiency_capture import capture;from pathlib import Path;import sys;"
            f"sys.exit(capture([sys.executable,'-c',{backend!r}],Path({str(root)!r}),'test',grace_seconds=2))"
        )
        return subprocess.Popen(
            [sys.executable, "-c", source],
            cwd=Path(__file__).resolve().parent,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def test_backend_eof_exits_while_client_stdin_is_open(self):
        with tempfile.TemporaryDirectory() as temp:
            process = self.proxy(
                Path(temp), "import os,sys;os.write(1,b'{}\\n');sys.exit(7)"
            )
            try:
                self.assertEqual(process.stdout.readline(), b"{}\n")
                self.assertEqual(process.wait(timeout=3), 7)
                self.assertFalse(process.stdin.closed)
            finally:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=3)

    def test_client_eof_drains_responses_and_preserves_exact_wire(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            backend = "import sys\nfor line in sys.stdin.buffer:sys.stdout.buffer.write(line);sys.stdout.buffer.flush()"
            process = self.proxy(root, backend)
            frames = (
                b'{"id":1,"params":{"_meta":{"progressToken":"opaque"}}}\n{"id":2}\n'
            )
            out, err = process.communicate(frames, timeout=5)
            self.assertEqual(process.returncode, 0, err)
            self.assertEqual(out, frames)
            events = [
                json.loads(line)
                for p in root.glob("*.jsonl")
                for line in p.read_text().splitlines()
            ]
            for direction in ("original", "visible"):
                recorded = [e for e in events if e["direction"] == direction]
                self.assertEqual(len(recorded), 2)
                for event, frame in zip(
                    recorded, frames.splitlines(keepends=True), strict=True
                ):
                    self.assertEqual(
                        event["wire_sha256"], hashlib.sha256(frame).hexdigest()
                    )
                    self.assertEqual(event["wire_bytes"], len(frame))
                    self.assertEqual(event["value"], json.loads(frame))

    def test_oversized_input_terminates_backend_without_hanging(self):
        with tempfile.TemporaryDirectory() as temp:
            process = self.proxy(Path(temp), "import time;time.sleep(30)")
            process.communicate(b"x" * INPUT_LIMIT + b"\n", timeout=5)
            self.assertNotEqual(process.returncode, 0)
            self.assertTrue(list(Path(temp).glob("test-*.jsonl")))


if __name__ == "__main__":
    unittest.main()
