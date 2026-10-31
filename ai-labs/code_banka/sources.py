"""Verify that every citation in a contract specification is backed by the cited document.

The LLM proposes the specification; this module checks it against the actual documents
before covenants.evaluate may use it. Any unverified source sends the case to a human.

documents: {"smlouva.md": "...", "waiver_2026Q2.md": "...", ...} for one client.
Documents mark pages with "[strana N]" and articles with "## Článek N – ...".
"""
import re
from datetime import date

from covenants import evaluate

PAGE_RE = re.compile(r"^\[strana (\d+)\]\s*$", re.MULTILINE)
NOTES_PREFIX = "poznamky_"    # analyst notes are context, never evidence of a waiver or limit


def quarter_end(period):
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


def verify_sources(spec, documents):
    """Return a list of problems; empty means every citation is grounded."""
    problems = []
    for part in ("ebitda", "debt"):
        _, error = page_text(documents, (spec.get(part) or {}).get("citation"))
        if error:
            problems.append(f"{part}: {error}")
    for covenant in spec.get("covenants") or []:
        text, error = page_text(documents, covenant.get("citation"))
        if error:
            problems.append(f"covenant {covenant.get('id')}: {error}")
        elif isinstance(covenant.get("limit"), (int, float)) and cz_number(covenant["limit"]) not in text:
            problems.append(f"covenant {covenant.get('id')}: limit {cz_number(covenant['limit'])} "
                            "not stated in the cited source")
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
        problems = verify_sources(spec, documents)
    except (AttributeError, TypeError) as exc:
        problems = [f"malformed spec: {exc}"]
    if problems:
        return {"status": "human_review", "reasons": ["unverified_source: " + p for p in problems],
                "covenants": []}
    return evaluate(items, spec, period)
