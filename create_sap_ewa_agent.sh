#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="sap-ewa-agent"

mkdir -p "$BASE_DIR"

cat > "$BASE_DIR/requirements.txt" <<'EOF'
playwright==1.55.0
httpx==0.28.1
psycopg[binary]==3.2.10
beautifulsoup4==4.13.5
python-dotenv==1.1.1
EOF

cat > "$BASE_DIR/.gitignore" <<'EOF'
.env
__pycache__/
*.pyc
.venv/
venv/
cookies.json
storage_state.json
playwright/.auth/
EOF

cat > "$BASE_DIR/.env.example" <<'EOF'
SAP_FOR_ME_USER=
SAP_FOR_ME_PASSWORD=
SAP_FOR_ME_HEADLESS=true
DATABASE_URL=
EOF

cat > "$BASE_DIR/models.py" <<'EOF'
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

    headless = os.getenv(
        "SAP_FOR_ME_HEADLESS",
        "true"
    ).lower() != "false"

    p = await async_playwright().start()

    browser = await p.chromium.launch(
        headless=headless
    )

    context = await browser.new_context()
    page = await context.new_page()

    await page.goto(
        "https://me.sap.com/",
        wait_until="domcontentloaded"
    )

    username_selectors = [
        'input[type="email"]',
        'input[name="j_username"]',
        'input[name="username"]',
        '#j_username',
    ]

    password_selectors = [
        'input[type="password"]',
        'input[name="j_password"]',
        'input[name="password"]',
        '#j_password',
    ]

    async def find_visible(selectors):
        for selector in selectors:
            locator = page.locator(selector).first

            try:
                if await locator.is_visible(timeout=1500):
                    return locator
            except Exception:
                pass

        return None

    user_input = await find_visible(
        username_selectors
    )

    if not user_input:
        raise RuntimeError(
            "Username field not found."
        )

    await user_input.fill(username)

    password_input = await find_visible(
        password_selectors
    )

    if not password_input:
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

        password_input = await find_visible(
            password_selectors
        )

    if not password_input:
        raise RuntimeError(
            "Password field not found."
        )

    await password_input.fill(password)
    await password_input.press("Enter")

    await page.wait_for_url(
        "**me.sap.com/**",
        timeout=120000
    )

    return SAPSession(
        p,
        browser,
        context
    )
EOF

cat > "$BASE_DIR/odata_client.py" <<'EOF'
import json
import re
import uuid


SERVICE_BASE = (
    "https://me.sap.com/backend/raw/core/"
    "CBLegacyProxyVerticle/"
    "sapforme/odata/"
    "sm_sise_session_reader"
)


class SAPForMeODataClient:
    def __init__(self, context):
        self.context = context

    async def get_json(self, path):
        boundary = (
            "batch_"
            + uuid.uuid4().hex
        )

        body = (
            f"--{boundary}\r\n"
            "Content-Type: application/http\r\n"
            "Content-Transfer-Encoding: binary\r\n"
            "\r\n"
            f"GET {path} HTTP/1.1\r\n"
            "sap-cancel-on-close: true\r\n"
            "sap-contextid-accept: header\r\n"
            "Accept: application/json\r\n"
            "Accept-Language: en-US\r\n"
            "DataServiceVersion: 2.0\r\n"
            "MaxDataServiceVersion: 2.0\r\n"
            "X-Requested-With: XMLHttpRequest\r\n"
            "\r\n"
            f"--{boundary}--\r\n"
        )

        response = await self.context.request.post(
            SERVICE_BASE + "/$batch",
            headers={
                "Content-Type":
                    f"multipart/mixed; boundary={boundary}",
                "Accept": "multipart/mixed",
                "DataServiceVersion": "2.0",
                "MaxDataServiceVersion": "2.0",
                "X-Requested-With": "XMLHttpRequest",
            },
            data=body
        )

        text = await response.text()

        if response.status != 200:
            raise RuntimeError(
                f"Batch failed HTTP "
                f"{response.status}: "
                f"{text[:500]}"
            )

        match = re.search(
            r'\{.*\}',
            text,
            re.S
        )

        if not match:
            raise RuntimeError(
                "No JSON found in batch response."
            )

        return json.loads(
            match.group(0)
        )
EOF

cat > "$BASE_DIR/parser.py" <<'EOF'
import html
import json

from bs4 import BeautifulSoup


def strip_html(value):
    soup = BeautifulSoup(
        value or "",
        "html.parser"
    )

    return html.unescape(
        soup.get_text(
            "\n",
            strip=True
        )
    )


def normalize_component(component):
    component_type = (
        component.get(
            "componentType",
            "UNKNOWN"
        )
        .upper()
    )

    raw = component.get(
        "componentJSON"
    )

    if isinstance(raw, str):
        payload = json.loads(raw)
    else:
        payload = raw or {}

    if component_type == "TEXT":
        html_text = (
            payload.get("data", {})
            .get("htmlText", "")
        )

        return {
            "type": "TEXT",
            "text": strip_html(
                html_text
            )
        }

    if component_type == "TABLE":
        return {
            "type": "TABLE",
            "header":
                payload.get(
                    "headerText",
                    ""
                ),
            "rows":
                payload.get(
                    "DATA",
                    []
                ),
            "columns":
                payload.get(
                    "columns",
                    []
                ),
        }

    return {
        "type": component_type,
        "raw": payload
    }


def normalize_section_tree(payload):
    root = payload.get(
        "d",
        payload
    )

    sections = (
        root
        .get(
            "SelfOrChildrenRecursive",
            {}
        )
        .get(
            "results",
            []
        )
    )

    if not sections:
        sections = [root]

    result = []

    for section in sections:
        components = (
            section
            .get(
                "Components",
                {}
            )
            .get(
                "results",
                []
            )
        )

        result.append({
            "section_guid":
                section.get(
                    "section"
                ),
            "name":
                section.get(
                    "name"
                ),
            "rating":
                section.get(
                    "rating",
                    {}
                ),
            "components": [
                normalize_component(c)
                for c
                in components
            ]
        })

    return result
EOF

cat > "$BASE_DIR/collectors.py" <<'EOF'
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
EOF

cat > "$BASE_DIR/db.py" <<'EOF'
# Database layer intentionally left minimal
# for the first collector test.

class Database:
    def __init__(self, *args, **kwargs):
        pass

    def enabled(self):
        return False
EOF

cat > "$BASE_DIR/main.py" <<'EOF'
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
# SAP EWA Agent MVP

Current flow:

SAP for Me
-> EWA sessions
-> TOC
-> SectionSet
-> Components
-> normalized JSON

This first version intentionally does not
persist anything to PostgreSQL yet.

First verify that authentication and
the OData batch collector work.
EOF

echo
echo "Created files:"
find "$BASE_DIR" \
    -maxdepth 1 \
    -type f \
    -printf "  %f\n" \
    | sort

echo
echo "Bootstrap complete."
