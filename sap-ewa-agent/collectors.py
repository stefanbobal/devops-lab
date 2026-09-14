from datetime import datetime, timezone

from models import (
    EWASession,
    TOCItem
)
from parser import (
    normalize_section_tree
)


def parse_date(value):
    if not value:
        return None

    try:
        millis = int(
            value
            .split("(")[1]
            .split(")")[0]
        )

        return datetime.fromtimestamp(
            millis / 1000,
            tz=timezone.utc
        )
    except Exception:
        return None


class EWACollector:
    def __init__(self, client):
        self.client = client

    async def list_sessions(self):
        path = (
            "SessionDocumentSet"
            "?$top=200"
            "&$orderby=SessionDate%20desc"
            "&$filter="
            "PackageId%20eq%20%27EW_ALERT%27"
        )

        payload = await self.client.get_json(
            path
        )

        rows = (
            payload
            .get("d", {})
            .get("results", [])
        )

        result = []

        for row in rows:
            rating = (
                row.get("Rating")
                or {}
            )

            system = (
                row.get("system")
                or {}
            )

            result.append(
                EWASession(
                    session_number=
                        row.get(
                            "SessionNumber",
                            ""
                        ),
                    document_key=
                        row.get(
                            "DocumentKey",
                            ""
                        ),
                    sid=
                        system.get(
                            "systemId",
                            ""
                        ),
                    session_date=
                        parse_date(
                            row.get(
                                "SessionDate"
                            )
                        ),
                    rating_key=
                        rating.get(
                            "RatingKey"
                        ),
                    rating_text=
                        rating.get(
                            "Text"
                        ),
                    raw=row
                )
            )

        return result

    async def get_toc(
        self,
        document_key
    ):
        payload = await self.client.get_json(
            f"DocumentSet('{document_key}')/"
            "TOC"
            "?$skip=0"
            "&$top=500"
            "&$expand=Favorite"
        )

        rows = (
            payload
            .get("d", {})
            .get("results", [])
        )

        result = []

        for row in rows:
            chapter_rating = (
                row.get(
                    "ChapterRating"
                )
                or {}
            )

            sub_rating = (
                row.get(
                    "SubChapterRating"
                )
                or {}
            )

            result.append(
                TOCItem(
                    document_key=
                        document_key,
                    chapter_guid=
                        row.get(
                            "Chapter"
                        ),
                    subchapter_guid=
                        row.get(
                            "SubChapter"
                        ),
                    chapter_name=
                        row.get(
                            "ChapterName"
                        ),
                    subchapter_name=
                        row.get(
                            "SubChapterName"
                        ),
                    chapter_rating_key=
                        chapter_rating.get(
                            "RatingKey"
                        ),
                    subchapter_rating_key=
                        sub_rating.get(
                            "RatingKey"
                        ),
                    raw=row
                )
            )

        return result

    async def get_section_tree(
        self,
        document_key,
        section_guid
    ):
        path = (
            "SectionSet("
            f"documentId='{document_key}',"
            f"section=guid'{section_guid}'"
            ")/HeaderSection"
            "?$expand="
            "ParentSection,"
            "SelfOrChildrenRecursive/"
            "Components"
        )

        payload = await self.client.get_json(
            path
        )

        return normalize_section_tree(
            payload
        )
