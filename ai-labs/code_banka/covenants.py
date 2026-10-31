"""Deterministic covenant evaluation: the code, not the LLM, decides the status.

Inputs:
  items  - statement line items extracted from a quarterly statement (tis. Kč);
           a missing or unreadable item is None
  spec   - contract specification resolved for one test period (see SPEC_EXAMPLE)
  period - test period id, e.g. "2026Q2"

Output: computed values, per-covenant results and a final status:
  breach | no_breach | human_review
"""
import math
import re
from decimal import Decimal, ROUND_HALF_UP

ALLOWED_ITEMS = {
    "revenue": "Tržby",
    "ebit": "Provozní výsledek hospodaření (EBIT)",
    "depreciation": "Odpisy a amortizace",
    "restructuring": "Jednorázové náklady na restrukturalizaci",
    "asset_sale_gain": "Jednorázový zisk z prodeje dlouhodobého majetku",
    "interest_expense": "Nákladové úroky",
    "bank_loans": "Bankovní úvěry a zápůjčky",
    "bonds": "Vydané dluhopisy",
    "cash": "Peněžní prostředky a peněžní ekvivalenty",
    "reported_ebitda": "EBITDA vykázaná společností",   # informational only, never used
}
EBITDA_BASE = ("ebit", "depreciation")
EBITDA_ADJUSTMENTS = ("restructuring", "asset_sale_gain")
DEBT_ITEMS = ("bank_loans", "bonds")
RATIOS = {"debt_to_ebitda": "max", "interest_cover": "min"}
MAY_BE_NEGATIVE = {"ebit"}   # an operating loss is possible; every other required item must be >= 0
PERIOD_RE = re.compile(r"^\d{4}Q[1-4]$")

SPEC_EXAMPLE = {
    "ebitda": {"add": ["restructuring"], "subtract": [],
               "citation": {"document": "smlouva.md", "article": "2", "page": 1}},
    "debt": {"include": ["bank_loans", "bonds"], "deduct_cash": True,
             "citation": {"document": "smlouva.md", "article": "2", "page": 1}},
    "covenants": [{"id": "leverage", "ratio": "debt_to_ebitda", "limit": 4.0,
                   "citation": {"document": "smlouva.md", "article": "6", "page": 3}}],
    "waivers": [{"covenant": "leverage", "period": "2026Q2",
                 "citation": {"document": "waiver_2026Q2.md", "article": None, "page": 1}}],
}

REVIEW_BAND = Decimal("0.02")   # within 2 % of a limit -> human review
TWO_PLACES = Decimal("0.01")


class SpecError(ValueError):
    """The specification is structurally invalid; never guess a fix."""


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _duplicates(values):
    return sorted({v for v in values if values.count(v) > 1})


def validate_spec(spec):
    errors = []
    ebitda, debt = spec.get("ebitda") or {}, spec.get("debt") or {}
    for key in ("add", "subtract"):
        values = ebitda.get(key, [])
        if not isinstance(values, list):
            errors.append(f"ebitda.{key} must be a list")
            continue
        for item in values:
            if item not in EBITDA_ADJUSTMENTS:
                errors.append(f"ebitda.{key}: item {item!r} not allowed")
        if _duplicates(values):
            errors.append(f"ebitda.{key}: duplicate items {_duplicates(values)}")
    if set(ebitda.get("add", [])) & set(ebitda.get("subtract", [])):
        errors.append("ebitda: an item is both added and subtracted")
    include = debt.get("include", [])
    if not isinstance(include, list) or not include or any(i not in DEBT_ITEMS for i in include):
        errors.append("debt.include must be a nonempty subset of " + ", ".join(DEBT_ITEMS))
    elif _duplicates(include):
        errors.append(f"debt.include: duplicate items {_duplicates(include)}")
    if not isinstance(debt.get("deduct_cash"), bool):
        errors.append("debt.deduct_cash must be true or false")
    covenants = spec.get("covenants") or []
    if not covenants:
        errors.append("at least one covenant is required")
    ids = [c.get("id") for c in covenants]
    if len(set(ids)) != len(ids):
        errors.append("duplicate covenant id; conflicting articles must go to human review")
    for c in covenants:
        if c.get("ratio") not in RATIOS:
            errors.append(f"covenant {c.get('id')!r}: unknown ratio {c.get('ratio')!r}")
        limit = c.get("limit")
        if not _is_number(limit) or limit <= 0:
            errors.append(f"covenant {c.get('id')!r}: limit must be a finite positive number")
    waiver_keys = []
    for w in spec.get("waivers") or []:
        if w.get("covenant") not in ids:
            errors.append(f"waiver for unknown covenant {w.get('covenant')!r}")
        if not isinstance(w.get("period"), str) or not PERIOD_RE.match(w["period"]):
            errors.append(f"waiver period {w.get('period')!r} must look like 2026Q2")
        citation = w.get("citation")
        if not isinstance(citation, dict) or not citation.get("document"):
            errors.append(f"waiver for {w.get('covenant')!r} has no source citation")
        waiver_keys.append((w.get("covenant"), w.get("period")))
    if len(set(waiver_keys)) != len(waiver_keys):
        errors.append("duplicate waiver")
    if errors:
        raise SpecError("; ".join(errors))


