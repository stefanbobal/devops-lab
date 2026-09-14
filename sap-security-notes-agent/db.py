import json
import os

import psycopg


SCHEMA = """
CREATE TABLE IF NOT EXISTS security_notes (
    system_sid TEXT NOT NULL,
    system_number TEXT NOT NULL,

    note_number TEXT NOT NULL,
    version INTEGER NOT NULL,

    title TEXT,
    component TEXT,
    category TEXT,

    priority TEXT,
    cvss_score DOUBLE PRECISION,
    cvss_vector TEXT,

    first_published_on TIMESTAMPTZ,
    released_on TIMESTAMPTZ,

    unread BOOLEAN,
    patch_day BOOLEAN,
    status_key TEXT,

    first_seen_at TIMESTAMPTZ
        NOT NULL DEFAULT NOW(),

    last_seen_at TIMESTAMPTZ
        NOT NULL DEFAULT NOW(),

    raw JSONB NOT NULL,

    PRIMARY KEY (
        system_sid,
        note_number
    )
);
"""


class Database:
    def __init__(self):
        self.dsn = os.getenv(
            "DATABASE_URL"
        )

    def enabled(self):
        return bool(self.dsn)

    def init_schema(self):
        if not self.dsn:
            return

        with psycopg.connect(
            self.dsn
        ) as conn:
            conn.execute(SCHEMA)

    def save_note(self, note):
        if not self.dsn:
            return None

        with psycopg.connect(
            self.dsn
        ) as conn:

            old = conn.execute(
                """
                SELECT version
                FROM security_notes
                WHERE
                    system_sid = %s
                    AND note_number = %s
                """,
                (
                    note.system_sid,
                    note.number,
                )
            ).fetchone()

            state = "existing"

            if old is None:
                state = "new"

            elif old[0] != note.version:
                state = "updated"

            conn.execute(
                """
                INSERT INTO security_notes (
                    system_sid,
                    system_number,
                    note_number,
                    version,
                    title,
                    component,
                    category,
                    priority,
                    cvss_score,
                    cvss_vector,
                    first_published_on,
                    released_on,
                    unread,
                    patch_day,
                    status_key,
                    raw
                )
                VALUES (
                    %s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,
                    %s
                )

                ON CONFLICT (
                    system_sid,
                    note_number
                )

                DO UPDATE SET
                    version =
                        EXCLUDED.version,
                    title =
                        EXCLUDED.title,
                    component =
                        EXCLUDED.component,
                    category =
                        EXCLUDED.category,
                    priority =
                        EXCLUDED.priority,
                    cvss_score =
                        EXCLUDED.cvss_score,
                    cvss_vector =
                        EXCLUDED.cvss_vector,
                    released_on =
                        EXCLUDED.released_on,
                    unread =
                        EXCLUDED.unread,
                    patch_day =
                        EXCLUDED.patch_day,
                    status_key =
                        EXCLUDED.status_key,
                    last_seen_at =
                        NOW(),
                    raw =
                        EXCLUDED.raw
                """,
                (
                    note.system_sid,
                    note.system_number,
                    note.number,
                    note.version,
                    note.title,
                    note.component,
                    note.category,
                    note.priority,
                    note.cvss_score,
                    note.cvss_vector,
                    note.first_published_on,
                    note.released_on,
                    note.unread,
                    note.patch_day,
                    note.status_key,
                    json.dumps(note.raw),
                )
            )

        return state
