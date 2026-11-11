"""Shared test helpers: a test CA, an in-memory Jira and a complete fake environment."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # the folder that contains cert_agent/

from cert_agent import certcheck, workflow  # noqa: E402
from cert_agent.config import Settings  # noqa: E402
from cert_agent.drivers.fake import FakeDriver  # noqa: E402
from cert_agent.models import CertRef, Target  # noqa: E402

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
HOST = "app.example.internal"


def new_key():
    return ec.generate_private_key(ec.SECP256R1())


def key_pem(key) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )


def x509_name(cn: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def make_csr(key, cn: str = HOST, names: list[str] | None = None) -> x509.CertificateSigningRequest:
    builder = x509.CertificateSigningRequestBuilder().subject_name(x509_name(cn))
    names = [cn] if names is None else names
    if names:
        builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName(n) for n in names]), critical=False)
    return builder.sign(key, hashes.SHA256())


class CA:
    def __init__(self, cn: str, issuer: "CA | None" = None, not_before=None, days: int = 3650, is_ca: bool = True):
        self.key = new_key()
        not_before = not_before or NOW - timedelta(days=365)
        signer_name = issuer.cert.subject if issuer else x509_name(cn)
        self.cert = (
            x509.CertificateBuilder()
            .subject_name(x509_name(cn))
            .issuer_name(signer_name)
            .public_key(self.key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(not_before)
            .not_valid_after(not_before + timedelta(days=days))
            .add_extension(x509.BasicConstraints(ca=is_ca, path_length=None), critical=True)
            .sign(issuer.key if issuer else self.key, hashes.SHA256())
        )

    def sign(self, csr, not_before=None, days: int = 365, names: list[str] | None = None, public_key=None):
        """Issue a certificate for a CSR. `names` and `public_key` let a test issue a wrong one."""
        not_before = not_before or NOW - timedelta(days=1)
        names = certcheck.dns_names(csr) if names is None else names
        builder = (
            x509.CertificateBuilder()
            .subject_name(csr.subject)
            .issuer_name(self.cert.subject)
            .public_key(public_key or csr.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(not_before)
            .not_valid_after(not_before + timedelta(days=days))
        )
        if names:
            builder = builder.add_extension(
                x509.SubjectAlternativeName([x509.DNSName(n) for n in names]), critical=False
            )
        return builder.sign(self.key, hashes.SHA256())


class FakeJira:
    """Keeps tickets in memory. Same methods as JiraClient."""

    def __init__(self):
        self.issues: dict[str, dict] = {}
        self.clock = 0

    def _stamp(self) -> str:
        self.clock += 1
        return f"2026-11-11T12:00:{self.clock:02d}.000+0000"

    def create_issue(self, project, issue_type, summary, description, labels):
        key = f"{project}-{len(self.issues) + 1}"
        self.issues[key] = {
            "key": key, "project": project, "summary": summary, "description": description,
            "status": "Open", "labels": list(labels), "attachments": [], "comments": [],
        }
        return key

    def find_open_issues(self, project, labels):
        return [
            self.get_issue(key)
            for key, issue in self.issues.items()
            if issue["project"] == project and set(labels) <= set(issue["labels"]) and issue["status"] != "Done"
        ]

    def get_issue(self, key):
        issue = self.issues[key]
        return {k: (list(v) if k == "labels" else v) for k, v in issue.items() if k in ("key", "project", "summary", "status", "labels")}

    def update_labels(self, key, add=(), remove=()):
        labels = self.issues[key]["labels"]
        for label in add:
            if label not in labels:
                labels.append(label)
        for label in remove:
            if label in labels:
                labels.remove(label)

    def transition(self, key, name):
        if name != "Done":
            return False
        self.issues[key]["status"] = "Done"
        return True

    def add_comment(self, key, body):
        self.issues[key]["comments"].append(body)

    def list_comments(self, key):
        return list(self.issues[key]["comments"])

    def add_attachment(self, key, filename, content):
        attachments = self.issues[key]["attachments"]
        item = {
            "id": str(1000 + sum(len(i["attachments"]) for i in self.issues.values())),
            "filename": filename, "size": len(content), "created": self._stamp(), "content": content,
        }
        attachments.append(item)
        return item

    def list_attachments(self, key):
        return list(self.issues[key]["attachments"])

    def download_attachment(self, attachment):
        return attachment["content"]

    # helpers for the tests
    def remove_attachment(self, key, filename):
        issue = self.issues[key]
        issue["attachments"] = [a for a in issue["attachments"] if a["filename"] != filename]

    def attachment(self, key, filename) -> bytes:
        return next(a["content"] for a in self.issues[key]["attachments"] if a["filename"] == filename)


class Env:
    """One fake target with a certificate that expires in 10 days, a fake Jira and a test CA."""

    def __init__(self, tmp_path: Path, approval_required: bool = True, endpoint: str = "", days_left: int = 10):
        self.root = CA("Test Root CA")
        self.issuing = CA("Test Issuing CA", issuer=self.root)
        self.rogue = CA("Rogue CA")
        self.jira = FakeJira()
        self.settings = Settings(
            jira_base_url="https://jira.invalid", jira_token="token", jira_project="CERT", hmac_key=b"k" * 32,
            inventory_path=tmp_path / "inventory.yaml", trusted_cas_path=tmp_path / "cas.pem",
            work_dir=tmp_path / "work", jira_done_transition="Done", verify_timeout=1, verify_interval=1,
        )
        self.target = Target(
            name="demo", type="fake", approval_required=approval_required, renew_days_before=30,
            certs=[CertRef(id="main", endpoint=endpoint)], options={"dir": str(tmp_path / "target")},
        )
        self.key = new_key()
        folder = tmp_path / "target" / "main"
        folder.mkdir(parents=True)
        first = self.issuing.sign(make_csr(self.key), not_before=NOW - timedelta(days=365 - days_left), days=365)
        (folder / "key.pem").write_bytes(key_pem(self.key))
        (folder / "cert.pem").write_text(certcheck.to_pem(first))
        self.first = first
        self.driver_class = FakeDriver
        self.deps = workflow.Deps(
            settings=self.settings, jira=self.jira, targets={"demo": self.target},
            trusted_roots=[self.root.cert], driver_factory=lambda target: self.driver_class(target, self.settings),
            now=lambda: NOW,
        )

    def installed(self) -> x509.Certificate:
        return FakeDriver(self.target, self.settings).current_certificate("main").certificate

    def open_ticket(self) -> str:
        return workflow.request_renewal(self.deps, "demo", "main")["ticket"]

    def csr(self, ticket: str) -> x509.CertificateSigningRequest:
        return certcheck.load_csr(self.jira.attachment(ticket, "demo_main.csr"))

    def attach_signed(self, ticket: str, cert: x509.Certificate, chain=None, filename: str = "signed.pem"):
        chain = [self.issuing.cert] if chain is None else chain
        data = "".join(certcheck.to_pem(c) for c in [cert, *chain]).encode()
        return self.jira.add_attachment(ticket, filename, data)

    def sign_and_attach(self, ticket: str, **kwargs) -> x509.Certificate:
        cert = self.issuing.sign(self.csr(ticket), **kwargs)
        self.attach_signed(ticket, cert)
        return cert

    def approve(self, ticket: str) -> None:
        self.jira.issues[ticket]["status"] = "Approved"

    def labels(self, ticket: str) -> list[str]:
        return self.jira.issues[ticket]["labels"]

    def comments(self, ticket: str) -> str:
        return "\n".join(self.jira.issues[ticket]["comments"])


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path)


@pytest.fixture
def make_env(tmp_path):
    return lambda **kwargs: Env(tmp_path, **kwargs)
