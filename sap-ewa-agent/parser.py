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
