import json
import unittest
from unittest import mock

import rag_prompt
import run_meta


class PromptHashes(unittest.TestCase):
    def test_stable_between_calls(self):
        self.assertEqual(run_meta.prompt_hashes(), run_meta.prompt_hashes())

    def test_changes_when_prompt_text_changes(self):
        before = run_meta.prompt_hashes()
        with mock.patch.object(rag_prompt, "SPEC_SYSTEM_PROMPT", rag_prompt.SPEC_SYSTEM_PROMPT + " extra"):
            after = run_meta.prompt_hashes()
        self.assertNotEqual(before["spec"], after["spec"])
        self.assertEqual(before["extract"], after["extract"])

    def test_extract_changes_independently(self):
        before = run_meta.prompt_hashes()
        with mock.patch.object(rag_prompt, "EXTRACT_SYSTEM_PROMPT", rag_prompt.EXTRACT_SYSTEM_PROMPT + " x"):
            after = run_meta.prompt_hashes()
        self.assertNotEqual(before["extract"], after["extract"])
        self.assertEqual(before["spec"], after["spec"])


class TableState(unittest.TestCase):
    def test_unreachable_database_is_recorded_not_raised(self):
        with mock.patch("psycopg.connect", side_effect=OSError("no db")):
            state = run_meta.table_state()
        self.assertIn("error", state)

    def test_split_detected_from_clause_column(self):
        conn = mock.MagicMock()
        conn.__enter__.return_value = conn
        conn.execute.return_value.fetchone.return_value = (308, 100)
        with mock.patch("psycopg.connect", return_value=conn):
            state = run_meta.table_state()
        self.assertEqual(state, dict(chunks=308, chunks_with_clause=100, split_definitions=True))

    def test_no_clauses_means_not_split(self):
        conn = mock.MagicMock()
        conn.__enter__.return_value = conn
        conn.execute.return_value.fetchone.return_value = (135, 0)
        with mock.patch("psycopg.connect", return_value=conn):
            self.assertFalse(run_meta.table_state()["split_definitions"])


class Metadata(unittest.TestCase):
    def test_contains_required_fields_and_is_json_serialisable(self):
        with mock.patch.object(run_meta, "table_state", return_value={"chunks": 1}):
            meta = run_meta.run_metadata()
        for key in ("time", "prompt_version", "prompt_hashes", "llm", "embedding", "threshold", "vector_table"):
            self.assertIn(key, meta)
        self.assertEqual(meta["prompt_version"], rag_prompt.PROMPT_VERSION)
        json.dumps(meta)


if __name__ == "__main__":
    unittest.main()
