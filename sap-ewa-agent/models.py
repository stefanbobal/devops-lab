from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class EWASession:
    session_number: str
    document_key: str
    sid: str
    session_date: datetime | None
    rating_key: int | None = None
    rating_text: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class TOCItem:
    document_key: str
    chapter_guid: str | None
    subchapter_guid: str | None
    chapter_name: str | None
    subchapter_name: str | None
    chapter_rating_key: int | None
    subchapter_rating_key: int | None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def section_guid(self):
        return self.subchapter_guid or self.chapter_guid

    @property
    def title(self):
        return self.subchapter_name or self.chapter_name or ""
