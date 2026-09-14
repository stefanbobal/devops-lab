import html
import json

from bs4 import BeautifulSoup


def strip_html(value):
    soup = BeautifulSoup(
        value or "",
        "html.parser"
    )

    return html.unescape(
        soup.get_text(
            "\n",
            strip=True
        )
    )


def normalize_component(component):
    component_type = (
        component.get(
            "componentType",
            "UNKNOWN"
        )
        .upper()
    )

    raw = component.get(
        "componentJSON"
    )

    if isinstance(raw, str):
        payload = json.loads(raw)
    else:
        payload = raw or {}

    if component_type == "TEXT":
        html_text = (
            payload.get("data", {})
            .get("htmlText", "")
        )

        return {
            "type": "TEXT",
            "text": strip_html(
                html_text
            )
        }

    if component_type == "TABLE":
        return {
            "type": "TABLE",
            "header":
                payload.get(
                    "headerText",
                    ""
                ),
            "rows":
                payload.get(
                    "DATA",
                    []
                ),
            "columns":
                payload.get(
                    "columns",
                    []
                ),
        }

    return {
        "type": component_type,
        "raw": payload
    }


def normalize_section_tree(payload):
    root = payload.get(
        "d",
        payload
    )

    sections = (
        root
        .get(
            "SelfOrChildrenRecursive",
            {}
        )
        .get(
            "results",
            []
        )
    )

    if not sections:
        sections = [root]

    result = []

    for section in sections:
        components = (
            section
            .get(
                "Components",
                {}
            )
            .get(
                "results",
                []
            )
        )

        result.append({
            "section_guid":
                section.get(
                    "section"
                ),
            "name":
                section.get(
                    "name"
                ),
            "rating":
                section.get(
                    "rating",
                    {}
                ),
            "components": [
                normalize_component(c)
                for c
                in components
            ]
        })

    return result


def category_for_section(name):
    name = (name or "").lower()

    categories = (
        ("security", "security"),
        ("performance", "performance"),
        ("sql", "sql"),
        ("statement", "sql"),
        ("hana", "hana"),
        ("database", "database"),
        ("capacity", "capacity"),
        ("availability", "availability"),
        ("maintenance", "maintenance"),
    )

    for keyword, category in categories:
        if keyword in name:
            return category

    return "other"


def normalize_findings(
    system,
    session_date,
    source_document,
    section_name,
    toc_rating_key,
    sections,
):
    findings = []

    for section in sections:
        rating = section.get("rating") or {}
        components = section.get("components") or []
        summary = "\n".join(
            component.get("text", "")
            for component in components
            if component.get("type") == "TEXT"
            and component.get("text")
        )
        table_data = [
            {
                "header": component.get("header", ""),
                "columns": component.get("columns", []),
                "rows": component.get("rows", []),
            }
            for component in components
            if component.get("type") == "TABLE"
        ]

        findings.append({
            "system": system,
            "session_date": (
                session_date.isoformat()
                if session_date
                else None
            ),
            "section_name": (
                section.get("name")
                or section_name
            ),
            "rating": rating.get("Text"),
            "rating_key": (
                rating.get("RatingKey")
                or toc_rating_key
            ),
            "category": category_for_section(
                section.get("name")
                or section_name
            ),
            "summary": summary,
            "table_data": table_data,
            "source_document": source_document,
        })

    return findings
