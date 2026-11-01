"""Offline import/API tests. These do not connect to PostgreSQL."""
import contextlib
import csv
import io
import json
import tempfile
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import db_store as store
import db_import


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root / "example"
        (self.run / "calls").mkdir(parents=True)
        (self.run / "contexts").mkdir()
        self.manifest = dict(fingerprint="abc", created_at="2026-11-01T10:00:00Z",
                             scenarios=[dict(id="s1",incident="Current",review_guidance="Review only")])
        self.call = dict(call_id="c1",scenario_id="s1",llm_profile="gemma",embedding_profile="bge",
                         mode="rag",status="ok",answer="First\nsecond",estimated_cost_usd=None)
        self.write("manifest.json", self.manifest)
        self.write("calls/c1.json", self.call)

    def write(self, path, data):
        (self.run / path).write_text(json.dumps(data), encoding="utf-8")

    def test_collect_preserves_unknown_cost_multiline_answer_and_guidance(self):
        runs, warnings = store.collect_runs(self.root)
        self.assertFalse(warnings)
        self.assertEqual(len(runs), 1)
        self.assertIsNone(runs[0]["calls"][0]["estimated_cost_usd"])
        self.assertEqual(runs[0]["calls"][0]["answer"], "First\nsecond")
        self.assertEqual(runs[0]["scenarios"][0]["review_guidance"], "Review only")

    def test_identity_stable_but_separate_repeated_runs(self):
        self.assertEqual(store.run_identity(self.manifest),store.run_identity(dict(self.manifest)))
        self.assertNotEqual(store.run_identity(self.manifest),store.run_identity({**self.manifest,"created_at":"later"}))

    def test_context_matches_original_runner_digest(self):
        import hashlib
        key = hashlib.sha256(json.dumps(["s1","bge"],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        self.assertEqual(store.context_key(self.call,{key:{}}),key)
        self.assertIsNone(store.context_key({**self.call,"mode":"no_history"},{key:{}}))

    def test_bad_references_rejected(self):
        self.write("calls/c1.json",{**self.call,"scenario_id":"missing"})
        with self.assertRaises(ValueError): store.collect_runs(self.root)

    def test_duplicate_call_ids_rejected(self):
        self.write("calls/duplicate.json",self.call)
        with self.assertRaises(ValueError): store.collect_runs(self.root)

    def test_csv_reviews_support_newlines_and_blank_scores(self):
        with (self.run/"quality_review.csv").open("w",encoding="utf-8",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=["call_id",*store.SCORES,"critical_error","notes"])
            writer.writeheader();writer.writerow(dict(call_id="c1",notes='A, "quote"\nnext',relevance_0_2="0"))
        runs,_=store.collect_runs(self.root)
        review=runs[0]["reviews"][0][1]
        self.assertEqual(review["notes"],'A, "quote"\nnext')
        self.assertEqual(review["relevance_0_2"],0)
        self.assertEqual(review["evidence_0_2"],"")

    def test_review_validation_rejects_invalid_scores(self):
        for value in (-1,3,True,"NaN",1.5):
            with self.assertRaises(ValueError): store.validate_review({"evidence_0_2":value})
        self.assertEqual(store.validate_review({"evidence_0_2":"2"})["evidence_0_2"],2)
        with self.assertRaises(ValueError): store.validate_review({"critical_error":"perhaps"})

    def test_completed_records_cannot_be_silently_replaced(self):
        self.assertFalse(store.should_update(self.call,dict(self.call)))
        with self.assertRaises(ValueError): store.should_update(self.call,{**self.call,"answer":"different"})
        self.assertTrue(store.should_update({**self.call,"status":"pending"},self.call))
        with self.assertRaises(ValueError): store.should_update({**self.call,"status":"pending"},{**self.call,"call_id":"other"})

    def test_dry_run_does_not_connect(self):
        with patch.object(db_import,"connect") as connect,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(db_import.main(["--results",str(self.root)]),0)
            connect.assert_not_called()

    def test_importer_reimport_is_idempotent_and_keeps_failed_calls(self):
        # Exercise importer decisions with a small SQL adapter; live PG/FK behavior
        # still requires the documented integration check on the VM.
        class Connection:
            def __init__(self):
                self.manifests={};self.calls={};self.found=None;self.rowcount=0
            def execute(self, sql, params):
                self.found=None;self.rowcount=0
                if sql.startswith("SELECT manifest"):
                    old=self.manifests.get(params[0]);self.found=(old,) if old else None
                elif "INSERT INTO llm_eval.runs" in sql:
                    self.manifests.setdefault(params[0],params[4])
                elif sql.startswith("SELECT data FROM llm_eval.calls"):
                    old=self.calls.get(tuple(params));self.found=(old,) if old else None
                elif "INSERT INTO llm_eval.calls" in sql:
                    self.calls[(params[0],params[1])]=params[-1]
                elif sql.startswith("UPDATE llm_eval.calls"):
                    self.calls[(params[3],params[4])]=params[1]
                return self
            def fetchone(self): return self.found
        self.write("calls/c1.json",{**self.call,"status":"error","error":"504 deadline exceeded"})
        runs,_=store.collect_runs(self.root)
        conn=Connection()
        module=types.SimpleNamespace(Jsonb=lambda value:value)
        with patch.dict(sys.modules,{"psycopg.types.json":module}):
            first=store.import_runs(conn,runs)
            second=store.import_runs(conn,runs)
        self.assertEqual(first["inserted_calls"],1)
        self.assertEqual(second["inserted_calls"],0)
        self.assertEqual(second["unchanged_calls"],1)
        self.assertEqual(len(conn.calls),1)
        self.assertEqual(next(iter(conn.calls.values()))["status"],"error")


class RequestTests(unittest.TestCase):
    def test_same_origin_guard(self):
        from api_server import Handler
        handler=object.__new__(Handler)
        for headers,allowed in (({"Host":"127.0.0.1:8008"},True),
            ({"Host":"127.0.0.1:8008","Origin":"http://127.0.0.1:8008"},True),
            ({"Host":"evil.invalid"},False),
            ({"Host":"127.0.0.1:8008","Origin":"https://evil.invalid"},False)):
            handler.headers=headers
            self.assertEqual(handler.local_request(),allowed)


if __name__ == "__main__":
    unittest.main()
