def risk_level(note):
    if note.priority == "HotNews":
        return "CRITICAL"

    if note.cvss_score >= 9.0:
        return "CRITICAL"

    if note.cvss_score >= 7.0:
        return "HIGH"

    if note.cvss_score >= 4.0:
        return "MEDIUM"

    return "LOW"


def should_alert(note):
    return (
        note.priority == "HotNews"
        or note.cvss_score >= 8.0
    )
