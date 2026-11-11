"""Driver for targets handled by an existing automation service on Cloud Run
(BOBJ, Google Cloud load balancer).

ASSUMED CONTRACT. The real service was not known when this was written, so adapt
the two calls below to it:

    POST <base_url><csr_path>      {"system": ..., "cert_id": ...}
                                   -> {"csr_pem": "-----BEGIN CERTIFICATE REQUEST-----..."}
    POST <base_url><install_path>  {"system": ..., "cert_id": ..., "certificate_pem": ..., "chain_pem": ...}
                                   -> any 2xx answer

Authentication is a Google identity token of the service account the agent runs as.
The current certificate is read from the TLS endpoint in the inventory.
"""
from __future__ import annotations

import requests
from cryptography import x509

from .. import certcheck
from ..log import timed
from .base import Driver, DriverError


class CloudRunDriver(Driver):
    def __init__(self, target, settings):
        super().__init__(target, settings)
        self.options = target.options.get("cloudrun") or {}
        if not self.options.get("base_url"):
            raise DriverError(f"{target.name}: cloudrun.base_url is missing in the inventory")
        # Set key_reuse: true in the inventory if the service keeps the key between renewals.
        self.key_reuse = bool(self.options.get("key_reuse", False))

    def _token(self) -> str:
        try:
            from google.auth.transport.requests import Request
            from google.oauth2 import id_token
        except ImportError as exc:
            raise DriverError("the cloudrun driver needs the google-auth library") from exc
        audience = self.options.get("audience") or self.options["base_url"]
        return id_token.fetch_id_token(Request(), audience)

    def _post(self, path: str, payload: dict) -> dict:
        url = self.options["base_url"].rstrip("/") + path
        with timed(f"{self.target.name}: POST {path}"):
            try:
                response = requests.post(
                    url, json=payload, headers={"Authorization": f"Bearer {self._token()}"}, timeout=120
                )
            except requests.RequestException as exc:
                raise DriverError(f"{self.target.name}: {url}: {exc}") from exc
            if response.status_code >= 400:
                raise DriverError(f"{self.target.name}: {url}: HTTP {response.status_code}: {response.text[:300]}")
        return response.json() if response.content else {}

    def _base_payload(self, cert_id: str) -> dict:
        self.target.cert(cert_id)
        return {"system": self.options.get("system", self.target.name), "cert_id": cert_id}

    def create_csr(self, cert_id: str) -> str:
        data = self._post(self.options.get("csr_path", "/csr"), self._base_payload(cert_id))
        if "csr_pem" not in data:
            raise DriverError(f"{self.target.name}: the service returned no csr_pem")
        return data["csr_pem"]

    def install(self, cert_id: str, leaf: x509.Certificate, chain: list[x509.Certificate]) -> None:
        payload = self._base_payload(cert_id)
        payload["certificate_pem"] = certcheck.to_pem(leaf)
        payload["chain_pem"] = "".join(certcheck.to_pem(cert) for cert in chain)
        self._post(self.options.get("install_path", "/install"), payload)
