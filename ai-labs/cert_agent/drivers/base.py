"""The driver interface.

A driver never returns or receives a private key. It hands out CSRs and takes
signed certificates, which are both public.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from cryptography import x509

from .. import tlscheck
from ..config import Settings
from ..models import CertInfo, Target


class DriverError(RuntimeError):
    pass


class Driver(ABC):
    # True when a CSR reuses the key of the installed certificate. The workflow then
    # also checks that the new certificate has the same key as the installed one.
    key_reuse = True

    def __init__(self, target: Target, settings: Settings):
        self.target = target
        self.settings = settings
        self.evidence: list[Path] = []  # screenshots and similar, attached to the ticket after an install

    def current_certificate(self, cert_id: str) -> CertInfo:
        """The certificate installed right now. Default: ask the TLS endpoint."""
        ref = self.target.cert(cert_id)
        if not ref.endpoint:
            raise DriverError(f"{self.target.name}/{cert_id}: no endpoint in the inventory to read the certificate from")
        try:
            certificate = tlscheck.fetch_served_certificate(ref.endpoint)
        except OSError as exc:
            raise DriverError(f"{self.target.name}/{cert_id}: cannot read {ref.endpoint}: {exc}") from exc
        return CertInfo(self.target.name, cert_id, certificate)

    @abstractmethod
    def create_csr(self, cert_id: str) -> str:
        """Create a certificate signing request on the target and return it as PEM."""

    @abstractmethod
    def install(self, cert_id: str, leaf: x509.Certificate, chain: list[x509.Certificate]) -> None:
        """Install the signed certificate. The chain lists the issuers, nearest first."""

    def rollback(self, cert_id: str, old_leaf: x509.Certificate, chain: list[x509.Certificate]) -> None:
        """Put the old certificate back. Possible without a backup when the key was reused."""
        if not self.key_reuse:
            raise NotImplementedError
        self.install(cert_id, old_leaf, chain)
