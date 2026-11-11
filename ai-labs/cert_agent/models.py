"""Plain data objects shared by the drivers and the workflow."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from cryptography import x509


@dataclass(frozen=True)
class CertRef:
    """One certificate on a target, as listed in the inventory."""

    id: str
    endpoint: str = ""  # "host:port" that serves the certificate; used for the TLS check
    names: tuple[str, ...] = ()  # DNS names the new certificate must cover, on top of the CSR's


@dataclass
class Target:
    name: str
    type: str
    environment: str = "sandbox"
    approval_required: bool = True
    renew_days_before: int = 30
    certs: list[CertRef] = field(default_factory=list)
    options: dict = field(default_factory=dict)  # the type-specific block: rfc, nwa, cloudrun, fake

    def cert(self, cert_id: str) -> CertRef:
        for ref in self.certs:
            if ref.id == cert_id:
                return ref
        raise KeyError(f"certificate {cert_id!r} is not in the inventory of target {self.name!r}")


@dataclass
class CertInfo:
    """A certificate as it is installed on a target right now."""

    target: str
    cert_id: str
    certificate: x509.Certificate

    def days_left(self, now: datetime) -> int:
        return (self.certificate.not_valid_after_utc - now).days
