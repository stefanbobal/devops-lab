import json
import tempfile
import unittest
from pathlib import Path

import t6_ops

PRICES = {"currency": "USD", "models": {"anthropic:claude-haiku-5-5": {
    "effective_from": "2026-10-30", "input_per_million": 1.0, "output_per_million": 10.0}}}


def anthropic_call(tokens_in, tokens_out, latency=2.0, finish="end_turn"):
    return dict(provider="anthropic", model="claude-haiku-5-5", latency_s=latency, finish_reason=finish,
                usage_raw=dict(input_tokens=tokens_in, output_tokens=tokens_out))


def ollama_call(count, duration_ns, latency=10.0):
    return dict(provider="ollama", model="qwen3.8:27b", latency_s=latency, finish_reason="stop",
                usage_raw=dict(prompt_eval_count=100, eval_count=count, eval_duration=duration_ns))


def run(*steps_per_case):
    rows = [dict(case_id=f"C0{i}-2026Q1", steps=steps) for i, steps in enumerate(steps_per_case, 1)]
    return dict(llm="m", rows=rows)


class OpsTests(unittest.TestCase):
    def test_cost_and_tokens_from_provider_usage(self):
        r = run([dict(step="extract", status="ok", llm=anthropic_call(1000, 100)),
                 dict(step="spec", status="ok", llm=anthropic_call(2000, 200))])
        calls = t6_ops.calls_of([r], PRICES, "2026-11-07")
        s = t6_ops.summarize([r], calls)
        self.assertEqual((s["input_tokens"], s["output_tokens"], s["calls"]), (3000, 300, 2))
        self.assertAlmostEqual(s["cost_usd"], 3000 * 1.0 / 1e6 + 300 * 10.0 / 1e6)

    def test_failed_step_still_counts_tokens_and_is_flagged(self):
        r = run([dict(step="spec", status="failed", llm=anthropic_call(500, 50))])
        s = t6_ops.summarize([r], t6_ops.calls_of([r], PRICES, "2026-11-07"))
        self.assertEqual((s["failed_steps"], s["input_tokens"]), (1, 500))

    def test_truncated_answer_is_incomplete(self):
        r = run([dict(step="spec", status="ok", llm=anthropic_call(500, 2000, finish="max_tokens"))])
        s = t6_ops.summarize([r], t6_ops.calls_of([r], PRICES, "2026-11-07"))
        self.assertEqual(s["incomplete_calls"], 1)

    def test_local_model_costs_zero_and_reports_speed(self):
        r = run([dict(step="extract", status="ok", llm=ollama_call(200, 4_000_000_000))])
        s = t6_ops.summarize([r], t6_ops.calls_of([r], PRICES, "2026-11-07"))
        self.assertEqual(s["cost_usd"], 0.0)
        self.assertAlmostEqual(s["tokens_per_second"], 50.0)

    def test_unknown_price_is_not_counted_as_zero(self):
        call = anthropic_call(100, 10)
        call["model"] = "claude-unknown"
        r = run([dict(step="extract", status="ok", llm=call)])
        s = t6_ops.summarize([r], t6_ops.calls_of([r], PRICES, "2026-11-07"))
        self.assertEqual(s["cost_unknown_calls"], 1)

    def test_steps_without_usage_are_ignored(self):
        r = run([dict(step="extract", status="ok"), dict(step="verify", status="ok")])
        self.assertEqual(t6_ops.calls_of([r], PRICES, "2026-11-07"), [])

    def test_percentile(self):
        self.assertEqual(t6_ops.percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 50), 5)
        self.assertEqual(t6_ops.percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 95), 10)
        self.assertIsNone(t6_ops.percentile([], 50))

    def test_load_files_prefers_exact_tag_repeats(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for name in ("a_r1", "a_r2", "a_7r_r1"):
                (d / f"t3_chain_{name}.json").write_text(json.dumps(dict(llm=name, rows=[])))
            self.assertEqual([r["llm"] for r in t6_ops.load_files("a", d)], ["a_r1", "a_r2"])

    def test_tag_is_required(self):
        with self.assertRaises(SystemExit):
            t6_ops.main([])


if __name__ == "__main__":
    unittest.main()
