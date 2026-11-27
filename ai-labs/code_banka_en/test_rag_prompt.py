import unittest

import rag_prompt

CHUNK = {"document": "smlouva.md", "doc_type": "contract", "article": "5", "clause": "5.1", "page": 3, "text": "Limit 3,75"}


class SpecPromptTests(unittest.TestCase):
    def test_chunks_carry_citation_metadata(self):
        text = rag_prompt.format_chunks([CHUNK])
        for part in ("smlouva.md", "article: 5 | clause: 5.1", "page: 3", "Limit 3,75"):
            self.assertIn(part, text)

    def test_empty_context_is_explicit(self):
        self.assertIn("No relevant", rag_prompt.format_chunks([]))

    def test_prompt_lists_allowed_values_and_period(self):
        system, user = rag_prompt.build_spec_prompts("2026Q2", "2026-06-30", [CHUNK])
        for part in ("debt_to_ebitda", "interest_cover", "restructuring", "bonds", "2026Q2", "2026-06-30"):
            self.assertIn(part, user)
        self.assertIn("Analyst notes", system)

    def test_prompt_explains_built_in_ebitda_base(self):
        _, user = rag_prompt.build_spec_prompts("2026Q2", "2026-06-30", [CHUNK])
        self.assertIn("NEVER list depreciation", user)

    def test_prompt_says_interest_definition_is_not_needed(self):
        _, user = rag_prompt.build_spec_prompts("2026Q2", "2026-06-30", [CHUNK])
        self.assertIn("never need a definition of interest expense", user)

    def test_incident_prompt_still_works(self):
        self.assertIn("No sufficiently", rag_prompt.format_context([]))


if __name__ == "__main__":
    unittest.main()
