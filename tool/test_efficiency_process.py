"""Actual subprocess/cache/pipe regressions; these tests never invoke a model."""

from __future__ import annotations

import copy
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from efficiency_benchmark import (
    PROCESS_CAPTURE_LIMIT,
    bounded_process,
    prepare,
    run,
    validate_manifest,
)
from efficiency_process import file_size_budget
from test_comparison import manifest
from test_efficiency import event


@unittest.skipIf(
    os.name == "nt", "POSIX resource allowance requires native Windows validation"
)
class ExecutorBudgets(unittest.TestCase):
    def executable(self, root: Path, body: str) -> Path:
        command = root / "executor.py"
        command.write_text(f"#!{sys.executable}\n{body}\n")
        command.chmod(0o700)
        return command

    def test_owned_cache_allowance_does_not_raise_stdout_or_stderr_budget(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cache = root / "cache.sqlite-wal"
            command = self.executable(
                root,
                "import json, pathlib, sys\n"
                "request=json.load(sys.stdin)\n"
                "pathlib.Path(request['cache']).write_bytes(b'x'*(9*1024*1024))\n"
                "print(json.dumps({'cached':True}))",
            )
            with self.assertRaisesRegex(ValueError, "default exit"):
                bounded_process(command, {"cache": str(cache)}, root, "default", 10)
            result = bounded_process(
                command,
                {"cache": str(cache)},
                root,
                "cache",
                10,
                file_size_limit_bytes=32 * 1024 * 1024,
            )
            self.assertEqual(result, {"cached": True})
            self.assertEqual(cache.stat().st_size, 9 * 1024 * 1024)
            for descriptor, stream in ((1, "stdout"), (2, "stderr")):
                command = self.executable(
                    root,
                    f"import os\nfor _ in range(160):os.write({descriptor}, b'x'*65536)\nprint('{{}}')",
                )
                with self.assertRaisesRegex(ValueError, stream + " exceeds 8 MiB"):
                    bounded_process(
                        command,
                        {},
                        root,
                        stream,
                        10,
                        file_size_limit_bytes=32 * 1024 * 1024,
                    )
                self.assertEqual(
                    (root / (stream + "." + stream)).stat().st_size,
                    PROCESS_CAPTURE_LIMIT,
                )

    def test_unread_stdin_cannot_bypass_executor_timeout(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            command = self.executable(root, "import time\ntime.sleep(30)")
            start = time.monotonic()
            with self.assertRaises(subprocess.TimeoutExpired):
                bounded_process(
                    command, {"text": "x" * (1024 * 1024)}, root, "timeout", 1
                )
            self.assertLess(time.monotonic() - start, 5)

    def test_descendant_retaining_pipes_is_bounded_and_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            command = self.executable(
                root,
                "import subprocess, sys\nsubprocess.Popen([sys.executable, '-c', 'import time;time.sleep(30)'])\nprint('{}')",
            )
            start = time.monotonic()
            with self.assertRaisesRegex(ValueError, "retained capture pipes"):
                bounded_process(command, {}, root, "retained", 10)
            self.assertLess(time.monotonic() - start, 5)

    def test_bad_file_budget_is_rejected_before_launch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            marker = root / "launched"
            command = self.executable(
                root,
                f"from pathlib import Path\nPath({str(marker)!r}).touch()\nprint('{{}}')",
            )
            for value in (True, 0, 8 * 1024 * 1024 - 1, 512 * 1024 * 1024 + 1, "512"):
                with self.assertRaises(ValueError):
                    bounded_process(
                        command, {}, root, "invalid", 10, file_size_limit_bytes=value
                    )
            self.assertFalse(marker.exists())


class CampaignReservation(unittest.TestCase):
    def test_after_attempt_policy_requires_explicit_overshoot_authorization(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            m = manifest(root, n=2, task_count=1)
            m["budget"]["reservation_policy"] = "remaining_positive"
            self.assertIn(
                "budget: explicit acceptance of final-attempt overshoot required",
                validate_manifest(m, root),
            )
            with self.assertRaisesRegex(ValueError, "overshoot"):
                validate_manifest(m, root, launch=True)
            m["budget"]["final_attempt_overshoot_accepted"] = True
            self.assertEqual(validate_manifest(m, root, launch=True), [])
            m["limits"]["executor_file_size_bytes"] = 32 * 1024 * 1024
            with self.assertRaisesRegex(ValueError, "enforcement status"):
                validate_manifest(m, root)
            m["limits"]["enforcement"]["executor_file_size_bytes"] = "enforced"
            self.assertEqual(validate_manifest(m, root), [])
            with self.assertRaises(ValueError):
                file_size_budget(512 * 1024 * 1024 + 1)

    def test_known_remaining_budget_allows_next_attempt_and_stops_after_overshoot(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = manifest(root, n=4, task_count=1)
            original["limits"].update(
                attempts_per_cell=1, max_uncached_input_tokens=100
            )
            original["budget"].update(max_uncached_input_tokens=20)

            def execute(command, request, local, label, timeout, **kwargs):
                if label == "oracle":
                    return {"accepted": True}
                return {"attempt_id": request["attempt_id"], "usage_events": [event()]}

            with patch(
                "efficiency_comparison.bounded_process", side_effect=execute
            ) as executor:
                jobs = prepare(original, root, root / "historical")
                self.assertEqual(
                    run(
                        original,
                        jobs,
                        root / "executor",
                        root / "oracle",
                        root / "historical",
                    ),
                    [],
                )
                executor.assert_not_called()
            updated = copy.deepcopy(original)
            updated["budget"].update(
                reservation_policy="remaining_positive",
                final_attempt_overshoot_accepted=True,
            )
            with patch("efficiency_comparison.bounded_process", side_effect=execute):
                work = root / "updated"
                jobs = prepare(updated, root, work)
                results = run(updated, jobs, root / "executor", root / "oracle", work)
                # Synthetic 15-token attempts: launch at 20, then at 5, stop at -10.
                self.assertEqual(len(results), 2)
                self.assertEqual(
                    sum(r["usage"]["totals"]["uncached_input_tokens"] for r in results),
                    30,
                )
                self.assertTrue(all(r["status"] == "completed" for r in results))


if __name__ == "__main__":
    unittest.main()
