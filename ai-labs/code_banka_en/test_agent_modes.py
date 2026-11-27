import json
import unittest

import agent
from covenants import GENERIC_SPEC

CASES = json.loads((agent.DATA / "expected.json").read_text("utf-8"))
BY_ID = {c["case_id"]: c for c in CASES}


def items_chat(case, spec_answer=None):
    """Perfect extraction first; a specification answer second (only used by modes that ask for one)."""
    answers = [json.dumps({"items": case["expected_items"]}),
               json.dumps(spec_answer if spec_answer is not None else case["expected_spec"])]
    return lambda system, user: answers.pop(0)


def run(case, mode, **kw):
    return agent.run(case["company_id"], case["period"], mode=mode, chat=kw.pop("chat", None) or items_chat(case),
                     retrieve_fn=kw.pop("retrieve_fn", None), **kw)


class ModeValidation(unittest.TestCase):
    def test_unknown_mode_is_refused(self):
        with self.assertRaises(ValueError):
            agent.run("C01", "2026Q1", mode="magic", chat=lambda s, u: "{}")

    def test_result_records_the_mode(self):
        self.assertEqual(run(BY_ID["C01-2026Q1"], "generic")["mode"], "generic")


class GenericMode(unittest.TestCase):
    def test_matches_the_generic_rule_status_for_all_cases(self):
        wrong = [c["case_id"] for c in CASES if run(c, "generic")["status"] != c["generic_rule_status"]]
        self.assertEqual(wrong, [])

    def test_breaks_exactly_the_cases_listed_as_failing_without_contract(self):
        broken = {c["case_id"] for c in CASES if run(c, "generic")["status"] != c["expected_status"]}
        self.assertEqual(broken, {c["case_id"] for c in CASES if c["fails_without_contract"]})

    def test_never_asks_the_model_for_a_specification(self):
        calls = []
        case = BY_ID["C01-2026Q1"]
        answers = [json.dumps({"items": case["expected_items"]})]
        def chat(system, user):
            calls.append(user)
            return answers.pop(0)
        out = run(case, "generic", chat=chat)
        self.assertEqual(len(calls), 1)
        self.assertEqual(out["spec"], GENERIC_SPEC)
        self.assertEqual([s["status"] for s in out["steps"] if s["step"] in ("retrieve", "spec", "verify")],
                         ["skipped"] * 3)


class FullMode(unittest.TestCase):
    def test_gives_the_model_every_contract_chunk_and_no_notes(self):
        case = BY_ID["C10-2026Q2"]
        seen = []
        answers = [json.dumps({"items": case["expected_items"]}), json.dumps(case["expected_spec"])]
        def chat(system, user):
            seen.append(user)
            return answers.pop(0)
        out = run(case, "full", chat=chat)
        spec_prompt = seen[1]
        self.assertIn("dodatek_1.md", spec_prompt)
        self.assertIn("smlouva.md", spec_prompt)
        self.assertNotIn("poznamky", spec_prompt)
        retrieve = [s for s in out["steps"] if s["step"] == "retrieve"][0]
        self.assertGreater(len(retrieve["chunks"]), 5)

    def test_does_not_call_the_search(self):
        def boom(company, period):
            raise AssertionError("search must not run in full mode")
        out = run(BY_ID["C01-2026Q1"], "full", retrieve_fn=boom)
        self.assertEqual(out["status"], BY_ID["C01-2026Q1"]["expected_status"])

    def test_perfect_model_gets_the_expected_status_everywhere(self):
        wrong = [c["case_id"] for c in CASES if run(c, "full")["status"] != c["expected_status"]]
        self.assertEqual(wrong, [])


class NoContextMode(unittest.TestCase):
    def test_prompt_has_no_excerpts_and_model_refusal_is_human_review(self):
        case = BY_ID["C01-2026Q1"]
        seen = []
        answers = [json.dumps({"items": case["expected_items"]}), json.dumps({"error": "no contract text"})]
        def chat(system, user):
            seen.append(user)
            return answers.pop(0)
        out = run(case, "no_context", chat=chat)
        self.assertIn("No relevant excerpts found.", seen[1])
        self.assertEqual(out["status"], "human_review")
        self.assertTrue(out["reasons"][0].startswith("spec_refused"))

    def test_invented_spec_is_stopped_by_the_verifier(self):
        case = BY_ID["C01-2026Q1"]
        invented = json.loads(json.dumps(case["expected_spec"]))
        invented["covenants"][0]["limit"] = 99.0   # looks plausible, but cites text that does not say so
        invented["covenants"][0]["citation"] = {"document": "smlouva.md", "article": "6", "page": 3}
        out = run(case, "no_context", chat=items_chat(case, invented))
        self.assertEqual(out["status"], "human_review")


class RagModeUnchanged(unittest.TestCase):
    def test_empty_search_still_means_human_review(self):
        out = run(BY_ID["C01-2026Q1"], "rag", retrieve_fn=lambda c, p: [])
        self.assertEqual(out["reasons"], ["no_relevant_contract_text"])


if __name__ == "__main__":
    unittest.main()
