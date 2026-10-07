"""Watcher-lag lifecycle regression; no native provider or model calls."""

import json
import unittest
from unittest.mock import Mock, patch

from workflow_smoke import compare_after_edit


def failure(message):
    return {"isError": True, "content": [{"text": json.dumps({"error": message})}]}


class ReviewWatcher(unittest.TestCase):
    def test_same_baseline_waits_only_for_expected_stale_hash(self):
        client = Mock()
        good = {"isError": False, "content": []}
        client.request.side_effect = [
            failure(
                "stale: source differs from snapshot during review capture/comparison"
            ),
            good,
        ]
        args = {"target": "sample.ts", "options": {"baseline": "same-handle"}}
        with patch("workflow_smoke.time.sleep"):
            response, count = compare_after_edit(client, args)
        self.assertEqual((response, count), (good, 1))
        self.assertEqual(
            client.request.call_args_list[0], client.request.call_args_list[1]
        )

    def test_provider_failure_and_expired_baseline_are_not_retried(self):
        for message in ("Provider failed during update", "baseline expired"):
            client = Mock()
            client.request.return_value = failure(message)
            response, count = compare_after_edit(client, {})
            self.assertTrue(response["isError"])
            self.assertEqual(count, 0)
            client.request.assert_called_once()

    def test_stale_deadline_remains_a_failure(self):
        client = Mock()
        client.request.return_value = failure(
            "stale: source differs from snapshot during review capture/comparison"
        )
        response, count = compare_after_edit(client, {}, max_wait_seconds=0)
        self.assertTrue(response["isError"])
        self.assertEqual(count, 0)
        client.request.assert_called_once()
