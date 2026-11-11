"""A target that lives in a directory. For tests and for trying the workflow without SAP.

Layout: <dir>/<cert id>/key.pem (never leaves the directory), cert.pem, chain.pem.
"""
from __future__ import annotations

import re
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization

from .. import certcheck
from ..models import CertInfo
from .base import Driver, DriverError


class FakeDriver(Driver):
    key_reuse = True

    def _dir(self, cert_id: str) -> Path:
        self.target.cert(cert_id)  # must be in the inventory
        return Path(self.target.options["dir"]) / re.sub(r"[^A-Za-z0-9._-]+", "_", cert_id)

    def _key(self, cert_id: str):
        return serialization.load_pem_private_key((self._dir(cert_id) / "key.pem").read_bytes(), password=None)

    def current_certificate(self, cert_id: str) -> CertInfo:
        path = self._dir(cert_id) / "cert.pem"
        if not path.exists():
            raise DriverError(f"{self.target.name}/{cert_id}: no certificate at {path}")
        return CertInfo(self.target.name, cert_id, certcheck.load_certificates(path.read_bytes())[0])

    def create_csr(self, cert_id: str) -> str:
        current = self.current_certificate(cert_id).certificate
        builder = x509.CertificateSigningRequestBuilder().subject_name(current.subject)
        names = certcheck.dns_names(current)
        if names:
            san = x509.SubjectAlternativeName([x509.DNSName(name) for name in names])
            builder = builder.add_extension(san, critical=False)
        return certcheck.to_pem(builder.sign(self._key(cert_id), hashes.SHA256()))

    def install(self, cert_id: str, leaf: x509.Certificate, chain: list[x509.Certificate]) -> None:
        if certcheck.spki(leaf) != certcheck.spki(self._key(cert_id)):
            raise DriverError("the certificate does not belong to the key on the target")
        directory = self._dir(cert_id)
        (directory / "cert.pem").write_text(certcheck.to_pem(leaf))
        (directory / "chain.pem").write_text("".join(certcheck.to_pem(c) for c in chain))
