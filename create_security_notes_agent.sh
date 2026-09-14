#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="sap-security-notes-agent"

mkdir -p "$BASE_DIR"

cat > "$BASE_DIR/requirements.txt" <<'EOF'
playwright==1.55.0
python-dotenv==1.1.1
psycopg[binary]==3.2.10
EOF

cat > "$BASE_DIR/.gitignore" <<'EOF'
.env
.env.*
!.env.example
__pycache__/
*.pyc
.venv/
storage_state.json
cookies.json
EOF

cat > "$BASE_DIR/.env.example" <<'EOF'
SAP_FOR_ME_USER=
SAP_FOR_ME_PASSWORD=
SAP_FOR_ME_HEADLESS=true

# Example:
# SECURITY_NOTE_SYSTEMS=PRD:000000000000000001,QAS:000000000000000002
SECURITY_NOTE_SYSTEMS=

# Optional for MVP
DATABASE_URL=
EOF

cat > "$BASE_DIR/models.py" <<'EOF'
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
EOF

cat > "$BASE_DIR/auth.py" <<'EOF'
import os
from dataclasses import dataclass

from playwright.async_api import async_playwright


@dataclass
class SAPSession:
    playwright: object
    browser: object
    context: object

    async def close(self):
        await self.context.close()
        await self.browser.close()
        await self.playwright.stop()


async def login_to_sap_for_me():
    username = os.environ["SAP_FOR_ME_USER"]
    password = os.environ["SAP_FOR_ME_PASSWORD"]

    headless = (
        os.getenv("SAP_FOR_ME_HEADLESS", "true")
        .lower()
        != "false"
    )

    playwright = await async_playwright().start()

    browser = await playwright.chromium.launch(
        headless=headless
    )

    context = await browser.new_context()
    page = await context.new_page()

    await page.goto(
        "https://me.sap.com/",
        wait_until="domcontentloaded"
    )

    async def first_visible(selectors):
        for selector in selectors:
            locator = page.locator(selector).first

            try:
                if await locator.is_visible(timeout=1500):
                    return locator
            except Exception:
                pass

        return None

    username_input = await first_visible([
        'input[type="email"]',
        'input[name="j_username"]',
        'input[name="username"]',
        '#j_username',
    ])

    if username_input is None:
        raise RuntimeError(
            "SAP username field not found."
        )

    await username_input.fill(username)

    password_input = await first_visible([
        'input[type="password"]',
        'input[name="j_password"]',
        'input[name="password"]',
        '#j_password',
    ])

    if password_input is None:
        for selector in [
            'button:has-text("Next")',
            'button:has-text("Continue")',
            'button[type="submit"]',
        ]:
            try:
                button = page.locator(selector).first

                if await button.is_visible(timeout=1000):
                    await button.click()
                    break
            except Exception:
                pass

        password_input = await first_visible([
            'input[type="password"]',
            'input[name="j_password"]',
            'input[name="password"]',
            '#j_password',
        ])

    if password_input is None:
        raise RuntimeError(
            "SAP password field not found."
        )

    await password_input.fill(password)

    submitted = False

    for selector in [
        'button:has-text("Sign in")',
        'button:has-text("Log On")',
        'button:has-text("Login")',
        'button[type="submit"]',
    ]:
        try:
            button = page.locator(selector).first

            if await button.is_visible(timeout=1000):
                await button.click()
                submitted = True
                break
        except Exception:
            pass

    if not submitted:
        await password_input.press("Enter")

    await page.wait_for_url(
        "**me.sap.com/**",
        timeout=120000
    )

    return SAPSession(
        playwright=playwright,
        browser=browser,
        context=context
    )
EOF

cat > "$BASE_DIR/odata_client.py" <<'EOF'
from urllib.parse import urlencode


SERVICE_BASE = (
    "https://me.sap.com/"
    "backend/raw/core/CBLegacyProxyVerticle/"
    "odata/sfm/securitynotes"
)


class SecurityNotesODataClient:
    def __init__(self, context):
        self.context = context

    async def get_json(
        self,
        entity: str,
        params: dict | None = None
    ):
        url = (
            f"{SERVICE_BASE}/"
            f"{entity.lstrip('/')}"
        )

        if params:
            url += "?" + urlencode(
                params,
                safe="$(),' "
            )

        response = await self.context.request.get(
            url,
            headers={
                "Accept": "application/json",
                "Accept-Language": "en-US",
                "DataServiceVersion": "2.0",
                "MaxDataServiceVersion": "2.0",
                "X-Requested-With": "XMLHttpRequest",
            }
        )

        text = await response.text()

        if response.status != 200:
            raise RuntimeError(
                f"OData GET failed: "
                f"HTTP {response.status}: "
                f"{text[:1000]}"
            )

        return await response.json()
EOF

cat > "$BASE_DIR/collectors.py" <<'EOF'
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
EOF

cat > "$BASE_DIR/config.py" <<'EOF'
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
EOF

cat > "$BASE_DIR/db.py" <<'EOF'
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
EOF

cat > "$BASE_DIR/risk.py" <<'EOF'
def risk_level(note):
    if note.priority == "HotNews":
        return "CRITICAL"

    if note.cvss_score >= 9.0:
        return "CRITICAL"

    if note.cvss_score >= 7.0:
        return "HIGH"

    if note.cvss_score >= 4.0:
        return "MEDIUM"

    return "LOW"


def should_alert(note):
    return (
        note.priority == "HotNews"
        or note.cvss_score >= 8.0
    )
EOF

cat > "$BASE_DIR/main.py" <<'EOF'
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
EOF

cat > "$BASE_DIR/Dockerfile" <<'EOF'
FROM mcr.microsoft.com/playwright/python:v1.55.0-noble

WORKDIR /app

COPY requirements.txt .

RUN pip install \
    --no-cache-dir \
    -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
ENV SAP_FOR_ME_HEADLESS=true

CMD ["python", "main.py"]
EOF

cat > "$BASE_DIR/README.md" <<'EOF'
# SAP Security Notes Agent

MVP flow:

SAP for Me
-> SAPNoteSet
-> filter by system number
-> CVSS / priority evaluation
-> PostgreSQL history
-> future Teams / AI integration

Do not commit:

- SAP credentials
- session cookies
- CSRF tokens
- company system numbers
- production payloads
EOF

echo
echo "Created:"
find "$BASE_DIR" \
    -maxdepth 1 \
    -type f \
    -printf "  %f\n" \
    | sort

echo
echo "Security Notes Agent bootstrap complete."
