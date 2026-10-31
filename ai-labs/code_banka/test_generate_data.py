"""The generated dataset is deterministic and consistent with covenants.py."""
import json
import tempfile
import unittest
from pathlib import Path

import generate_data
from covenants import evaluate


class GeneratedDataTests(unittest.TestCase):
    def generate(self, folder):
        generate_data.main(["--out", str(folder)])
        return {p.relative_to(folder): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}

    def test_deterministic_and_consistent(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            first, second = self.generate(Path(a) / "d"), self.generate(Path(b) / "d")
            self.assertEqual(first, second)
            cases = json.loads(first[Path("expected.json")])
            self.assertEqual(len(cases), 36)
            for case in cases:
                items = {k: v["value"] for k, v in case["expected_items"].items()}
                self.assertEqual(evaluate(items, case["expected_spec"], case["period"])["status"],
                                 case["expected_status"], case["case_id"])
                self.assertTrue((Path(a) / "d" / case["statement"]).exists())
                for cite in [case["expected_spec"]["ebitda"]["citation"]] + \
                        [c["citation"] for c in case["expected_spec"]["covenants"]]:
                    doc = Path(a) / "d" / "companies" / case["company_id"] / cite["document"]
                    text = doc.read_text(encoding="utf-8")
                    self.assertIn(f"[strana {cite['page']}]", text)
                    self.assertIn(f"Článek {cite['article']} ", text)


if __name__ == "__main__":
    unittest.main()
