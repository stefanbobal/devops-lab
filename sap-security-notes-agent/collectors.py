from datetime import datetime, timezone

from models import SecurityNote


def parse_odata_date(value):
    if not value:
        return None

    try:
        millis = int(
            value.split("(")[1]
            .split(")")[0]
        )

        return datetime.fromtimestamp(
            millis / 1000,
            tz=timezone.utc
        )

    except Exception:
        return None


class SecurityNotesCollector:
    def __init__(self, client):
        self.client = client

    async def get_notes_for_system(
        self,
        sid: str,
        system_number: str,
        status: str = "ToBeReviewed",
        page_size: int = 100
    ):
        results = []
        skip = 0

        while True:
            filter_value = (
                f"System eq '{system_number}' "
                f"and StatusKey eq '{status}'"
            )

            payload = await self.client.get_json(
                "SAPNoteSet",
                {
                    "$skip": skip,
                    "$top": page_size,
                    "$filter": filter_value,
                    "$inlinecount": "allpages",
                }
            )

            data = payload.get("d", {})
            rows = data.get("results", [])

            for row in rows:
                results.append(
                    SecurityNote(
                        system_sid=sid,
                        system_number=system_number,

                        number=str(
                            row.get("Number", "")
                        ),
                        version=int(
                            row.get("Version") or 0
                        ),
                        title=row.get(
                            "Title", ""
                        ),
                        component=row.get(
                            "Component", ""
                        ),
                        category=row.get(
                            "Category", ""
                        ),
                        priority=row.get(
                            "Priority", ""
                        ),
                        cvss_score=float(
                            row.get("CVSSScore")
                            or 0
                        ),
                        cvss_vector=row.get(
                            "CVSSVector", ""
                        ),
                        first_published_on=
                            parse_odata_date(
                                row.get(
                                    "FirstPublishedOn"
                                )
                            ),
                        released_on=
                            parse_odata_date(
                                row.get(
                                    "ReleasedOn"
                                )
                            ),
                        unread=bool(
                            row.get("Unread")
                        ),
                        patch_day=bool(
                            row.get("PatchDay")
                        ),
                        status_key=row.get(
                            "StatusKey", ""
                        ),
                        raw=row
                    )
                )

            total = int(
                data.get("__count")
                or len(results)
            )

            skip += len(rows)

            if (
                not rows
                or skip >= total
            ):
                break

        return results
