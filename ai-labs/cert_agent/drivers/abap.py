"""SAP ABAP driver: talks to three RFC function modules from abap/z_cert_agent.abap.

    Z_CERT_AGENT_GET_CERT   own certificate of a PSE, as base64 DER
    Z_CERT_AGENT_CSR        certificate request for the existing key of a PSE, as PEM
    Z_CERT_AGENT_IMPORT     import the certificate response, save, distribute, notify ICM

A certificate id is "<PSE context>/<PSE application>", for example "SSLS/DFAULT"
for the SSL server Standard PSE.

Needs the pyrfc library and the SAP NW RFC SDK. The Python side is covered by a
test with a stand-in for pyrfc. It has not run against a real SAP system.
"""
from __future__ import annotations

import base64
import os

from cryptography import x509

from .. import certcheck
from ..log import timed
from ..models import CertInfo
from .base import Driver, DriverError


class AbapDriver(Driver):
    key_reuse = True  # a STRUST certificate request is made for the existing key pair

    def _connect(self):
        try:
            from pyrfc import Connection
        except ImportError as exc:
            raise DriverError("the abap driver needs the pyrfc library and the SAP NW RFC SDK") from exc
        options = dict(self.target.options.get("rfc") or {})
        password_env = options.pop("password_env", "")
        if password_env:
            if not os.environ.get(password_env):
                raise DriverError(f"{self.target.name}: environment variable {password_env} is not set")
            options["passwd"] = os.environ[password_env]
        return Connection(**{key: str(value) for key, value in options.items()})

    def _call(self, function: str, cert_id: str, **parameters) -> dict:
        context, _, applic = cert_id.partition("/")
        if not context or not applic:
            raise DriverError(f"ABAP certificate id must be CONTEXT/APPLICATION, got {cert_id!r}")
        self.target.cert(cert_id)  # only PSEs listed in the inventory
        with timed(f"{self.target.name}: RFC {function} for {cert_id}"):
            connection = self._connect()
            try:
                return connection.call(function, IV_CONTEXT=context, IV_APPLIC=applic, **parameters)
            except Exception as exc:  # pyrfc raises its own family of errors
                detail = getattr(exc, "key", "") or getattr(exc, "message", "") or str(exc)
                raise DriverError(f"{self.target.name}: {function} failed: {detail}") from exc
            finally:
                connection.close()

    def current_certificate(self, cert_id: str) -> CertInfo:
        result = self._call("Z_CERT_AGENT_GET_CERT", cert_id)
        der = base64.b64decode(result["EV_CERT_B64"])
        return CertInfo(self.target.name, cert_id, x509.load_der_x509_certificate(der))

    def create_csr(self, cert_id: str) -> str:
        return self._call("Z_CERT_AGENT_CSR", cert_id)["EV_CSR"]

    def install(self, cert_id: str, leaf: x509.Certificate, chain: list[x509.Certificate]) -> None:
        response = "".join(certcheck.to_pem(cert) for cert in [leaf, *chain])
        self._call("Z_CERT_AGENT_IMPORT", cert_id, IV_RESPONSE=response)
