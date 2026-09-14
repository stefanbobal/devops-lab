from dataclasses import dataclass
from datetime import datetime


@dataclass
class SecurityNote:
    system_sid: str
    system_number: str

    number: str
    version: int
    title: str
    component: str
    category: str

    priority: str
    cvss_score: float
    cvss_vector: str

    first_published_on: datetime | None
    released_on: datetime | None

    unread: bool
    patch_day: bool
    status_key: str

    raw: dict
