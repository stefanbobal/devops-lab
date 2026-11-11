"""The Python side of the ABAP and Cloud Run drivers, with stand-ins for SAP and the service.

These tests prove what the drivers send and how they read the answers. They do
not prove that a real SAP system or the real Cloud Run service behaves that way.
"""
import base64
import json
import sys
import threading
import types
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from cryptography.hazmat.primitives import serialization

from cert_agent import certcheck
from cert_agent.config import load_inventory
from cert_agent.drivers import DriverError, get_driver
from cert_agent.models import CertRef, Target
from conftest import CA, Env, make_csr, new_key


# ---------------------------------------------------------------- ABAP over RFC

@pytest.fixture
def sap(monkeypatch, tmp_path):
    """A stand-in for pyrfc that behaves like the three Z function modules."""
    env = Env(tmp_path)
    state = types.SimpleNamespace(calls=[], connections=[], cert=env.first, key=env.key, closed=0)

    class Connection:
        def __init__(self, **params):
            state.connections.append(params)

        def call(self, function, **params):
            state.calls.append((function, params))
            if params["IV_CONTEXT"] != "SSLS":
                error = RuntimeError("abap exception")
                error.key = "PSE_NOT_ALLOWED"
                raise error
            if function == "Z_CERT_AGENT_GET_CERT":
                der = state.cert.public_bytes(serialization.Encoding.DER)
                return {"EV_CERT_B64": base64.b64encode(der).decode()}
            if function == "Z_CERT_AGENT_CSR":
                pem = certcheck.to_pem(make_csr(state.key))
                return {"EV_CSR": pem.replace("CERTIFICATE REQUEST", "NEW CERTIFICATE REQUEST")}
            if function == "Z_CERT_AGENT_IMPORT":
                state.cert = certcheck.load_certificates(params["IV_RESPONSE"].encode())[0]
                return {"EV_ICM_NOTIFIED": "X"}
            raise AssertionError(function)

        def close(self):
            state.closed += 1

    monkeypatch.setitem(sys.modules, "pyrfc", types.SimpleNamespace(Connection=Connection))
    monkeypatch.setenv("ABAP_TEST_PASSWORD", "pw")
    target = Target(
        name="abap-test", type="abap", certs=[CertRef(id="SSLS/DFAULT"), CertRef(id="SNCS/DFAULT")],
        options={"rfc": {"ashost": "sap.example.internal", "sysnr": "00", "client": 100, "user": "CERT_AGENT",
                         "password_env": "ABAP_TEST_PASSWORD"}},
    )
    return env, state, get_driver(target, env.settings)


def test_abap_driver_reads_requests_and_imports(sap):
    env, state, driver = sap
    assert driver.current_certificate("SSLS/DFAULT").certificate == env.first
    assert state.connections[0] == {
        "ashost": "sap.example.internal", "sysnr": "00", "client": "100", "user": "CERT_AGENT", "passwd": "pw",
    }

    csr = certcheck.load_csr(driver.create_csr("SSLS/DFAULT").encode())
    assert certcheck.spki(csr) == certcheck.spki(env.first)

    new = env.issuing.sign(csr)
    driver.install("SSLS/DFAULT", new, [env.issuing.cert, env.root.cert])
    function, params = state.calls[-1]
    assert function == "Z_CERT_AGENT_IMPORT"
    assert params["IV_CONTEXT"] == "SSLS" and params["IV_APPLIC"] == "DFAULT"
    sent = certcheck.load_certificates(params["IV_RESPONSE"].encode())
    assert sent == [new, env.issuing.cert, env.root.cert]  # own certificate first, then the issuers
    assert driver.current_certificate("SSLS/DFAULT").certificate == new
    assert state.closed == len(state.connections)  # every connection is closed again


