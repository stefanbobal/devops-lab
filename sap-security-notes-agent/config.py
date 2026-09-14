import os


def get_systems():
    value = os.getenv(
        "SECURITY_NOTE_SYSTEMS",
        ""
    ).strip()

    if not value:
        raise RuntimeError(
            "SECURITY_NOTE_SYSTEMS is empty."
        )

    systems = {}

    for entry in value.split(","):
        sid, number = entry.split(
            ":",
            1
        )

        systems[sid.strip()] = (
            number.strip()
        )

    return systems
