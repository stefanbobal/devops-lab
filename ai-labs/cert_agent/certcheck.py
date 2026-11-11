"""Parse certificates and CSRs, and decide whether a signed certificate may be installed.

The decision is purely cryptographic, so it does not matter who attached the file
to the ticket: a certificate passes only if it belongs to our key, carries our
names, is valid long enough and chains to a CA on the allow-list.
"""
from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import NameOID

MAX_CHAIN = 8
HOSTNAME = re.compile(r"^(\*\.)?[a-z0-9-]+(\.[a-z0-9-]+)+$")


@dataclass
class ValidationResult:
    leaf: x509.Certificate | None = None
    chain: list[x509.Certificate] = field(default_factory=list)  # issuers, nearest first
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.leaf is not None and not self.problems


# ---------------------------------------------------------------- parsing

def load_certificates(data: bytes) -> list[x509.Certificate]:
    """Read one or more certificates from PEM, DER, PKCS#7 (.p7b) or bare base64."""
    text = data.strip()
    try:
        if b"-----BEGIN CERTIFICATE-----" in text:
            return list(x509.load_pem_x509_certificates(text))
        if b"-----BEGIN PKCS7-----" in text:
            return list(pkcs7.load_pem_pkcs7_certificates(text))
    except ValueError as exc:
        raise ValueError(f"damaged PEM file: {exc}") from exc
    for loader in (lambda d: [x509.load_der_x509_certificate(d)], pkcs7.load_der_pkcs7_certificates):
        try:
            certs = list(loader(data))
        except (ValueError, TypeError):
            continue
        if certs:
            return certs
    try:  # some CAs send the DER bytes as base64 without the PEM header lines
        decoded = base64.b64decode(b"".join(text.split()), validate=True)
    except (binascii.Error, ValueError):
        decoded = b""
    if decoded and decoded != data:
        return load_certificates(decoded)
    raise ValueError("not a certificate file (expected PEM, DER or PKCS#7)")


def load_csr(data: bytes) -> x509.CertificateSigningRequest:
    """Read a CSR from PEM or DER. SAP and keytool write 'NEW CERTIFICATE REQUEST'."""
    text = data.strip()
    try:
        if b"-----BEGIN" in text:
            return x509.load_pem_x509_csr(text.replace(b"NEW CERTIFICATE REQUEST", b"CERTIFICATE REQUEST"))
        return x509.load_der_x509_csr(data)
    except ValueError as exc:
        raise ValueError(f"not a certificate request: {exc}") from exc


def to_pem(obj) -> str:
    return obj.public_bytes(serialization.Encoding.PEM).decode()


# ---------------------------------------------------------------- facts about a certificate

def fingerprint(cert: x509.Certificate) -> str:
    return cert.fingerprint(hashes.SHA256()).hex()


def spki(obj) -> bytes:
    """The public key in a comparable form. Works for certificates and CSRs."""
    return obj.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )


def subject(obj) -> str:
    return obj.subject.rfc4514_string()


def common_name(obj) -> str:
    attrs = obj.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    return str(attrs[0].value) if attrs else ""


def dns_names(obj) -> list[str]:
    """DNS names from the subject alternative name extension, lower case."""
    try:
        san = obj.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        return []
    return [name.lower() for name in san.get_values_for_type(x509.DNSName)]


def required_names(csr: x509.CertificateSigningRequest, extra: tuple[str, ...] = ()) -> list[str]:
    """Names the signed certificate must cover: the CSR's, plus those from the inventory."""
    names = dns_names(csr)
    cn = common_name(csr).lower()
    if not names and HOSTNAME.match(cn):
        names = [cn]
    for name in extra:
        if name.lower() not in names:
            names.append(name.lower())
    return names


def _covers(have: str, need: str) -> bool:
    if have == need:
        return True
    return have.startswith("*.") and "." in need and need.split(".", 1)[1] == have[2:]


# ---------------------------------------------------------------- validation

def _is_ca(cert: x509.Certificate) -> bool:
    try:
        return bool(cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca)
    except x509.ExtensionNotFound:
        return False


def _find_issuer(cert: x509.Certificate, pool: list[x509.Certificate]) -> x509.Certificate | None:
    for candidate in pool:
        if candidate.subject != cert.issuer or not _is_ca(candidate):
            continue
        try:
            cert.verify_directly_issued_by(candidate)
        except (ValueError, TypeError, InvalidSignature):
            continue
        return candidate
    return None


def build_chain(
    leaf: x509.Certificate,
    others: list[x509.Certificate],
    trusted: list[x509.Certificate],
    now: datetime,
) -> tuple[list[x509.Certificate], list[str]]:
    """Walk from the leaf up to a CA on the allow-list, checking every signature."""
    trusted_fps = {fingerprint(c) for c in trusted}
    pool = [c for c in others if c is not leaf] + list(trusted)
    chain: list[x509.Certificate] = []
    seen = {fingerprint(leaf)}
    current = leaf
    for _ in range(MAX_CHAIN):
        issuer = _find_issuer(current, pool)
        if issuer is None:
            return chain, [f"no issuing CA certificate found for {subject(current)}"]
        fp = fingerprint(issuer)
        if fp in seen:
            return chain, [f"the chain ends at {subject(current)}, which is not on the CA allow-list"]
        seen.add(fp)
        if not issuer.not_valid_before_utc <= now <= issuer.not_valid_after_utc:
            return chain, [f"CA certificate {subject(issuer)} is not valid today"]
        chain.append(issuer)
        if fp in trusted_fps:
            return chain, []
        current = issuer
    return chain, ["the certificate chain is too long"]


def validate(
    csr: x509.CertificateSigningRequest,
    certs: list[x509.Certificate],
    trusted: list[x509.Certificate],
    *,
    now: datetime,
    min_valid_days: int = 30,
    extra_names: tuple[str, ...] = (),
) -> ValidationResult:
    """Check a signed certificate (with its chain) against the CSR it answers."""
    result = ValidationResult()
    key = spki(csr)
    leaf = next((c for c in certs if spki(c) == key), None)
    if leaf is None:
        result.problems.append("no certificate in the file belongs to the key of the CSR")
        return result
    result.leaf = leaf

    # Clients ignore the common name once a certificate has alternative names, so do we.
    have = set(dns_names(leaf)) or {common_name(leaf).lower()}
    for name in required_names(csr, extra_names):
        if not any(_covers(h, name) for h in have):
            result.problems.append(f"the name {name} is missing from the certificate")

    if leaf.not_valid_before_utc > now:
        result.problems.append(f"not valid yet (starts {leaf.not_valid_before_utc:%Y-%m-%d})")
    if leaf.not_valid_after_utc < now + timedelta(days=min_valid_days):
        result.problems.append(
            f"expires too soon ({leaf.not_valid_after_utc:%Y-%m-%d}, minimum is {min_valid_days} days from now)"
        )

    result.chain, chain_problems = build_chain(leaf, certs, trusted, now)
    result.problems.extend(chain_problems)
    return result
