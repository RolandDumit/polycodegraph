import unittest
from token_usage import extract, evaluate, ORDER


def event(total, last=None):
    def usage(n):
        return dict(input_tokens=n * 100, cached_input_tokens=n * 50, cache_write_input_tokens=0, output_tokens=n * 10, reasoning_output_tokens=n * 2, total_tokens=n * 110)
    return {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": usage(total), "last_token_usage": usage(last if last is not None else total)}}}


class UsageTest(unittest.TestCase):
    def test_duplicates_and_resets(self):
        usage = extract([event(1), event(1), event(2, 1), event(1), event(2, 1)])
        self.assertEqual(usage["usage_events"], 4)
        self.assertEqual(usage["duplicates_ignored"], 1)
        self.assertEqual(usage["counter_resets"], 1)
        self.assertEqual(usage["uncached_input_tokens"], 200)
        self.assertEqual(usage["total_token_usage"]["total_tokens"], 440)

    def test_missing_or_disagreeing_counters(self):
        for events in ([], [event(2, 1)], [event(1), event(3, 1)]):
            with self.assertRaises(ValueError):
                extract(events)

    def test_reasoning_and_cache_are_subsets(self):
        e = event(1)
        e["payload"]["info"]["total_token_usage"]["cached_input_tokens"] = 101
        with self.assertRaises(ValueError):
            extract([e])

    def test_gate_includes_cached_output_and_correctness(self):
        runs = {key: dict(extract([event(1)]), model=["same"], reasoning_effort=["high"]) for key in ORDER}
        validation = dict.fromkeys(ORDER, True)
        for key in ("C1", "C2"):
            runs[key]["uncached_input_tokens"] = 35  # -30% vs A/B
            runs[key]["total_token_usage"]["input_tokens"] = 85
            runs[key]["total_token_usage"]["total_tokens"] = 95
        self.assertEqual(evaluate(runs, validation)["outcome"], "reached")
        runs["C1"]["total_token_usage"]["output_tokens"] = 12  # average +10%
        runs["C1"]["total_token_usage"]["total_tokens"] = 97
        self.assertEqual(evaluate(runs, validation)["outcome"], "failed")
        runs["C1"]["total_token_usage"]["output_tokens"] = 10
        for key in ("C1", "C2"):
            runs[key]["uncached_input_tokens"] = 45  # vs A -10%, vs B -10%
            runs[key]["total_token_usage"]["input_tokens"] = 95
            runs[key]["total_token_usage"]["total_tokens"] = 105
        self.assertEqual(evaluate(runs, validation)["outcome"], "partial")
        validation["C1"] = False
        self.assertEqual(evaluate(runs, validation)["outcome"], "failed")
        with self.assertRaises(ValueError):
            evaluate(dict(reversed(list(runs.items()))), validation)


if __name__ == "__main__":
    unittest.main()
