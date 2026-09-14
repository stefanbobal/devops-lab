import asyncio
import json

from dotenv import load_dotenv

from auth import (
    login_to_sap_for_me
)
from collectors import (
    EWACollector
)
from odata_client import (
    SAPForMeODataClient
)


KEYWORDS = (
    "performance",
    "sql",
    "hana",
    "security",
    "maintenance",
    "capacity",
    "availability",
)


def interesting(item):
    ratings = [
        item.chapter_rating_key or 0,
        item.subchapter_rating_key or 0
    ]

    if max(ratings) >= 4:
        return True

    name = item.title.lower()

    return any(
        keyword in name
        for keyword in KEYWORDS
    )


async def main():
    load_dotenv()

    session = (
        await login_to_sap_for_me()
    )

    try:
        client = (
            SAPForMeODataClient(
                session.context
            )
        )

        collector = (
            EWACollector(
                client
            )
        )

        sessions = (
            await collector.list_sessions()
        )

        print(
            f"Found "
            f"{len(sessions)} "
            f"EWA sessions."
        )

        latest = {}

        for ewa in sessions:
            current = latest.get(
                ewa.sid
            )

            if (
                not current
                or (
                    ewa.session_date
                    and (
                        not current.session_date
                        or ewa.session_date
                        > current.session_date
                    )
                )
            ):
                latest[
                    ewa.sid
                ] = ewa

        for sid, ewa in sorted(
            latest.items()
        ):
            print(
                "\nSystem:",
                sid,
                "Rating:",
                ewa.rating_text
            )

            toc = (
                await collector.get_toc(
                    ewa.document_key
                )
            )

            selected = [
                item
                for item in toc
                if (
                    item.section_guid
                    and interesting(item)
                )
            ]

            print(
                "TOC:",
                len(toc),
                "Selected:",
                len(selected)
            )

            for item in selected[:5]:
                print(
                    "  Section:",
                    item.title
                )

                sections = (
                    await collector
                    .get_section_tree(
                        ewa.document_key,
                        item.section_guid
                    )
                )

                print(
                    json.dumps(
                        sections,
                        ensure_ascii=False
                    )[:4000]
                )

    finally:
        await session.close()


if __name__ == "__main__":
    asyncio.run(main())
