import asyncio
import os

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
from normalizer import (
    normalize_findings,
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

EMPTY_SECTION_GUID = "00000000-0000-0000-0000-000000000000"


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


def finding_level(finding):
    rating = (finding.get("rating") or "").lower()
    rating_key = finding.get("rating_key") or 0

    if "critical" in rating or "alarm" in rating or rating_key >= 5:
        return "CRITICAL"

    if "warning" in rating or rating_key >= 4:
        return "WARNING"

    return None


def configured_prod_sids():
    return {
        sid.strip().upper()
        for sid in os.getenv(
            "EWA_PROD_SIDS",
            "",
        ).split(",")
        if sid.strip()
    }


def section_limit(environment_name, default):
    value = os.getenv(
        environment_name,
        str(default),
    )

    try:
        return max(1, int(value))
    except ValueError:
        return default


def max_warning_sections():
    return section_limit(
        "EWA_MAX_WARNING_SECTIONS",
        10,
    )


def max_other_sections():
    return section_limit(
        "EWA_MAX_OTHER_SECTIONS",
        10,
    )


def latest_sessions_by_sid(sessions):
    latest = {}

    for ewa in sessions:
        current = latest.get(ewa.sid)

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
            latest[ewa.sid] = ewa

    return latest


def select_section_details(
    toc,
    warning_limit,
    other_limit,
):
    candidates = [
        item
        for item in toc
        if (
            item.section_guid
            and item.section_guid != EMPTY_SECTION_GUID
            and interesting(item)
        )
    ]

    ordered = sorted(
        candidates,
        key=lambda item: (
            max(
                item.chapter_rating_key or 0,
                item.subchapter_rating_key or 0,
            ),
            item.title.lower(),
        ),
        reverse=True,
    )

    critical = []
    warnings = []
    other = []

    for item in ordered:
        rating_key = max(
            item.chapter_rating_key or 0,
            item.subchapter_rating_key or 0,
        )

        if rating_key >= 5:
            critical.append(item)
        elif rating_key >= 4:
            warnings.append(item)
        else:
            other.append(item)

    return (
        critical
        + warnings[:warning_limit]
        + other[:other_limit]
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

        prod_sids = configured_prod_sids()

        if not prod_sids:
            print(
                "EWA_PROD_SIDS is empty; "
                "no systems will be processed."
            )
            return

        sessions = [
            ewa
            for ewa in sessions
            if ewa.sid.upper() in prod_sids
        ]

        print(
            f"Found {len(sessions)} PROD EWA sessions."
        )

        latest = latest_sessions_by_sid(sessions)
        warning_limit = max_warning_sections()
        other_limit = max_other_sections()

        for sid, ewa in sorted(
            latest.items()
        ):
            print(
                f"\nSystem: {sid} | "
                f"Rating: {ewa.rating_text}"
            )

            toc = (
                await collector.get_toc(
                    ewa.document_key
                )
            )

            selected = select_section_details(
                toc,
                warning_limit,
                other_limit,
            )

            print(
                f"TOC: {len(toc)} | "
                f"Detail sections: {len(selected)} "
                f"(all critical, max {warning_limit} warnings, "
                f"max {other_limit} other)"
            )

            findings = []
            for item in selected:
                sections = (
                    await collector
                    .get_section_tree(
                        ewa.document_key,
                        item.section_guid
                    )
                )

                findings.extend(
                    normalize_findings(
                        system=sid,
                        session_date=ewa.session_date,
                        source_document=ewa.document_key,
                        section_name=item.title,
                        toc_rating_key=(
                            item.subchapter_rating_key
                            or item.chapter_rating_key
                        ),
                        sections=sections,
                    )
                )

            alerts = [
                finding
                for finding in findings
                if finding_level(finding)
            ]

            if alerts:
                print("Findings:")
                for finding in alerts:
                    print(
                        f"  [{finding_level(finding)}] "
                        f"{finding['section_name']} "
                        f"({finding['category']})"
                    )
            else:
                print("Findings: none")

    finally:
        await session.close()


if __name__ == "__main__":
    asyncio.run(main())
