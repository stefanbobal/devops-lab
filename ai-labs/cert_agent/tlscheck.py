"""Read the certificate a host really serves, by doing a TLS handshake."""
from __future__ import annotations

import socket
import ssl
import time

from cryptography import x509

from .certcheck import fingerprint
from .log import step


def split_endpoint(endpoint: str) -> tuple[str, int]:
    host, _, port = endpoint.rpartition(":")
    if not host or not port.isdigit():
        raise ValueError(f"endpoint must look like host:port, got {endpoint!r}")
    return host, int(port)


def fetch_served_certificate(endpoint: str, timeout: float = 10) -> x509.Certificate:
    """Return the server certificate presented at host:port.

    Trust is deliberately not checked here. The caller compares the fingerprint
    with the certificate it expects, which is a stronger check than a CA lookup.
    """
    host, port = split_endpoint(endpoint)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, port), timeout=timeout) as sock:
        with context.wrap_socket(sock, server_hostname=host) as tls:
            der = tls.getpeercert(binary_form=True)
    if not der:
        raise ssl.SSLError(f"{endpoint} presented no certificate")
    return x509.load_der_x509_certificate(der)


def wait_until_served(endpoint: str, expected_fingerprint: str, timeout: int = 300, interval: int = 15) -> bool:
    """Poll the endpoint until it serves the expected certificate, or the time runs out."""
    deadline = time.monotonic() + timeout
    attempt = 0
    while True:
        attempt += 1
        try:
            served = fingerprint(fetch_served_certificate(endpoint))
        except OSError as exc:
            served = f"error: {exc}"
        if served == expected_fingerprint:
            step(f"TLS check {endpoint}: attempt {attempt}, new certificate is served")
            return True
        if time.monotonic() + interval > deadline:
            step(f"TLS check {endpoint}: attempt {attempt}, giving up (last answer: {served[:40]})")
            return False
        step(f"TLS check {endpoint}: attempt {attempt}, not served yet, next try in {interval}s")
        time.sleep(interval)
