from datetime import datetime, timedelta, timezone

from models import (
    EWASession,
    TOCItem,
)

from parser import (
    normalize_section_tree,
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
            tz=timezone.utc,
        )

    except Exception:
        return None


class EWACollector:
    def __init__(self, client):
        self.client = client

    async def list_sessions(self):
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=10)

        start_str = start.strftime(
            "%Y-%m-%dT00:00:00"
        )

        end_str = now.strftime(
            "%Y-%m-%dT00:00:00"
        )

        path = (
            "SessionDocumentSet"
            "?$skip=0"
            "&$top=30"
            "&$orderby="
            "Rating/RatingKey%20desc,"
            "SessionDate%20desc,"
            "SystemIdentifier%20asc"
            "&$filter="
            f"(SessionDate%20ge%20datetime%27{start_str}%27"
            "%20and%20"
            f"SessionDate%20le%20datetime%27{end_str}%27)"
            "%20and%20"
            "PackageId%20eq%20%27EW_ALERT%27"
            "&$expand=SystemFavorite%2cCustomers"
            "&$inlinecount=allpages"
        )

        print("Fetching EWA sessions...")

        payload = await self.client.get_json(
            path
        )

        rows = (
            payload
            .get("d", {})
            .get("results", [])
        )

        print(
            "EWA sessions returned:",
            len(rows),
        )

        result = []

        for row in rows:
            rating = (
                row.get("Rating")
                or {}
            )

            system = (
                row.get("system")
                or row.get("System")
                or {}
            )

            sid = (
                system.get("systemId")
                or system.get("SystemId")
                or row.get("SystemIdentifier")
                or ""
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

                    sid=sid,

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

                    raw=row,
                )
            )

        return result

    async def get_toc(
        self,
        document_key,
    ):
        path = (
            f"DocumentSet('{document_key}')/"
            "TOC"
            "?$skip=0"
            "&$top=100"
            "&$expand=Favorite"
        )

        print(
            "Fetching TOC for document:",
            document_key,
        )

        payload = await self.client.get_json(
            path
        )

        rows = (
            payload
            .get("d", {})
            .get("results", [])
        )

        print(
            "TOC entries returned:",
            len(rows),
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

                    raw=row,
                )
            )

        return result

    async def get_section_tree(
        self,
        document_key,
        section_guid,
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

        print(
            "Fetching section:",
            section_guid,
        )

        payload = await self.client.get_json(
            path
        )

        return normalize_section_tree(
            payload
        )