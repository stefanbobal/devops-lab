import re
from datetime import date, datetime

from parser import (
    category_for_section,
)


SEVERITY_LEVELS = (
    ("critical", "CRITICAL"),
    ("alarm", "CRITICAL"),
    ("negative", "CRITICAL"),
    ("error", "CRITICAL"),
    ("warning", "WARNING"),
    ("positive", "OK"),
    ("ok", "OK"),
)


def finding_severity(rating, rating_key):
    text = str((rating or {}).get("Text") or "").lower()
    rating_key = rating.get("RatingKey") or rating_key or 0

    for marker, severity in SEVERITY_LEVELS:
        if marker in text:
            return severity

    if rating_key >= 5:
        return "CRITICAL"
    if rating_key >= 4:
        return "WARNING"
    if rating_key == 3:
        return "OK"

    return "UNKNOWN"


def _field_number(value):
    match = re.fullmatch(r"FIELD(\d+)", str(value or ""))
    return int(match.group(1)) if match else None


def _column_names(columns):
    names = {}

    for index, column in enumerate(columns or [], start=1):
        if isinstance(column, dict):
            name = column.get("params") or column.get("name")
        else:
            name = column

        if name:
            names[index] = str(name)

    return names


def _normalise_value(value):
    if not isinstance(value, str):
        return value

    value = value.strip()
    if not value:
        return None

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T.*", value):
        return value.split("T", 1)[0]

    return value


def normalize_table(table):
    columns = _column_names(table.get("columns"))
    records = []

    for row in table.get("rows") or []:
        if isinstance(row, dict):
            record = {}
            for key, value in row.items():
                number = _field_number(key)
                field_name = columns.get(number, key) if number else key
                record[field_name] = _normalise_value(value)
            records.append(record)
        elif isinstance(row, (list, tuple)):
            records.append({
                columns.get(index, f"FIELD{index}"):
                    _normalise_value(value)
                for index, value in enumerate(row, start=1)
            })
        else:
            records.append({"value": _normalise_value(row)})

    return {
        "header": table.get("header", ""),
        "columns": list(columns.values()),
        "records": records,
    }


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
        name = section.get("name") or section_name
        components = section.get("components") or []
        tables = [
            normalize_table(component)
            for component in components
            if component.get("type") == "TABLE"
        ]
        summary = "\n".join(
            component.get("text", "")
            for component in components
            if component.get("type") == "TEXT"
            and component.get("text")
        )
        rating_key = rating.get("RatingKey") or toc_rating_key

        findings.append({
            "system": system,
            "session_date": (
                session_date.isoformat()
                if isinstance(session_date, (date, datetime))
                else session_date
            ),
            "section_name": name,
            "rating": rating.get("Text"),
            "rating_key": rating_key,
            "severity": finding_severity(rating, rating_key),
            "category": category_for_section(name),
            "summary": summary,
            "table_data": tables,
            "records": [
                record
                for table in tables
                for record in table["records"]
            ],
            "source_document": source_document,
        })

    return findings
