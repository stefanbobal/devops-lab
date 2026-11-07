import copy
import unittest

import t3_spec

SPEC = {"ebitda": {"add": ["restructuring"], "subtract": []}, "debt": {"include": ["bonds", "bank_loans"], "deduct_cash": True},
        "covenants": [{"id": "leverage", "ratio": "debt_to_ebitda", "limit": 4}], "waivers": []}


class T3Tests(unittest.TestCase):
    def test_parse_json_strips_fences_and_text(self):
        self.assertEqual(t3_spec.parse_json('Here:\n```json\n{"a": 1}\n```'), {"a": 1})
        with self.assertRaises(ValueError):
            t3_spec.parse_json("no json")

    def test_differences_ignore_order_and_citations(self):
        other = copy.deepcopy(SPEC)
        other["debt"]["include"] = ["bank_loans", "bonds"]
        other["ebitda"]["citation"] = {"document": "x"}
        self.assertEqual(t3_spec.differences(other, SPEC), [])

    def test_differences_name_the_wrong_part(self):
        other = copy.deepcopy(SPEC)
        other["covenants"][0]["limit"] = 3.5
        other["waivers"] = [{"covenant": "leverage", "period": "2026Q2"}]
        self.assertEqual(t3_spec.differences(other, SPEC), ["covenants", "waivers"])

    def test_covenant_id_is_a_free_label(self):
        other = copy.deepcopy(SPEC)
        other["covenants"][0]["id"] = "lev"
        self.assertEqual(t3_spec.differences(other, SPEC), [])

    def test_waiver_of_another_period_is_ignored(self):
        want = copy.deepcopy(SPEC)
        want["waivers"] = [{"covenant": "leverage", "period": "2026Q2"}]
        self.assertEqual(t3_spec.differences(SPEC, want, "2026Q1"), [])
        self.assertEqual(t3_spec.differences(SPEC, want, "2026Q2"), ["waivers"])


if __name__ == "__main__":
    unittest.main()
