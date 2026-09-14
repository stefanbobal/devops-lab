import asyncio

from dotenv import load_dotenv

from auth import login_to_sap_for_me
from collectors import SecurityNotesCollector
from config import get_systems
from db import Database
from odata_client import SecurityNotesODataClient
from risk import risk_level, should_alert


async def main():
    load_dotenv()

    systems = get_systems()

    sap = await login_to_sap_for_me()

    try:
        client = SecurityNotesODataClient(
            sap.context
        )

        collector = SecurityNotesCollector(
            client
        )

        db = Database()

        if db.enabled():
            db.init_schema()

        print(
            f"Monitoring "
            f"{len(systems)} system(s)."
        )

        for sid, system_number in systems.items():

            print()
            print(
                f"=== {sid} ==="
            )

            notes = (
                await collector
                .get_notes_for_system(
                    sid,
                    system_number
                )
            )

            print(
                f"To Be Reviewed: "
                f"{len(notes)}"
            )

            notes.sort(
                key=lambda n: n.cvss_score,
                reverse=True
            )

            for note in notes:

                level = risk_level(
                    note
                )

                state = None

                if db.enabled():
                    state = db.save_note(
                        note
                    )

                marker = ""

                if should_alert(note):
                    marker = " !!!"

                print(
                    f"{note.number} "
                    f"v{note.version} "
                    f"[{level}] "
                    f"CVSS {note.cvss_score:.1f} "
                    f"{note.component}"
                    f"{marker}"
                )

                print(
                    f"  {note.title}"
                )

                if state in (
                    "new",
                    "updated"
                ):
                    print(
                        f"  DB state: "
                        f"{state.upper()}"
                    )

    finally:
        await sap.close()


if __name__ == "__main__":
    asyncio.run(main())
