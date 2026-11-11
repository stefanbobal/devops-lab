"""TLS check against a real TLS server on localhost."""
import socket
import ssl
import threading

import pytest

from cert_agent import certcheck, tlscheck
from conftest import CA, key_pem, make_csr, new_key


@pytest.fixture
def tls_server(tmp_path):
    ca = CA("Root")
    key = new_key()
    cert = ca.sign(make_csr(key, cn="localhost"))
    (tmp_path / "cert.pem").write_text(certcheck.to_pem(cert))
    (tmp_path / "key.pem").write_bytes(key_pem(key))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(tmp_path / "cert.pem", tmp_path / "key.pem")
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()

    def serve():
        while True:
            try:
                connection, _ = listener.accept()
            except OSError:
                return
            try:
                context.wrap_socket(connection, server_side=True).close()
            except OSError:
                pass

    threading.Thread(target=serve, daemon=True).start()
    yield f"127.0.0.1:{listener.getsockname()[1]}", cert
    listener.close()


def test_reads_the_served_certificate(tls_server):
    endpoint, cert = tls_server
    assert tlscheck.fetch_served_certificate(endpoint) == cert


def test_wait_until_served(tls_server):
    endpoint, cert = tls_server
    assert tlscheck.wait_until_served(endpoint, certcheck.fingerprint(cert), timeout=2, interval=1) is True
    assert tlscheck.wait_until_served(endpoint, "00" * 32, timeout=2, interval=1) is False


def test_unreachable_endpoint(tls_server):
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    endpoint = f"127.0.0.1:{closed.getsockname()[1]}"  # bound but not listening
    with pytest.raises(OSError):
        tlscheck.fetch_served_certificate(endpoint, timeout=2)
    assert tlscheck.wait_until_served(endpoint, "00" * 32, timeout=1, interval=1) is False
    closed.close()


@pytest.mark.parametrize("endpoint", ["host", "host:", ":443", "host:https"])
def test_bad_endpoint_text(endpoint):
    with pytest.raises(ValueError):
        tlscheck.split_endpoint(endpoint)