def required_items(spec):
    needed = set(EBITDA_BASE) | set(spec["ebitda"].get("add", [])) | set(spec["ebitda"].get("subtract", []))
    needed |= set(spec["debt"]["include"])
    if spec["debt"]["deduct_cash"]:
        needed.add("cash")
    if any(c["ratio"] == "interest_cover" for c in spec["covenants"]):
        needed.add("interest_expense")
    return sorted(needed)


def _d(value):
    return Decimal(str(value))


def invalid_items(items, names):
    """Required items must be finite numbers; only EBIT may be negative. Strings are not parsed here."""
    bad = []
    for name in names:
        value = items.get(name)
        if not _is_number(value) or (value < 0 and name not in MAY_BE_NEGATIVE):
            bad.append(f"{name}={value!r}")
    return bad


def compute_values(items, spec):
    ebitda = sum(_d(items[i]) for i in EBITDA_BASE)
    ebitda += sum(_d(items[i]) for i in spec["ebitda"].get("add", []))
    ebitda -= sum(_d(items[i]) for i in spec["ebitda"].get("subtract", []))
    debt = sum(_d(items[i]) for i in spec["debt"]["include"])
    if spec["debt"]["deduct_cash"]:
        debt -= _d(items["cash"])
    values = {"ebitda": ebitda, "debt": debt}
    if items.get("interest_expense") is not None:
        values["interest_expense"] = _d(items["interest_expense"])
    return values


def evaluate(items, spec, period, review_band=REVIEW_BAND):
    """Return status breach / no_breach / human_review with reasons; deterministic."""
    try:
        validate_spec(spec)
    except (SpecError, AttributeError, TypeError, KeyError) as exc:   # malformed spec -> human, never a guess
        return {"status": "human_review", "reasons": ["invalid_spec: " + str(exc)], "covenants": []}
    needed = required_items(spec)
    missing = [i for i in needed if items.get(i) is None]
    if missing:
        return {"status": "human_review", "reasons": ["missing_item: " + ", ".join(missing)], "covenants": []}
    invalid = invalid_items(items, needed)
    if invalid:
        return {"status": "human_review", "reasons": ["invalid_item: " + ", ".join(invalid)], "covenants": []}
    values = compute_values(items, spec)
    if values["ebitda"] <= 0:
        return {"status": "human_review", "reasons": ["non_positive_ebitda"], "covenants": [],
                "values": {k: str(v) for k, v in values.items()}}
    waived = {w["covenant"] for w in spec.get("waivers") or [] if w.get("period") == period}
    results, reasons = [], []
    for c in spec["covenants"]:
        limit = _d(c["limit"])
        if c["ratio"] == "debt_to_ebitda":
            value = values["debt"] / values["ebitda"]
        else:
            if values.get("interest_expense", 0) <= 0:
                reasons.append(f"{c['id']}: non_positive_interest_expense")
                continue
            value = values["ebitda"] / values["interest_expense"]
        kind = RATIOS[c["ratio"]]
        breached = value > limit if kind == "max" else value < limit
        near = abs(value - limit) / limit <= review_band
        result = {"id": c["id"], "ratio": c["ratio"], "kind": kind, "limit": str(limit),
                  "value": str(value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)),
                  "breached": breached, "waived": breached and c["id"] in waived, "near_limit": near}
        results.append(result)
        if near:
            reasons.append(f"{c['id']}: within {review_band:.0%} of limit")
    unwaived = [r for r in results if r["breached"] and not r["waived"] and not r["near_limit"]]
    if unwaived:
        status = "breach"
    elif reasons:
        status = "human_review"
    else:
        status = "no_breach"
    return {"status": status, "reasons": reasons, "covenants": results,
            "values": {k: str(v) for k, v in values.items()}}
