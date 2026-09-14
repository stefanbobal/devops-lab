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
