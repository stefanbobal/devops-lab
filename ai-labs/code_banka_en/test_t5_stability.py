import json
import tempfile
import unittest
from pathlib import Path

import t5_stability as t5


def spec(limit):
    return dict(ebitda={"add": [], "subtract": []}, debt={"include": ["bank_loans"], "deduct_cash": True},
                covenants=[dict(id="x", ratio="debt_to_ebitda", limit=limit)], waivers=[])


def row(got, limit=3.0, expected="no_breach", reasons=()):
    return dict(case_id="C10-2026Q1", expected=expected, got=got, stage=None, reasons=list(reasons),
                seconds=1.0, spec=spec(limit), items={"revenue": 1})


def run(*rows):
    return dict(llm="m", rows=list(rows))


class CategoryTests(unittest.TestCase):
    def test_same_status_is_stable(self):
        self.assertEqual(t5.category(["breach", "breach", "breach"]), "stable")

    def test_human_review_vs_correct_is_harmless(self):
        self.assertEqual(t5.category(["no_breach", "human_review", "no_breach"]), "harmless")

    def test_breach_vs_no_breach_is_dangerous(self):
        self.assertEqual(t5.category(["breach", "human_review", "no_breach"]), "dangerous")


class AnalyseTests(unittest.TestCase):
    def test_counts_correct_runs_and_spec_variants(self):
        runs = [run(row("no_breach", 3.0)), run(row("human_review", 3.75)), run(row("no_breach", 3.0))]
        c = t5.analyse(runs)[0]
        self.assertEqual((c["category"], c["correct"], c["spec_variants"], c["item_variants"]),
                         ("harmless", 2, 2, 1))

    def test_same_status_but_different_spec_is_visible(self):
        runs = [run(row("no_breach", 3.0)), run(row("no_breach", 3.75))]
        c = t5.analyse(runs)[0]
        self.assertEqual((c["category"], c["spec_variants"]), ("stable", 2))

    def test_missing_spec_does_not_crash(self):
        bad = row("human_review")
        bad["spec"] = None
        self.assertEqual(t5.analyse([run(bad), run(row("no_breach"))])[0]["spec_variants"], 2)


class LoadTests(unittest.TestCase):
    def test_exact_tag_only_and_numeric_order(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for name in ("t5_a_r1", "t5_a_r2", "t5_a_r10", "t5_a_7r_r1"):
                (d / f"t3_chain_{name}.json").write_text(json.dumps(dict(llm=name, rows=[])))
            self.assertEqual([r["llm"] for r in t5.load_runs("t5_a", d)], ["t5_a_r1", "t5_a_r2", "t5_a_r10"])

    def test_tag_is_required(self):
        with self.assertRaises(SystemExit):
            t5.main([])


if __name__ == "__main__":
    unittest.main()