def test_abap_driver_reports_abap_exceptions_and_bad_ids(sap, monkeypatch):
    _, _, driver = sap
    with pytest.raises(DriverError, match="PSE_NOT_ALLOWED"):
        driver.create_csr("SNCS/DFAULT")
    with pytest.raises(KeyError):
        driver.create_csr("SSLC/ANONYM")  # not in the inventory
    with pytest.raises(DriverError, match="CONTEXT/APPLICATION"):
        driver.create_csr("SSLS")
    monkeypatch.delenv("ABAP_TEST_PASSWORD")
    with pytest.raises(DriverError, match="ABAP_TEST_PASSWORD is not set"):
        driver.create_csr("SSLS/DFAULT")


# ---------------------------------------------------------------- Cloud Run service

class Service(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.calls.append((self.path, self.headers.get("Authorization"), payload))
        if self.path == "/csr":
            body = json.dumps({"csr_pem": self.server.csr_pem}).encode()
            status = 200
        elif self.path == "/install":
            body, status = b"", 204
        else:
            body, status = b"no such system", 404
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def service(tmp_path, monkeypatch):
    env = Env(tmp_path)
    server = HTTPServer(("127.0.0.1", 0), Service)
    server.calls = []
    server.csr_pem = certcheck.to_pem(make_csr(new_key()))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    target = Target(
        name="glb-test", type="cloudrun", certs=[CertRef(id="frontend")],
        options={"cloudrun": {"base_url": f"http://127.0.0.1:{server.server_port}", "system": "glb-dev"}},
    )
    driver = get_driver(target, env.settings)
    monkeypatch.setattr(driver, "_token", lambda: "id-token")
    yield env, server, driver
    server.shutdown()


def test_cloudrun_driver_calls_the_assumed_contract(service):
    env, server, driver = service
    assert driver.create_csr("frontend") == server.csr_pem
    assert server.calls[-1] == ("/csr", "Bearer id-token", {"system": "glb-dev", "cert_id": "frontend"})

    leaf = env.issuing.sign(make_csr(new_key()))
    driver.install("frontend", leaf, [env.issuing.cert])
    path, _, payload = server.calls[-1]
    assert path == "/install" and payload["system"] == "glb-dev" and payload["cert_id"] == "frontend"
    assert certcheck.load_certificates(payload["certificate_pem"].encode()) == [leaf]
    assert certcheck.load_certificates(payload["chain_pem"].encode()) == [env.issuing.cert]

    assert driver.key_reuse is False
    with pytest.raises(NotImplementedError):
        driver.rollback("frontend", leaf, [])


def test_cloudrun_driver_reports_http_errors(service):
    _, _, driver = service
    driver.options["csr_path"] = "/missing"
    with pytest.raises(DriverError, match="HTTP 404"):
        driver.create_csr("frontend")


# ---------------------------------------------------------------- inventory and factory

def test_example_inventory_loads():
    from cert_agent.config import HERE

    targets = load_inventory(HERE / "inventory.example.yaml")
    assert {name: t.type for name, t in targets.items()} == {
        "abap-sandbox": "abap", "java-sandbox": "java_nwa", "bobj-dev": "cloudrun", "glb-dev": "cloudrun",
    }
    abap = targets["abap-sandbox"]
    assert abap.approval_required is False and abap.renew_days_before == 30
    assert abap.cert("SSLS/DFAULT").endpoint == "abap-sandbox.example.internal:44300"
    assert abap.options["rfc"]["password_env"] == "ABAP_SANDBOX_PASSWORD"
    assert targets["bobj-dev"].approval_required is True  # from the defaults
    assert targets["glb-dev"].cert("frontend").names == ("app-dev.example.internal",)


def test_unknown_target_type_and_missing_options(tmp_path):
    env = Env(tmp_path)
    with pytest.raises(DriverError, match="unknown type"):
        get_driver(Target(name="x", type="mainframe", certs=[CertRef(id="a")]), env.settings)
    with pytest.raises(DriverError, match="base_url"):
        get_driver(Target(name="x", type="cloudrun", certs=[CertRef(id="a")]), env.settings)
    with pytest.raises(DriverError, match="nwa.base_url"):
        get_driver(Target(name="x", type="java_nwa", certs=[CertRef(id="a")]), env.settings)
