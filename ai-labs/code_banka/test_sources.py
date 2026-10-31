"""A specification is used only if its citations are backed by the documents."""
import copy
import json
import re
import tempfile
import unittest
from pathlib import Path

import generate_data
from sources import evaluate_with_sources, verify_sources


class SourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name) / "d"
        generate_data.main(["--out", str(cls.root)])
        cls.cases = {c["case_id"]: c for c in
                     json.loads((cls.root / "expected.json").read_text(encoding="utf-8"))}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def docs(self, company_id):
        folder = self.root / "companies" / company_id
        return {p.name: p.read_text(encoding="utf-8") for p in folder.glob("*.md")}

    def run_case(self, case_id, spec=None):
        case = self.cases[case_id]
        items = {k: v["value"] for k, v in case["expected_items"].items()}
        return evaluate_with_sources(items, spec or case["expected_spec"], case["period"],
                                     self.docs(case["company_id"]))

    def test_all_expected_specs_are_grounded(self):
        for case_id, case in self.cases.items():
            self.assertEqual(verify_sources(case["expected_spec"], self.docs(case["company_id"]), case["period"]), [], case_id)
            self.assertEqual(self.run_case(case_id)["status"], case["expected_status"], case_id)

    def fake_waiver(self, case_id, citation):
        spec = copy.deepcopy(self.cases[case_id]["expected_spec"])
        spec["waivers"].append({"covenant": "leverage", "period": self.cases[case_id]["period"],
                                "citation": citation})
        return self.run_case(case_id, spec)

    def test_invented_waiver_cannot_hide_breach(self):
        case_id = "C01-2026Q3"   # real breach, no waiver exists
        self.assertEqual(self.cases[case_id]["expected_status"], "breach")
        for citation in ({"document": "waiver_2026Q3.md", "article": None, "page": 1},   # does not exist
                         {"document": "smlouva.md", "article": None, "page": 1},         # no grant, no date
                         {"document": "smlouva.md", "article": None, "page": 99}):
            result = self.fake_waiver(case_id, citation)
            self.assertEqual(result["status"], "human_review", citation)

    def test_waiver_request_in_notes_is_not_a_waiver(self):
        result = self.fake_waiver("C06-2026Q2", {"document": "poznamky_analytika.md", "article": None, "page": 1})
        self.assertEqual(result["status"], "human_review")
        self.assertIn("analyst notes", result["reasons"][0])

    def test_contract_article_on_waivers_is_not_a_grant(self):
        # The "Prominutí a změny" article says "neprominuje"; it must not count as a granted waiver.
        contract = self.docs("C06")["smlouva.md"]
        article = re.search(r"^## Článek (\d+) – Prominutí", contract, re.MULTILINE).group(1)
        for page in range(1, 6):
            result = self.fake_waiver("C06-2026Q2", {"document": "smlouva.md", "article": article, "page": page})
            self.assertEqual(result["status"], "human_review", page)

    def test_waiver_for_other_period_is_rejected(self):
        spec = copy.deepcopy(self.cases["C05-2026Q3"]["expected_spec"])
        spec["waivers"][0]["period"] = "2026Q3"   # real letter names only 30. 6. 2026
        result = self.run_case("C05-2026Q3", spec)
        self.assertEqual(result["status"], "human_review")
        self.assertIn("test date", result["reasons"][0])

    def test_limit_not_in_source_is_rejected(self):
        spec = copy.deepcopy(self.cases["C01-2026Q3"]["expected_spec"])
        spec["covenants"][0]["limit"] = 9.0
        result = self.run_case("C01-2026Q3", spec)
        self.assertEqual(result["status"], "human_review")
        self.assertIn("limit", result["reasons"][0])

    def test_amendment_limit_must_cite_amendment(self):
        spec = copy.deepcopy(self.cases["C10-2026Q2"]["expected_spec"])
        spec["covenants"][0]["citation"] = self.cases["C10-2026Q1"]["expected_spec"]["covenants"][0]["citation"]
        result = self.run_case("C10-2026Q2", spec)   # 3,75 is not written in the original contract
        self.assertEqual(result["status"], "human_review")

    def test_old_step_down_limit_cannot_hide_breach(self):
        spec = copy.deepcopy(self.cases["C04-2026Q3"]["expected_spec"])
        spec["covenants"][0]["limit"] = 4.5
        self.assertEqual(self.run_case("C04-2026Q3", spec)["status"], "human_review")

    def test_future_limit_cannot_be_used_before_effective_date(self):
        spec = copy.deepcopy(self.cases["C04-2026Q2"]["expected_spec"])
        spec["covenants"][0]["limit"] = 4.0
        self.assertEqual(self.run_case("C04-2026Q2", spec)["status"], "human_review")

    def test_old_limit_and_original_citation_cannot_bypass_amendment(self):
        spec = copy.deepcopy(self.cases["C10-2026Q2"]["expected_spec"])
        spec["covenants"] = copy.deepcopy(self.cases["C10-2026Q1"]["expected_spec"]["covenants"])
        self.assertEqual(self.run_case("C10-2026Q2", spec)["status"], "human_review")

    def test_definition_mutations_cannot_hide_breach(self):
        for cid, section, key, value in (
            ("C03-2026Q2", "ebitda", "subtract", []),
            ("C01-2026Q3", "ebitda", "add", ["restructuring"]),
            ("C02-2026Q2", "ebitda", "add", []),
            ("C08-2026Q2", "debt", "deduct_cash", True),
            ("C03-2026Q2", "debt", "include", ["bank_loans"]),
        ):
            with self.subTest(cid=cid, section=section, key=key):
                spec = copy.deepcopy(self.cases[cid]["expected_spec"])
                spec[section][key] = value
                self.assertEqual(self.run_case(cid, spec)["status"], "human_review")

    def test_omitted_or_swapped_covenant_is_rejected(self):
        spec = copy.deepcopy(self.cases["C07-2026Q2"]["expected_spec"])
        spec["covenants"].pop()
        self.assertEqual(self.run_case("C07-2026Q2", spec)["status"], "human_review")
        spec = copy.deepcopy(self.cases["C07-2026Q2"]["expected_spec"])
        spec["covenants"][0]["ratio"] = "interest_cover"
        self.assertEqual(self.run_case("C07-2026Q2", spec)["status"], "human_review")

    def test_unknown_definition_or_clause_goes_to_human(self):
        case = self.cases["C03-2026Q2"]
        items = {k: v["value"] for k, v in case["expected_items"].items()}
        for old, new in (("EBITDA snižuje.", "EBITDA snižuje pouze po schválení."),
                         ("hodnotu 4,25.", "hodnotu 4,25 s výjimkou sezónního období.")):
            docs = self.docs("C03")
            self.assertIn(old, docs["smlouva.md"])
            docs["smlouva.md"] = docs["smlouva.md"].replace(old, new)
            self.assertEqual(evaluate_with_sources(items, case["expected_spec"], case["period"], docs)["status"],
                             "human_review")

    def test_invalid_period_goes_to_human(self):
        case = self.cases["C01-2026Q1"]
        items = {k: v["value"] for k, v in case["expected_items"].items()}
        for period in (None, "2026Q9", "2026garbageQ1"):
            self.assertEqual(evaluate_with_sources(items, case["expected_spec"], period,
                                                  self.docs("C01"))["status"], "human_review")

    def test_supported_wording_and_article_order_across_seeds(self):
        for seed in (1, 7, 42):
            with self.subTest(seed=seed), tempfile.TemporaryDirectory() as folder:
                root = Path(folder) / "data"
                generate_data.main(["--seed", str(seed), "--out", str(root)])
                for case in json.loads((root / "expected.json").read_text(encoding="utf-8")):
                    docs = {p.name: p.read_text(encoding="utf-8")
                            for p in (root / "companies" / case["company_id"]).glob("*.md")}
                    items = {k: v["value"] for k, v in case["expected_items"].items()}
                    result = evaluate_with_sources(items, case["expected_spec"], case["period"], docs)
                    self.assertEqual(result["status"], case["expected_status"], (seed, case["case_id"], result))


if __name__ == "__main__":
    unittest.main()
