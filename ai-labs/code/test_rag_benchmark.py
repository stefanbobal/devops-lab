"""Offline tests: python -m unittest -v test_rag_benchmark (no paid API calls)."""
import contextlib
import csv
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from unittest.mock import MagicMock

import llm_metrics as metrics
import rag_test as runner
from rag import load_threshold


class UsageTests(unittest.TestCase):
    def test_prices_validated_before_calls(self):
        prices = runner.read_json(runner.BASE / "llm_prices.json")
        metrics.validate_prices(prices)
        prices["models"]["azure:gpt-5-mini"]["input_per_million"] = -1
        with self.assertRaises(ValueError):
            metrics.validate_prices(prices)

    def test_azure_reasoning_is_already_in_output(self):
        u = metrics.normalize_usage("azure", {"prompt_tokens": 1000, "completion_tokens": 80,
            "prompt_tokens_details": {"cached_tokens": 200},
            "completion_tokens_details": {"reasoning_tokens": 50}})
        self.assertEqual((u["input_tokens"], u["output_tokens"], u["reasoning_tokens"]), (1000, 80, 50))

    def test_vertex_thoughts_added_once(self):
        u = metrics.normalize_usage("vertex", {"prompt_token_count": 200, "candidates_token_count": 20,
                                                "thoughts_token_count": 30})
        self.assertEqual(u["output_tokens"], 50)

    def test_anthropic_cache_input_total(self):
        u = metrics.normalize_usage("anthropic", {"input_tokens": 100, "cache_read_input_tokens": 200,
            "cache_creation_input_tokens": 50, "output_tokens": 30})
        self.assertEqual(u["input_tokens"], 350)

    def test_missing_usage_is_unknown(self):
        for provider in ("azure", "vertex", "anthropic", "ollama"):
            self.assertIsNone(metrics.normalize_usage(provider, {})["input_tokens"])
            self.assertIsNone(metrics.normalize_usage(provider, {})["output_tokens"])

    def test_actual_price_tiers_and_effective_dates(self):
        prices = runner.read_json(runner.BASE / "llm_prices.json")
        usage = dict(input_tokens=100000, output_tokens=1000, cached_input_tokens=0, cache_creation_tokens=0)
        quote = lambda provider, model, day="2026-10-30": metrics.estimate_cost(provider, model, usage, prices, day)
        self.assertAlmostEqual(quote("anthropic", "claude-haiku-5-5")["estimated_cost_usd"], .0105)
        usage["input_tokens"] = 100001
        self.assertAlmostEqual(quote("anthropic", "claude-haiku-5-5")["estimated_cost_usd"], .0525005)
        self.assertIsNone(quote("vertex", "gemini-4-argon")["estimated_cost_usd"])
        self.assertAlmostEqual(quote("vertex", "gemini-4-argon", "2026-12-01")["estimated_cost_usd"], .420004)
        self.assertEqual(quote("ollama", "local")["estimated_cost_usd"], 0)
        self.assertIsNone(quote("azure", "unknown-deployment")["estimated_cost_usd"])

    def test_cache_cost_not_charged_twice(self):
        usage = dict(input_tokens=1000, output_tokens=100, cached_input_tokens=500, cache_creation_tokens=100)
        rate = {"effective_from": "2026-01-01", "input_per_million": 2, "output_per_million": 10,
                "cached_input_per_million": .2, "cache_creation_per_million": 2.5}
        prices = {"models": {"anthropic:test": rate}}
        value = metrics.estimate_cost("anthropic", "test", usage, prices, "2026-10-30")
        self.assertAlmostEqual(value["estimated_cost_usd"], .00215)
        del rate["cached_input_per_million"]
        self.assertIsNone(metrics.estimate_cost("anthropic", "test", usage, prices, "2026-10-30")["estimated_cost_usd"])


