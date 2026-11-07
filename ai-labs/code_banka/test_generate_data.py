"""The generated dataset is deterministic, consistent with covenants.py and grounded in its documents."""
import json
import tempfile
import unittest
from pathlib import Path

import generate_data
from covenants import evaluate
from sources import page_text


def load_documents(root, company_id):
    folder = root / "companies" / company_id
    return {p.name: p.read_text(encoding="utf-8") for p in folder.glob("*.md")}


class GeneratedDataTests(unittest.TestCase):
    def generate(self, folder):
        generate_data.main(["--out", str(folder)])
        return {p.relative_to(folder): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}

    def test_deterministic_and_consistent(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            root = Path(a) / "d"
            first, second = self.generate(root), self.generate(Path(b) / "d")
            self.assertEqual(first, second)
            cases = json.loads(first[Path("expected.json")])
            self.assertEqual(len(cases), 36)
            for case in cases:
                items = {k: v["value"] for k, v in case["expected_items"].items()}
                self.assertEqual(evaluate(items, case["expected_spec"], case["period"])["status"],
                                 case["expected_status"], case["case_id"])
                self.assertTrue((root / case["statement"]).exists())

    def test_test_set_is_separate_deterministic_and_verifiable(self):
        from sources import evaluate_with_sources
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b, \
                tempfile.TemporaryDirectory() as c:
            test_root, dev_root = Path(a) / "t", Path(c) / "d"
            generate_data.main(["--set", "test", "--out", str(test_root)])
            first = {p.relative_to(test_root): p.read_bytes() for p in test_root.rglob("*") if p.is_file()}
            generate_data.main(["--set", "test", "--out", str(Path(b) / "t")])
            second = {p.relative_to(Path(b) / "t"): p.read_bytes() for p in (Path(b) / "t").rglob("*") if p.is_file()}
            self.assertEqual(first, second)
            generate_data.main(["--out", str(dev_root)])
            test_cases = json.loads((test_root / "expected.json").read_text(encoding="utf-8"))
            dev_cases = json.loads((dev_root / "expected.json").read_text(encoding="utf-8"))
            self.assertEqual(len(test_cases), 18)
            self.assertFalse({c["company_id"] for c in test_cases} & {c["company_id"] for c in dev_cases})
            for case in test_cases:   # the strict verifier must support the shuffled contracts
                docs = load_documents(test_root, case["company_id"])
                items = {k: v["value"] for k, v in case["expected_items"].items()}
                result = evaluate_with_sources(items, case["expected_spec"], case["period"], docs)
                self.assertEqual(result["status"], case["expected_status"], case["case_id"])
            counts = {len([a for a in load_documents(test_root, cid)["smlouva.md"].splitlines()
                           if a.startswith("## Článek")]) for cid in {c["company_id"] for c in test_cases}}
            self.assertEqual(counts, {12})

    def test_cited_article_is_on_cited_page(self):
        with tempfile.TemporaryDirectory() as a:
            root = Path(a) / "d"
            generate_data.main(["--out", str(root)])
            for case in json.loads((root / "expected.json").read_text(encoding="utf-8")):
                spec, docs = case["expected_spec"], load_documents(root, case["company_id"])
                citations = [spec["ebitda"]["citation"], spec["debt"]["citation"]]
                citations += [c["citation"] for c in spec["covenants"]] + [w["citation"] for w in spec["waivers"]]
                for cite in citations:
                    text, error = page_text(docs, cite)
                    self.assertIsNone(error, f"{case['case_id']}: {error}")
                    if cite["article"] is not None:
                        self.assertTrue(text.startswith(f"## Článek {cite['article']} –"), case["case_id"])

    def test_wrong_page_is_detected(self):
        docs = {"smlouva.md": "[strana 1]\n\n## Článek 1 – A\n\ntext\n\n[strana 2]\n\n## Článek 2 – B\n\ntext\n"}
        self.assertIsNone(page_text(docs, {"document": "smlouva.md", "article": "2", "page": 2})[1])
        self.assertIn("not on page", page_text(docs, {"document": "smlouva.md", "article": "2", "page": 1})[1])

    def test_never_deletes_foreign_or_source_folders(self):
        with tempfile.TemporaryDirectory() as a:
            foreign = Path(a) / "foreign"
            foreign.mkdir()
            (foreign / "keep.txt").write_text("important")
            with self.assertRaises(SystemExit):
                generate_data.main(["--out", str(foreign)])
            self.assertEqual((foreign / "keep.txt").read_text(), "important")
            # A folder the generator created itself may be replaced.
            own = Path(a) / "own"
            generate_data.main(["--out", str(own)])
            generate_data.main(["--out", str(own)])
            self.assertTrue((own / generate_data.MARKER).is_file())
        code_dir = Path(generate_data.__file__).resolve().parent
        for target in (code_dir, code_dir.parent):
            with self.assertRaises(SystemExit):
                generate_data.main(["--out", str(target)])
        self.assertTrue((code_dir / "generate_data.py").exists())


if __name__ == "__main__":
    unittest.main()
