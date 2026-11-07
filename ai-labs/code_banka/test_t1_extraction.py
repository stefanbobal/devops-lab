import unittest

import t1_extraction as t1

EXPECTED = {"C01-2026Q1": {"revenue": {"value": 100, "page": 1}, "ebit": {"value": 10, "page": 1},
                           "depreciation": {"value": None, "page": 1}}}


def row(items, problems=()):
    return dict(case_id="C01-2026Q1", items=items,
                steps=[dict(step="check_items", status="problems" if problems else "ok", problems=list(problems))])


def run(*rows):
    return dict(llm="m", rows=list(rows))


class ClassifyTests(unittest.TestCase):
    def test_four_outcomes(self):
        self.assertEqual(t1.classify(5, 5), "correct")
        self.assertEqual(t1.classify(None, None), "correct")
        self.assertEqual(t1.classify(5, None), "missing")
        self.assertEqual(t1.classify(None, 7), "invented")
        self.assertEqual(t1.classify(5, 7), "wrong")


class AnalyseTests(unittest.TestCase):
    def test_perfect_extraction(self):
        a = t1.analyse([run(row({"revenue": 100, "ebit": 10, "depreciation": None}))], EXPECTED)
        self.assertEqual((a["counts"], a["clean_case_runs"], a["errors"]), ({"correct": 3}, 1, []))

    def test_wrong_number_that_passed_the_check_is_reported(self):
        a = t1.analyse([run(row({"revenue": 100, "ebit": 99, "depreciation": None}))], EXPECTED)
        self.assertEqual(a["counts"]["wrong"], 1)
        self.assertEqual(a["errors"][0]["item"], "ebit")

    def test_rejected_number_counts_as_missing_and_as_rejected(self):
        a = t1.analyse([run(row({"revenue": 100, "ebit": None, "depreciation": None},
                                ["ebit: value 11 not found on page 1"]))], EXPECTED)
        self.assertEqual((a["counts"]["missing"], a["rejected"]), (1, 1))

    def test_invented_value_for_a_missing_item(self):
        a = t1.analyse([run(row({"revenue": 100, "ebit": 10, "depreciation": 5}))], EXPECTED)
        self.assertEqual(a["counts"]["invented"], 1)

    def test_failed_extraction_makes_every_expected_value_missing(self):
        bad = dict(case_id="C01-2026Q1", items=None, steps=[dict(step="extract", status="failed")])
        a = t1.analyse([run(bad)], EXPECTED)
        self.assertEqual((a["extraction_failed"], a["counts"]["missing"], a["counts"]["correct"]), (1, 2, 1))

    def test_tag_is_required(self):
        with self.assertRaises(SystemExit):
            t1.main([])


if __name__ == "__main__":
    unittest.main()