class AdapterTests(unittest.TestCase):
    def test_each_sdk_adapter_preserves_usage_and_incomplete_answers(self):
        for provider in ("azure", "anthropic", "vertex", "ollama"):
            with self.subTest(provider=provider):
                config = types.ModuleType("config")
                config.LLM_MODEL, config.LLM_PROVIDER = "test-model", provider
                config.GCP_PROJECT, config.VERTEX_LLM_LOCATION = "test-project", "global"
                response = types.SimpleNamespace()
                client = MagicMock()
                client.__enter__.return_value = client
                modules = {"config": config}
                raw_usage = {"input_tokens": 200, "output_tokens": 10}
                if provider == "azure":
                    response.usage = {"prompt_tokens": 200, "completion_tokens": 10}
                    response.model = "resolved"
                    response.choices = [types.SimpleNamespace(finish_reason="length", message=types.SimpleNamespace(content="partial"))]
                    client.with_options.return_value.chat.completions.create.return_value = response
                    modules["providers"] = types.SimpleNamespace(_get_azure_client=lambda: client)
                elif provider == "anthropic":
                    response.usage, response.model, response.stop_reason = raw_usage, "resolved", "max_tokens"
                    response.content = [types.SimpleNamespace(type="text", text="partial")]
                    client.messages.create.return_value = response
                    modules["anthropic"] = types.SimpleNamespace(Anthropic=lambda **kw: client)
                elif provider == "vertex":
                    response.usage_metadata = {"prompt_token_count": 200, "candidates_token_count": 10, "thoughts_token_count": 5}
                    response.text, response.model_version = "partial", "resolved"
                    response.candidates = [types.SimpleNamespace(finish_reason="MAX_TOKENS")]
                    client.models.generate_content.return_value = response
                    constructors = types.SimpleNamespace(HttpOptions=lambda **kw: kw, HttpRetryOptions=lambda **kw: kw,
                                                         GenerateContentConfig=lambda **kw: kw)
                    genai = types.ModuleType("google.genai")
                    genai.Client, genai.types = lambda **kw: client, constructors
                    google = types.ModuleType("google")
                    google.genai = genai
                    modules.update({"google": google, "google.genai": genai, "google.genai.types": constructors})
                else:
                    client.chat.return_value = dict(model="resolved", done=True, done_reason="length",
                        message={"content": "partial"}, prompt_eval_count=200, eval_count=10,
                        load_duration=100000000, eval_duration=1000000000)
                    modules["ollama"] = types.SimpleNamespace(Client=lambda **kw: client)
                with patch.dict(sys.modules, modules):
                    result = metrics.chat_measured("system", "user", 100, 10)
                self.assertEqual(result["status"], "incomplete")
                self.assertEqual(result["input_tokens"], 200)
                self.assertEqual(result["output_tokens"], 15 if provider == "vertex" else 10)
                self.assertGreater(result["llm_latency_s"], 0)
                self.assertEqual(result["answer"], "partial")


class MatrixTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scenarios = self.root / "scenarios.json"
        runner.write_json(self.scenarios, [dict(id="one", incident="Current failure", domain=None, db_type=None)])
        self.args = ["--embeddings", "gemini", "--llms", "gemma,haiku", "--scenarios", str(self.scenarios),
                     "--out", str(self.root / "run"), "--pricing-date", "2026-10-30"]
        # Load real config without requiring python-dotenv in an offline test environment.
        stub = types.ModuleType("dotenv")
        stub.load_dotenv = lambda: None
        self.addCleanup(patch.stopall)
        patch.dict(sys.modules, {"dotenv": stub}).start()
        self.requests = []

    def fake_worker(self, request, embedding, llm, timeout):
        self.requests.append((request, embedding, llm))
        if request["operation"] == "retrieve":
            return dict(status="ok", context="Frozen historical evidence", context_hash="abc", history=[],
                        retrieval_latency_s=.1)
        return dict(status="ok", answer="Verify the current logs.", provider="ollama" if llm == "gemma" else "anthropic",
                    model="gemma3:27b" if llm == "gemma" else "claude-haiku-5-5", input_tokens=100,
                    output_tokens=10, cached_input_tokens=0, cache_creation_tokens=0, reasoning_tokens=0,
                    llm_latency_s=.2, worker_wall_s=.3)

    def run_main(self, *extra):
        with contextlib.redirect_stdout(io.StringIO()), patch.object(runner, "run_worker", self.fake_worker):
            return runner.main(self.args + list(extra))

    def test_dry_run_never_calls_api(self):
        self.assertEqual(self.run_main(), 0)
        self.assertFalse(self.requests)
        self.assertFalse((self.root / "run").exists())

    def test_retrieve_once_same_prompt_and_resume_no_duplicates(self):
        self.assertEqual(self.run_main("--execute", "--max-calls", "1"), 0)
        self.assertEqual(self.run_main("--execute", "--resume"), 0)
        self.assertEqual(self.run_main("--execute", "--resume"), 0)
        retrievals = [r for r in self.requests if r[0]["operation"] == "retrieve"]
        calls = [r for r in self.requests if r[0]["operation"] == "chat"]
        self.assertEqual(len(retrievals), 1)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][0]["user"], calls[1][0]["user"])
        with (self.root / "run" / "quality_review.csv").open() as f:
            self.assertEqual(len(list(csv.DictReader(f))), 2)

    def test_resume_rejects_changed_settings(self):
        self.run_main("--execute", "--max-calls", "1")
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.run_main("--execute", "--resume", "--top-k", "4")

    def test_failed_calls_not_retried_and_cost_unknown(self):
        original = self.fake_worker
        def failure(request, embedding, llm, timeout):
            if request["operation"] == "chat":
                self.requests.append((request, embedding, llm))
                return {"status": "timeout", "error": "Deadline", "worker_wall_s": 1}
            return original(request, embedding, llm, timeout)
        self.fake_worker = failure
        self.assertEqual(self.run_main("--execute"), 1)
        count = len(self.requests)
        self.assertEqual(self.run_main("--execute", "--resume"), 1)
        self.assertEqual(len(self.requests), count)
        summary = runner.read_json(self.root / "run" / "summary.json")
        self.assertTrue(all(row["unknown_cost_calls"] == 1 for row in summary))

    def test_controls_not_multiplied_by_embeddings(self):
        self.args[1] = "gemini,bge"
        self.run_main("--execute", "--modes", "no_history")
        self.assertEqual(len(self.requests), 2)
        self.assertTrue(all(r[0]["operation"] == "chat" for r in self.requests))

    def test_interrupted_paid_call_remains_pending_and_is_not_repeated(self):
        original = self.fake_worker
        def interrupted(request, embedding, llm, timeout):
            if request["operation"] == "chat":
                raise KeyboardInterrupt()
            return original(request, embedding, llm, timeout)
        self.fake_worker = interrupted
        with self.assertRaises(KeyboardInterrupt):
            self.run_main("--execute")
        records = list((self.root / "run" / "calls").glob("*.json"))
        self.assertEqual(len(records), 1)
        self.assertEqual(runner.read_json(records[0])["status"], "pending")
        self.fake_worker = original
        self.assertEqual(self.run_main("--execute", "--resume"), 1)
        self.assertEqual(len([r for r in self.requests if r[0]["operation"] == "chat"]), 1)

    def test_threshold_missing_and_duplicate_rejected(self):
        path = self.root / "thresholds.json"
        for rows in ([], [{"model": "bge", "threshold": .6}] * 2,
                     [{"model": "bge", "threshold": True}]):
            runner.write_json(path, rows)
            with self.assertRaises(ValueError):
                load_threshold("bge", path)

    def test_duplicate_scenarios_rejected(self):
        with self.assertRaises(ValueError):
            runner.validate_scenarios([{"id": "a", "incident": "text"}] * 2)


if __name__ == "__main__":
    unittest.main()
