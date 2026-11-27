"""Offline readiness tests; no Docker, database or network calls."""
import contextlib
import io
import json
import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

import lab_start


class StartupTests(unittest.TestCase):
    def test_docker_custom_name_and_health(self):
        rows = [{"Names": "lab-db", "Image": "custom-db", "Status": "Up 2 minutes (healthy)"}]
        result = types.SimpleNamespace(stdout=json.dumps(rows[0]), returncode=0)
        with patch.dict(os.environ, {"LAB_DB_CONTAINER": "lab-db"}), patch.object(lab_start.subprocess, "run", return_value=result):
            self.assertIn("lab-db", lab_start.check_docker())
            rows[0]["Status"] = "Up 2 minutes (unhealthy)"
            result.stdout = json.dumps(rows[0])
            with self.assertRaises(RuntimeError):
                lab_start.check_docker()

    def test_missing_database_container_fails(self):
        result = types.SimpleNamespace(stdout="", returncode=0)
        with patch.dict(os.environ, {"LAB_DB_CONTAINER": ""}), patch.object(lab_start.subprocess, "run", return_value=result):
            with self.assertRaises(RuntimeError):
                lab_start.check_docker()

    def test_vector_extension_is_required_in_connected_database(self):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.execute.return_value.fetchone.return_value = None
        psycopg = types.SimpleNamespace(connect=MagicMock(return_value=connection))
        with patch.dict(sys.modules, {"psycopg": psycopg, "config": types.SimpleNamespace(PG_DSN="test-only")}):
            with self.assertRaises(RuntimeError):
                lab_start.check_database()
            connection.execute.return_value.fetchone.return_value = ("0.8.0",)
            self.assertIn("vector operation OK", lab_start.check_database())

    def run_main(self, fail=False, cloud=False):
        dotenv = types.SimpleNamespace(load_dotenv=lambda path: None)
        with patch.dict(sys.modules, {"dotenv": dotenv}), contextlib.redirect_stdout(io.StringIO()), \
             patch.object(lab_start, "check_venv", return_value="test-python"), \
             patch.object(lab_start, "check_docker", side_effect=RuntimeError() if fail else None, return_value="db up"), \
             patch.object(lab_start, "check_database", return_value="vector OK"), \
             patch.object(lab_start, "check_ollama", return_value="models OK"), \
             patch.object(lab_start.subprocess, "run", return_value=types.SimpleNamespace(returncode=0)) as proc:
            code = lab_start.main(["--cloud"] if cloud else [])
            return code, proc.call_count

    def test_failed_preflight_blocks_cloud(self):
        self.assertEqual(self.run_main(fail=True, cloud=True), (1, 0))

    def test_default_is_free_and_cloud_is_explicit(self):
        self.assertEqual(self.run_main(), (0, 0))
        self.assertEqual(self.run_main(cloud=True), (0, 1))


if __name__ == "__main__":
    unittest.main()
