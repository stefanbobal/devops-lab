"""Hand-calculated examples for covenants.py (independent of generate_data.py)."""
import copy
import unittest

from covenants import evaluate

WAIVER_CITE = {"document": "waiver_2026Q2.md", "article": None, "page": 1}
ITEMS = dict(revenue=1000, ebit=60, depreciation=40, restructuring=20, asset_sale_gain=10,
             interest_expense=25, bank_loans=380, bonds=50, cash=30, reported_ebitda=120)
SPEC = {
    "ebitda": {"add": [], "subtract": []},
    "debt": {"include": ["bank_loans", "bonds"], "deduct_cash": True},
    "covenants": [{"id": "leverage", "ratio": "debt_to_ebitda", "limit": 4.5}],
    "waivers": [],
}


def spec(**changes):
    s = copy.deepcopy(SPEC)
    for path, value in changes.items():
        target = s
        *parents, last = path.split("__")
        for p in parents:
            target = target[p]
        target[last] = value
    return s


class CovenantTests(unittest.TestCase):
    def test_standard_definition(self):
        # EBITDA 60+40 = 100; net debt 380+50-30 = 400; 4.00 <= 4.50
        r = evaluate(ITEMS, SPEC, "2026Q2")
        self.assertEqual(r["status"], "no_breach")
        self.assertEqual(r["covenants"][0]["value"], "4.00")

    def test_limit_breach(self):
        # 4.00 > 3.50
        r = evaluate(ITEMS, spec(covenants=[{"id": "leverage", "ratio": "debt_to_ebitda", "limit": 3.5}]), "2026Q2")
        self.assertEqual(r["status"], "breach")

    def test_restructuring_add_back_changes_result(self):
        # EBITDA 100+20 = 120; 400/120 = 3.33 <= 3.50
        s = spec(ebitda__add=["restructuring"],
                 covenants=[{"id": "leverage", "ratio": "debt_to_ebitda", "limit": 3.5}])
        r = evaluate(ITEMS, s, "2026Q2")
        self.assertEqual((r["status"], r["covenants"][0]["value"]), ("no_breach", "3.33"))

    def test_asset_gain_subtraction_creates_breach(self):
        # EBITDA 100-10 = 90; 400/90 = 4.44 > 4.20
        s = spec(ebitda__subtract=["asset_sale_gain"],
                 covenants=[{"id": "leverage", "ratio": "debt_to_ebitda", "limit": 4.2}])
        r = evaluate(ITEMS, s, "2026Q2")
        self.assertEqual((r["status"], r["covenants"][0]["value"]), ("breach", "4.44"))

    def test_gross_debt(self):
        # gross debt 430/100 = 4.30 > 4.20
        s = spec(debt__deduct_cash=False,
                 covenants=[{"id": "leverage", "ratio": "debt_to_ebitda", "limit": 4.2}])
        self.assertEqual(evaluate(ITEMS, s, "2026Q2")["status"], "breach")

    def test_waiver_only_for_its_period(self):
        s = spec(covenants=[{"id": "leverage", "ratio": "debt_to_ebitda", "limit": 3.5}],
                 waivers=[{"covenant": "leverage", "period": "2026Q2", "citation": WAIVER_CITE}])
        self.assertEqual(evaluate(ITEMS, s, "2026Q2")["status"], "no_breach")
        self.assertEqual(evaluate(ITEMS, s, "2026Q3")["status"], "breach")

    def test_interest_cover_minimum(self):
        # 100/25 = 4.00 < 4.50 -> breach of a minimum covenant
        s = spec(covenants=[{"id": "leverage", "ratio": "debt_to_ebitda", "limit": 5.0},
                            {"id": "icr", "ratio": "interest_cover", "limit": 4.5}])
        r = evaluate(ITEMS, s, "2026Q2")
        self.assertEqual(r["status"], "breach")
        self.assertEqual([c["breached"] for c in r["covenants"]], [False, True])

    def test_near_limit_goes_to_human(self):
        # 4.00 vs 4.05: within 2 %
        s = spec(covenants=[{"id": "leverage", "ratio": "debt_to_ebitda", "limit": 4.05}])
        self.assertEqual(evaluate(ITEMS, s, "2026Q2")["status"], "human_review")
        # exactly at the limit is not a breach, but still near -> human review
        s = spec(covenants=[{"id": "leverage", "ratio": "debt_to_ebitda", "limit": 4.0}])
        r = evaluate(ITEMS, s, "2026Q2")
        self.assertEqual((r["status"], r["covenants"][0]["breached"]), ("human_review", False))

    def test_missing_item_goes_to_human(self):
        items = dict(ITEMS, depreciation=None)
        r = evaluate(items, SPEC, "2026Q2")
        self.assertEqual(r["status"], "human_review")
        self.assertIn("depreciation", r["reasons"][0])

    def test_unused_missing_item_is_fine(self):
        items = dict(ITEMS, asset_sale_gain=None, reported_ebitda=None)
        self.assertEqual(evaluate(items, SPEC, "2026Q2")["status"], "no_breach")

    def test_invalid_spec_goes_to_human(self):
        for bad in (spec(ebitda__add=["reported_ebitda"]),
                    spec(debt__include=[]),
                    spec(covenants=[{"id": "leverage", "ratio": "debt_to_ebitda", "limit": -1}]),
                    spec(covenants=[{"id": "x", "ratio": "debt_to_ebitda", "limit": 4},
                                    {"id": "x", "ratio": "debt_to_ebitda", "limit": 5}]),
                    spec(waivers=[{"covenant": "other", "period": "2026Q2", "citation": WAIVER_CITE}]),
                    spec(waivers=[{"covenant": "leverage", "period": "2026Q2"}]),          # no source
                    spec(waivers=[{"covenant": "leverage", "period": "Q2", "citation": WAIVER_CITE}]),
                    spec(ebitda__add=["restructuring", "restructuring"]),
                    spec(ebitda__subtract=["asset_sale_gain", "asset_sale_gain"]),
                    spec(debt__include=["bank_loans", "bank_loans"]),
                    spec(covenants=[{"id": "leverage", "ratio": "debt_to_ebitda", "limit": float("nan")}]),
                    spec(covenants=[{"id": "leverage", "ratio": "debt_to_ebitda", "limit": float("inf")}]),
                    spec(covenants=[{"id": "leverage", "ratio": "debt_to_ebitda", "limit": True}]),
                    spec(covenants=["not a dict"]),
                    spec(ebitda="not a dict")):
            r = evaluate(ITEMS, bad, "2026Q2")
            self.assertEqual(r["status"], "human_review")
            self.assertTrue(r["reasons"][0].startswith("invalid_spec"))


    def test_duplicate_add_back_cannot_hide_breach(self):
        # Single add-back: 400/120 = 3.33 > 3.00; duplicate: 400/140 = 2.86.
        s = spec(ebitda__add=["restructuring", "restructuring"],
                 covenants=[{"id": "leverage", "ratio": "debt_to_ebitda", "limit": 3.0}])
        self.assertEqual(evaluate(ITEMS, s, "2026Q2")["status"], "human_review")

    def test_invalid_numbers_go_to_human(self):
        s = spec(covenants=[{"id": "leverage", "ratio": "debt_to_ebitda", "limit": 3.5}])   # real breach
        for name, value in (("depreciation", float("nan")), ("depreciation", float("inf")),
                            ("bank_loans", -380), ("cash", -30), ("bonds", True), ("bank_loans", "380"),
                            ("depreciation", "1 234")):
            r = evaluate(dict(ITEMS, **{name: value}), s, "2026Q2")
            self.assertEqual(r["status"], "human_review", (name, value))
            self.assertTrue(r["reasons"][0].startswith("invalid_item"), (name, value))

    def test_operating_loss_is_allowed(self):
        # EBIT may be negative: -10 + 40 = 30; 400/30 = 13.33 > 4.5 -> breach, not invalid
        self.assertEqual(evaluate(dict(ITEMS, ebit=-10), SPEC, "2026Q2")["status"], "breach")

    def test_missing_sections_and_malformed_items_go_to_human(self):
        for part in ("ebitda", "debt", "covenants"):
            for value in (None, "wrong type"):
                bad = copy.deepcopy(SPEC)
                bad[part] = value
                self.assertEqual(evaluate(ITEMS, bad, "2026Q2")["status"], "human_review")
            bad = copy.deepcopy(SPEC)
            del bad[part]
            self.assertEqual(evaluate(ITEMS, bad, "2026Q2")["status"], "human_review")
        for items in (None, [], "wrong type"):
            self.assertEqual(evaluate(items, SPEC, "2026Q2")["status"], "human_review")

    def test_unused_interest_is_not_converted(self):
        for value in ("bad", float("nan"), True):
            items = dict(ITEMS, interest_expense=value)
            self.assertEqual(evaluate(items, SPEC, "2026Q2")["status"], "no_breach")
            with_interest = spec(covenants=[{"id": "icr", "ratio": "interest_cover", "limit": 3}])
            self.assertEqual(evaluate(items, with_interest, "2026Q2")["status"], "human_review")

    def test_invalid_review_band_and_period_go_to_human(self):
        for band in (True, "0.02", float("nan"), float("inf"), -0.1, 1):
            self.assertEqual(evaluate(ITEMS, SPEC, "2026Q2", review_band=band)["status"], "human_review")
        for period in (None, "2026Q9", "2026Q2\n"):
            self.assertEqual(evaluate(ITEMS, SPEC, period)["status"], "human_review")


if __name__ == "__main__":
    unittest.main()
