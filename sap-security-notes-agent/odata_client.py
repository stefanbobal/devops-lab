from urllib.parse import urlencode


SERVICE_BASE = (
    "https://me.sap.com/backend/raw/core/"
    "W7LegacyProxyVerticle/"
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
