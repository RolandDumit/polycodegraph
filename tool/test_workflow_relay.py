"""Real framing/async cancellation gates; trusted fixtures never invoke a model."""

from __future__ import annotations

import asyncio
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from efficiency_benchmark import bounded_process
from efficiency_mcp import WorkflowRelay, read_frame, serve
from efficiency_transport import REQUEST_BYTES, NativeTransport, RpcError, parse_frame
from test_efficiency010 import CATALOG, page, wire


def frames(*values: dict) -> io.BytesIO:
    return io.BytesIO(b"".join(json.dumps(v).encode() + b"\n" for v in values))


class Relay(unittest.IsolatedAsyncioTestCase):
    async def test_local_has_no_native_process_or_initialization_guide(self):
        relay = WorkflowRelay(Path("nonexistent"), Path("nonexistent"), None, "local")
        with patch.object(NativeTransport, "start", new_callable=AsyncMock) as start:
            result = await relay.handle(
                "initialize", {"protocolVersion": "draft", "capabilities": {}, "clientInfo": {}}
            )
            await relay.notify("notifications/initialized")
            self.assertEqual(await relay.handle("tools/list", {}), {"tools": []})
            self.assertNotIn("instructions", result)
            start.assert_not_awaited()
        with self.assertRaises(RpcError):
            await relay.handle("tools/call", {"name": "inspect_change", "arguments": {}})
        with self.assertRaises(RpcError):
            await relay.handle("tools/list", {"_meta": {"progressToken": False}})

    async def test_workflow_prepares_one_text_and_preserves_metadata_without_claiming_insertion(self):
        values = [page(remaining=1), page(offset=1, text="b\nc", start=2)]
        backend = AsyncMock()
        answers = [
            {"serverInfo": {"name": "native", "version": "fixed"}, "instructions": "ordinary"},
            {"tools": CATALOG},
            *map(wire, values),
        ]
        backend.request.side_effect = answers
        relay = WorkflowRelay(Path("native"), Path("root"), None, "rename")
        with patch.object(NativeTransport, "start", return_value=backend):
            await relay.handle("initialize", {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {}})
        await relay.notify("notifications/initialized")
        meta = {"progressToken": "correlation", "vendor/custom": {"opaque": True}}
        result = await relay.handle(
            "tools/call",
            {
                "name": "inspect_change",
                "arguments": {"target": "target", "intent": "rename", "format": "lean"},
                "_meta": meta,
            },
        )
        self.assertNotIn("structuredContent", result)
        self.assertEqual(len(result["content"]), 1)
        self.assertTrue(json.loads(result["content"][0]["text"])["collection"]["complete"])
        for call in backend.request.await_args_list[2:]:
            self.assertEqual(call.args[1]["_meta"], meta)
        receipt = relay.summary()
        self.assertIsNone(receipt["provider_prompt_insertion"])
        self.assertIsNone(receipt["observer"]["actual_schema_sha256"])
        self.assertEqual(receipt["observer"]["injected_chars"], 0)
        self.assertEqual(receipt["observer"]["mcp_calls"], 2)
        self.assertFalse(any(e["kind"] == "insertion" for e in relay.observer.events))
        rejected = await relay.handle(
            "tools/call",
            {
                "name": "inspect_change",
                "arguments": {
                    "target": "target",
                    "intent": "rename",
                    "format": "lean",
                    "options": {"destination": "private-name"},
                },
            },
        )
        self.assertTrue(rejected["isError"])
        self.assertEqual(relay.summary()["responses_prepared"], 2)
        self.assertEqual(relay.observer.errors, 1)
        self.assertNotIn("private-name", json.dumps(relay.observer.events))

    async def test_full_defaults_to_original_guide_and_direct_canonical_result(self):
        backend = AsyncMock()
        expected = wire({"ordinary": True})
        backend.request.side_effect = [
            {"serverInfo": {"name": "native"}, "instructions": "ordinary"},
            {"tools": CATALOG},
            expected,
        ]
        relay = WorkflowRelay(Path("native"), Path("root"), None, "full")
        with patch.object(NativeTransport, "start", return_value=backend):
            initial = await relay.handle(
                "initialize", {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {}}
            )
        await relay.notify("notifications/initialized")
        self.assertEqual(initial["instructions"], "ordinary")
        self.assertEqual((await relay.handle("tools/list", {}))["tools"], CATALOG)
        result = await relay.handle("tools/call", {"name": "status", "arguments": None})
        self.assertEqual(result, expected)

    async def test_frontend_strict_json_recovery_pipeline_and_eof_drain(self):
        relay = WorkflowRelay(None, Path("root"), None, "local")
        output = []

        async def emit(value):
            output.append(value)

        stream = io.BytesIO(
            b"bad\n"
            b"\x80\n"
            b'{"id":NaN}\n'
            + frames(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {}},
                },
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            ).getvalue()
        )
        await serve(relay, stream, emit)
        self.assertEqual([v["error"]["code"] for v in output[:3]], [-32700] * 3)
        self.assertEqual(output[-1], {"jsonrpc": "2.0", "id": 2, "result": {"tools": []}})

    async def test_frontend_cancels_queued_ids_allows_reuse_and_bounds_admission(self):
        entered = asyncio.Event()
        stopped = asyncio.Event()

        class FakeRelay:
            async def handle(self, method, params):
                if params.get("wait"):
                    entered.set()
                    try:
                        await asyncio.Event().wait()
                    finally:
                        stopped.set()
                return {}

            async def notify(self, method):
                pass

            async def close(self):
                pass

        output = []

        async def emit(value):
            output.append(value)

        # Queue two IDs then cancel both while the first operation is active.
        values = [
            {"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {"wait": True}},
            {"jsonrpc": "2.0", "id": 2, "method": "ping"},
            {"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 2}},
            {"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 1}},
        ]
        values.extend({"jsonrpc": "2.0", "id": i, "method": "ping"} for i in range(3, 70))
        read_fd, write_fd = os.pipe()
        with os.fdopen(read_fd, "rb") as source, os.fdopen(write_fd, "wb", buffering=0) as writer:
            running = asyncio.create_task(serve(FakeRelay(), source, emit))
            writer.write(frames(values[0]).getvalue())
            await asyncio.wait_for(entered.wait(), 1)
            writer.write(frames(*values[1:4]).getvalue())
            await asyncio.wait_for(stopped.wait(), 1)
            writer.write(frames(*values[4:], {"jsonrpc": "2.0", "id": 2, "method": "ping"}).getvalue())
            writer.close()
            await asyncio.wait_for(running, 2)
        self.assertFalse(any(v["id"] == 1 for v in output))
        self.assertEqual(sum(v["id"] == 2 for v in output), 1)
        self.assertTrue(all(v.get("result") == {} or v.get("error", {}).get("code") == -32000 for v in output))

    async def test_frontend_queue_rejects_overflow_while_cancellation_stays_live(self):
        entered = asyncio.Event()
        rejected = asyncio.Event()

        class FakeRelay:
            async def handle(self, method, params):
                if params.get("wait"):
                    entered.set()
                    await asyncio.Event().wait()
                return {}

            async def notify(self, method):
                pass

            async def close(self):
                pass

        output = []

        async def emit(value):
            output.append(value)
            if value.get("error", {}).get("code") == -32000:
                rejected.set()

        read_fd, write_fd = os.pipe()
        with os.fdopen(read_fd, "rb") as source, os.fdopen(write_fd, "wb", buffering=0) as writer:
            running = asyncio.create_task(serve(FakeRelay(), source, emit))
            writer.write(frames({"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {"wait": True}}).getvalue())
            await asyncio.wait_for(entered.wait(), 1)
            writer.write(frames(*({"jsonrpc": "2.0", "id": i, "method": "ping"} for i in range(2, 72))).getvalue())
            await asyncio.wait_for(rejected.wait(), 1)
            writer.write(
                frames({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 1}}).getvalue()
            )
            writer.close()
            await asyncio.wait_for(running, 2)
        self.assertFalse(any(v["id"] == 1 for v in output))
        self.assertTrue(any(v.get("error", {}).get("code") == -32000 for v in output))

    async def test_native_transport_cancellation_drains_late_reply_and_reaps_child(self):
        # This is a trusted protocol fixture, never indexed application code.
        program = (
            "import sys,json,time\n"
            "for line in sys.stdin:\n"
            " v=json.loads(line)\n"
            " if 'id' not in v: continue\n"
            " if v['method']=='slow': time.sleep(.1)\n"
            " print(json.dumps({'jsonrpc':'2.0','id':v['id'],'result':{'method':v['method']}}),flush=True)\n"
        )
        child = await asyncio.create_subprocess_exec(
            sys.executable, "-I", "-c", program, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE
        )
        transport = NativeTransport(child)
        first = asyncio.create_task(transport.request("slow", {}))
        await asyncio.sleep(0.03)
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        result = await asyncio.wait_for(transport.request("ping", {}), 1)
        self.assertEqual(result, {"method": "ping"})
        self.assertFalse(transport.pending)
        await transport.close()
        self.assertEqual(child.returncode, 0)

    async def test_native_invalid_utf8_fails_and_requires_restart(self):
        program = "import sys; sys.stdin.readline(); sys.stdout.buffer.write(b'\\xff\\n'); sys.stdout.flush()"
        child = await asyncio.create_subprocess_exec(
            sys.executable, "-I", "-c", program, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE
        )
        transport = NativeTransport(child)
        try:
            with self.assertRaises(ConnectionError):
                await asyncio.wait_for(transport.request("ping", {}), 1)
            with self.assertRaises(ConnectionError):
                await transport.request("ping", {})
            self.assertFalse(transport.pending)
        finally:
            await transport.close()

    async def test_native_forced_shutdown_is_bounded(self):
        child = await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            "-c",
            "import time; time.sleep(30)",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
        )
        transport = NativeTransport(child)
        pending = asyncio.create_task(transport.request("ping", {}))
        await asyncio.sleep(0)
        await asyncio.wait_for(transport.close(grace_seconds=0.05), 7)
        with self.assertRaises(ConnectionError):
            await asyncio.wait_for(pending, 1)
        self.assertIsNotNone(child.returncode)

    @unittest.skipIf(os.name == "nt", "POSIX descendant inventory")
    async def test_cleanup_targets_only_owned_descendants_across_groups(self):
        child = AsyncMock()
        child.pid, child.returncode = 42, None
        child.kill = lambda: None
        probe = AsyncMock()
        probe.returncode = 0
        probe.stdout.read.return_value = b"42 1\n43 42\n44 43\n55 1\n56 55\n"
        transport = NativeTransport(child)
        transport.reader.cancel()
        with (
            patch("efficiency_transport.asyncio.create_subprocess_exec", return_value=probe),
            patch("efficiency_transport.os.kill") as kill,
        ):
            await transport._kill_tree()
        self.assertEqual([call.args[0] for call in kill.call_args_list], [44, 43, 42])
        with self.assertRaises(asyncio.CancelledError):
            await transport.reader


class Bounds(unittest.TestCase):
    def test_native_number_depth_and_utf8_limits(self):
        for frame in [
            b"NaN",
            b"1e999",
            b"18446744073709551616",
            b"-9223372036854775809",
            b"\\xff",
            b"[" * 129 + b"]" * 129,
        ]:
            with self.subTest(frame=frame[:30]), self.assertRaises(ValueError):
                parse_frame(frame)
        self.assertEqual(parse_frame(b'{"number":18446744073709551615}'), {"number": 2**64 - 1})

    def test_oversized_and_unterminated_frames_recover(self):
        stream = io.BytesIO(b"x" * (REQUEST_BYTES + 1) + b"\n{}\n")
        self.assertEqual(read_frame(stream), b"")
        self.assertEqual(read_frame(stream), b"{}\n")
        self.assertIsNone(read_frame(stream))
        self.assertEqual(read_frame(io.BytesIO(b"{}")), b"")

    @unittest.skipIf(os.name == "nt", "POSIX resource launcher")
    def test_trusted_launcher_preserves_output_limit_and_json_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            command = root / "trusted executor"
            command.write_text(
                f"#!{sys.executable}\nimport json,sys,resource\njson.load(sys.stdin)\n"
                "json.dump({'limit':resource.getrlimit(resource.RLIMIT_FSIZE)[0]},sys.stdout)\n"
            )
            command.chmod(0o700)
            result = bounded_process(command, {}, root, "probe", 5)
            self.assertEqual(result["limit"], 8 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
