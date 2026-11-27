import copy
import json
import unittest

import agent

CASES = json.loads((agent.DATA / "expected.json").read_text("utf-8"))
BY_ID = {c["case_id"]: c for c in CASES}
CHUNK = [{"document": "smlouva.md", "doc_type": "contract", "article": "2", "clause": "2.5", "page": 1, "text": "x"}]


def fake_chat(case, items=None, spec=None):
    """Answers the extraction prompt first and the specification prompt second, like a perfect model."""
    answers = [json.dumps({"items": items if items is not None else case["expected_items"]}),
               json.dumps(spec if spec is not None else case["expected_spec"])]
    return lambda system, user: answers.pop(0)


def run_case(case, **kw):
    return agent.run(case["company_id"], case["period"], chat=kw.pop("chat", None) or fake_chat(case),
                     retrieve_fn=lambda company, period: CHUNK)


class AgentTests(unittest.TestCase):
    def test_steps_are_recorded_in_order(self):
        out = run_case(BY_ID["C01-2026Q1"])
        self.assertEqual([s["step"] for s in out["steps"]],
                         ["extract", "check_items", "retrieve", "spec", "verify", "evaluate"])
        self.assertEqual(out["status"], "no_breach")

    def test_perfect_model_gives_expected_status_for_all_36_cases(self):
        wrong = [c["case_id"] for c in CASES if run_case(c)["status"] != c["expected_status"]]
        self.assertEqual(wrong, [])

    def test_invented_number_goes_to_human_review(self):
        case = BY_ID["C01-2026Q1"]
        items = copy.deepcopy(case["expected_items"])
        items["cash"]["value"] = 999999
        out = run_case(case, chat=fake_chat(case, items=items))
        self.assertEqual(out["status"], "human_review")
        self.assertIn("cash", out["reasons"][0])

    def test_unreadable_item_goes_to_human_review(self):
        case = BY_ID["C09-2026Q2"]
        self.assertIn("missing_item", run_case(case)["reasons"][0])

    def test_refused_spec_goes_to_human_review(self):
        case = BY_ID["C01-2026Q1"]
        out = run_case(case, chat=fake_chat(case, spec={"error": "limit missing"}))
        self.assertEqual(out["status"], "human_review")
        self.assertTrue(out["reasons"][0].startswith("spec_refused"))

    def test_waiver_applied_to_a_period_it_does_not_cover_is_stopped(self):
        case = BY_ID["C05-2026Q1"]
        spec = copy.deepcopy(case["expected_spec"])
        spec["waivers"][0]["period"] = "2026Q1"
        out = run_case(case, chat=fake_chat(case, spec=spec))
        self.assertEqual(out["status"], "human_review")
        self.assertTrue(out["reasons"][0].startswith("unverified_spec"))

    def test_bad_json_from_the_model_does_not_crash(self):
        case = BY_ID["C01-2026Q1"]
        out = run_case(case, chat=lambda system, user: "sorry, I cannot")
        self.assertEqual(out["status"], "human_review")
        self.assertTrue(out["reasons"][0].startswith("extraction_failed"))

    def test_no_chunks_goes_to_human_review(self):
        case = BY_ID["C01-2026Q1"]
        out = agent.run("C01", "2026Q1", chat=fake_chat(case), retrieve_fn=lambda c, p: [])
        self.assertEqual(out["reasons"], ["no_relevant_contract_text"])


if __name__ == "__main__":
    unittest.main()
