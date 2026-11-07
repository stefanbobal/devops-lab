import json
import unittest
from pathlib import Path

import load_documents as ld


class ChunkingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chunks = ld.load_chunks()
        cls.cases = []   # cases of every set that exists
        for root in ld.DATA_DIRS.values():
            if (root / "expected.json").is_file():
                cls.cases += json.loads((root / "expected.json").read_text("utf-8"))

    def test_statements_are_not_loaded(self):
        self.assertFalse([c for c in self.chunks if c["document"].startswith("vykaz")])

    def test_contract_articles_are_numbered_without_gaps(self):
        for company in {c["company_id"] for c in self.chunks}:
            articles = [c["article"] for c in self.chunks
                        if c["company_id"] == company and c["doc_type"] == "contract"]
            articles = list(dict.fromkeys(articles))   # the definitions article is split into several chunks
            self.assertEqual(articles, [str(i) for i in range(1, len(articles) + 1)], company)
            self.assertGreaterEqual(len(articles), 10, company)

    def test_every_cited_article_is_a_chunk_on_the_cited_page(self):
        index = {(c["company_id"], c["document"], c["article"], c["page"]) for c in self.chunks}
        for case in self.cases:
            spec = case["expected_spec"]
            cites = [spec["ebitda"]["citation"], spec["debt"]["citation"]]
            cites += [cov["citation"] for cov in spec["covenants"]]
            for cite in cites:
                key = (case["company_id"], cite["document"], cite["article"], cite["page"])
                self.assertIn(key, index, case["case_id"])

    def test_definitions_are_split_per_clause_and_only_those(self):
        for company in {c["company_id"] for c in self.chunks}:
            mine = [c for c in self.chunks if c["company_id"] == company and c["doc_type"] == "contract"]
            split = [c for c in mine if c["clause"]]
            self.assertTrue(all(c["article_title"] == "Definice a výklad" for c in split), company)
            self.assertTrue(all(c["text"].startswith(c["clause"] + " ") for c in split), company)
            self.assertEqual(sum("„EBITDA“" in c["text"] for c in split), 1, company)
            self.assertEqual(sum("„Čistý dluh“" in c["text"] or "„Dluh“ znamená" in c["text"] for c in split), 1, company)
            self.assertFalse([c for c in mine if c["article_title"] == "Finanční ukazatele" and c["clause"]], company)

    def test_switch_restores_one_chunk_per_article(self):
        text = (ld.DATA / "companies" / "C01" / "smlouva.md").read_text("utf-8")
        whole = ld.chunk_document("C01", "x", "smlouva.md", text, split_definitions=False)
        split = ld.chunk_document("C01", "x", "smlouva.md", text, split_definitions=True)
        self.assertEqual(len(whole), 10)
        self.assertGreater(len(split), 10)
        self.assertEqual([c["article"] for c in whole], [str(i) for i in range(1, 11)])

    def test_waiver_and_notes_are_single_chunks(self):
        for kind in ("waiver", "notes"):
            docs = [c for c in self.chunks if c["doc_type"] == kind]
            self.assertTrue(docs)
            self.assertTrue(all(c["article"] is None for c in docs))

    def test_embedding_text_carries_company_and_article(self):
        text = ld.embedding_text(next(c for c in self.chunks if c["article"] == "5"))
        self.assertIn("Firma:", text)
        self.assertIn("článek 5", text)


if __name__ == "__main__":
    unittest.main()
