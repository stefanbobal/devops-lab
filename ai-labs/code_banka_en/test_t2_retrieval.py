import unittest

import t2_retrieval as t2


def row(kind, sims, is_gold=None):
    is_gold = is_gold or [False] * len(sims)
    gold = next((s for s, g in zip(sims, is_gold) if g), None)
    return dict(kind=kind, sims=sims, is_gold=is_gold, gold_sim=gold, rank=None)


class T2Tests(unittest.TestCase):
    def case(self, waivers):
        spec = {"ebitda": {"citation": {"document": "smlouva.md", "article": "2"}},
                "debt": {"citation": {"document": "smlouva.md", "article": "2"}},
                "covenants": [{"citation": {"document": "smlouva.md", "article": "5"}}],
                "waivers": waivers}
        return dict(period="2026Q2", expected_spec=spec)

    def test_negative_query_only_without_waiver(self):
        kinds = [k for k, _, _ in t2.queries(self.case([]))]
        self.assertEqual(kinds, ["ebitda", "debt", "limit", "no_waiver"])
        waiver = [{"citation": {"document": "waiver_2026Q2.md", "article": None}}]
        kinds = [k for k, _, _ in t2.queries(self.case(waiver))]
        self.assertEqual(kinds, ["ebitda", "debt", "limit", "waiver"])
        negative = dict((k, g) for k, _, g in t2.queries(self.case([])))["no_waiver"]
        self.assertEqual(negative, [])

    def test_sweep_separates_recall_and_false_accept(self):
        rows = [row("ebitda", [0.80, 0.50, 0.40], [True, False, False]),
                row("limit", [0.60, 0.55, 0.30], [True, False, False]),
                row("no_waiver", [0.58, 0.40, 0.30]),
                row("no_waiver", [0.45, 0.40, 0.30])]
        by = {s["threshold"]: s for s in t2.thresholds_sweep(rows)}
        self.assertEqual((by[0.55]["recall"], by[0.55]["false_accept"]), (1.0, 0.5))
        self.assertEqual((by[0.65]["recall"], by[0.65]["false_accept"]), (0.5, 0.0))
        self.assertEqual(by[0.30]["false_accept"], 1.0)

    def test_negative_rows_do_not_change_precision(self):
        base = [row("ebitda", [0.80, 0.50, 0.40], [True, False, False])]
        extra = base + [row("no_waiver", [0.9, 0.9, 0.9])]
        a = {s["threshold"]: s["precision"] for s in t2.thresholds_sweep(base)}
        b = {s["threshold"]: s["precision"] for s in t2.thresholds_sweep(extra)}
        self.assertEqual(a, b)

    def test_choose_threshold_is_highest_meeting_recall(self):
        sweep = [dict(threshold=0.5, recall=1.0), dict(threshold=0.6, recall=0.96),
                 dict(threshold=0.7, recall=0.6)]
        self.assertEqual(t2.choose_threshold(sweep)["threshold"], 0.6)
        self.assertIsNone(t2.choose_threshold([dict(threshold=0.5, recall=0.5)]))

    def test_test_set_needs_final_and_never_writes_thresholds(self):
        with self.assertRaises(SystemExit):
            t2.main(["--set", "test"])
        with self.assertRaises(SystemExit):
            t2.main(["--set", "test", "--final", "--write-thresholds"])


if __name__ == "__main__":
    unittest.main()
