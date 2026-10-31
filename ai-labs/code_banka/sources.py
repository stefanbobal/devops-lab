"""Verify that every citation in a contract specification is backed by the cited document.

The LLM proposes the specification; this module checks it against the actual documents
before covenants.evaluate may use it. Any unverified source sends the case to a human.

documents: {"smlouva.md": "...", "waiver_2026Q2.md": "...", ...} for one client.
Documents mark pages with "[strana N]" and articles with "## Článek N – ...".
"""
import re
from datetime import date

from covenants import evaluate, validate_spec, PERIOD_RE
from contract_rules import definitions, contract_limits, amendment
from decimal import Decimal

PAGE_RE = re.compile(r"^\[strana (\d+)\]\s*$", re.MULTILINE)
NOTES_PREFIX = "poznamky_"    # analyst notes are context, never evidence of a waiver or limit


def quarter_end(period):
    if not isinstance(period, str) or not PERIOD_RE.fullmatch(period):
        raise ValueError("invalid period")
    year, quarter = int(period[:4]), int(period[-1])
    return {1: date(year, 3, 31), 2: date(year, 6, 30), 3: date(year, 9, 30), 4: date(year, 12, 31)}[quarter]


def cz_date(day):
    return f"{day.day}. {day.month}. {day.year}"


def cz_number(value):
    return f"{value:.2f}".replace(".", ",")


def pages(text):
    """Return {page_number: page_text}."""
    marks = list(PAGE_RE.finditer(text))
    return {int(m.group(1)): text[m.end():(marks[i + 1].start() if i + 1 < len(marks) else len(text))]
            for i, m in enumerate(marks)}


def page_text(documents, citation):
    """Text of the cited page (and article, if given), or an error string."""
    if not isinstance(citation, dict):
        return None, "citation missing"
    name, page, article = citation.get("document"), citation.get("page"), citation.get("article")
    if name not in documents:
        return None, f"document {name!r} not found"
    if name.startswith(NOTES_PREFIX):
        return None, f"{name} is analyst notes, not a contractual source"
    content = pages(documents[name]).get(page)
    if content is None:
        return None, f"{name}: page {page!r} not found"
    if article is not None:
        heading = re.search(rf"^## Článek {re.escape(str(article))} –.*$", content, re.MULTILINE)
        if not heading:
            return None, f"{name}: article {article} not on page {page}"
        following = re.search(r"^## Článek ", content[heading.end():], re.MULTILINE)
        content = content[heading.start():heading.end() + following.start() if following else len(content)]
    return content, None


def resolved_limits(documents, period):
    """Resolve the supported contract plus supplied amendments, never an LLM-selected date."""
    test_day = quarter_end(period)
    contract = documents.get("smlouva.md", "")
    articles = []
    for page, content in pages(contract).items():
        for match in re.finditer(r"^## Článek (\d+) – Finanční ukazatele\s*$", content, re.MULTILINE):
            cite = {"document": "smlouva.md", "article": match[1], "page": page}
            text, error = page_text(documents, cite)
            if error:
                raise ValueError(error)
            articles.append((cite, contract_limits(text, test_day)))
    if len(articles) != 1:
        raise ValueError("expected exactly one supported covenant article")
    cite, rules = articles[0]
    resolved = {ratio: (limit, cite) for ratio, (limit, _) in rules.items()}
    amendments = [name for name in documents if name.startswith("dodatek")]
    # Multiple amendments need explicit precedence rules; never guess their order.
    if len(amendments) > 1:
        raise ValueError("multiple amendments require human review")
    for name in amendments:
        amended_cite = {"document": name, "article": "1", "page": 1}
        text, error = page_text(documents, amended_cite)
        if error:
            raise ValueError(error)
        article, subarticle, start, old, new = amendment(text)
        base = rules.get("debt_to_ebitda")
        if article != cite["article"] or base is None or subarticle != base[1] or old != base[0]:
            raise ValueError("amendment conflicts with the cited base limit")
        if test_day >= start:
            resolved["debt_to_ebitda"] = (new, amended_cite)
    return resolved


def verify_sources(spec, documents, period=None):
    """Return a list of problems; empty means every citation is grounded."""
    problems = []
    for part in ("ebitda", "debt"):
        text, error = page_text(documents, (spec.get(part) or {}).get("citation"))
        if error:
            problems.append(f"{part}: {error}")
        else:
            try:
                expected = definitions(text, part)
                for key, value in expected.items():
                    actual = spec[part].get(key, [] if isinstance(value, list) else None)
                    matches = sorted(actual) == sorted(value) if isinstance(value, list) else actual == value
                    if not matches:
                        problems.append(f"{part}.{key}: does not match the cited definition")
            except ValueError as exc:
                problems.append(str(exc))
    try:
        limits = resolved_limits(documents, period)
    except ValueError as exc:
        problems.append(f"limit: {exc}")
        limits = {}
    proposed_ratios = [c.get("ratio") for c in spec.get("covenants") or []]
    if set(proposed_ratios) != set(limits) or len(proposed_ratios) != len(set(proposed_ratios)):
        problems.append("limit: specification must include every contractual covenant exactly once")
    for covenant in spec.get("covenants") or []:
        text, error = page_text(documents, covenant.get("citation"))
        if error:
            problems.append(f"covenant {covenant.get('id')}: {error}")
        elif covenant.get("ratio") in limits:
            limit, cite = limits[covenant["ratio"]]
            if Decimal(str(covenant.get("limit"))) != limit or covenant.get("citation") != cite:
                problems.append(f"covenant {covenant.get('id')}: limit or citation does not match "
                                f"the effective rule for {period}")
    for waiver in spec.get("waivers") or []:
        text, error = page_text(documents, waiver.get("citation"))
        label = f"waiver {waiver.get('covenant')}/{waiver.get('period')}"
        if error:
            problems.append(f"{label}: {error}")
            continue
        try:
            day = cz_date(quarter_end(waiver["period"]))
        except (KeyError, TypeError, ValueError):
            problems.append(f"{label}: invalid period")
            continue
        if not re.search(r"\bprominuje\b", text):   # "neprominuje" in the contract does not count
            problems.append(f"{label}: cited text does not grant a waiver")
        if day not in text:
            problems.append(f"{label}: cited text does not name test date {day}")
    return problems


def evaluate_with_sources(items, spec, period, documents):
    """covenants.evaluate, but only after every citation has been verified."""
    try:
        validate_spec(spec)
        problems = verify_sources(spec, documents, period)
    except (AttributeError, TypeError, KeyError, ValueError) as exc:
        problems = [f"malformed spec: {exc}"]
    if problems:
        return {"status": "human_review", "reasons": ["unverified_source: " + p for p in problems],
                "covenants": []}
    return evaluate(items, spec, period)
