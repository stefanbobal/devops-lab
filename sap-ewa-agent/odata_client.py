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
        self.csrf_token = None

    async def _fetch_csrf_token(self):
        print("Fetching EWA CSRF token...")

        urls = [
            SERVICE_BASE + "/",
            SERVICE_BASE + "/$metadata",
        ]

        last_status = None
        last_text = ""

        for url in urls:
            response = await self.context.request.get(
                url,
                headers={
                    "X-CSRF-Token": "Fetch",
                    "Accept": "*/*",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": "https://me.sap.com/",
                },
            )

            last_status = response.status
            last_text = await response.text()

            token = response.headers.get(
                "x-csrf-token"
            )

            print(
                "CSRF fetch HTTP status:",
                response.status
            )

            if token:
                print(
                    "EWA CSRF token received."
                )

                self.csrf_token = token
                return token

        raise RuntimeError(
            "Could not obtain EWA CSRF token. "
            f"Last HTTP status: {last_status}. "
            f"Response: {last_text[:300]}"
        )

    async def get_json(self, path):
        if not self.csrf_token:
            await self._fetch_csrf_token()

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
            "X-CSRF-Token": self.csrf_token,
            "Origin": "https://me.sap.com",
            "Referer": "https://me.sap.com/",
            },
         data=body.encode("utf-8"),
         timeout=120000,
        )

        text = await response.text()

        print(
            "EWA batch HTTP status:",
            response.status
        )

        if response.status == 403:
            print(
                "EWA batch returned 403. "
                "Refreshing CSRF token..."
            )

            self.csrf_token = None
            await self._fetch_csrf_token()

            response = await self.context.request.post(
                SERVICE_BASE + "/$batch",
                headers={
                    "Content-Type":
                        f"multipart/mixed; boundary={boundary}",
                    "Accept": "multipart/mixed",
                    "DataServiceVersion": "2.0",
                    "MaxDataServiceVersion": "2.0",
                    "X-Requested-With": "XMLHttpRequest",
                    "X-CSRF-Token": self.csrf_token,
                    "Origin": "https://me.sap.com",
                    "Referer": "https://me.sap.com/",
                },
                data=body.encode("utf-8"),
                timeout=120000,
            )

            text = await response.text()

            print(
                "EWA batch retry HTTP status:",
                response.status
            )

        if response.status != 200:
            raise RuntimeError(
                f"Batch failed HTTP "
                f"{response.status}: "
                f"{text[:500]}"
            )

        # Extract JSON part from multipart batch response.
        match = re.search(
            r'\{.*\}',
            text,
            re.S,
        )

        if not match:
            raise RuntimeError(
                "No JSON found in batch response."
            )

        return json.loads(
            match.group(0)
        )