"""The whole renewal, end to end, against a fake target and an in-memory Jira."""
from datetime import timedelta

import json
import pytest

from cert_agent import certcheck, workflow
from cert_agent.certcheck import fingerprint
from cert_agent.drivers import DriverError, get_driver
from cert_agent.drivers.fake import FakeDriver
from cert_agent.models import CertRef, Target
from conftest import NOW, make_csr, new_key


# ---------------------------------------------------------------- the good path

def test_full_renewal(env):
    rows = workflow.scan_and_request(env.deps)
    assert rows[0]["days_left"] == 10 and rows[0]["action"] == "ticket created"
    ticket = rows[0]["ticket"]
    issue = env.jira.issues[ticket]
    assert {a["filename"] for a in issue["attachments"]} == {"demo_main.csr", workflow.META_FILE}
    assert certcheck.spki(env.csr(ticket)) == certcheck.spki(env.first)  # CSR is for the key on the target
    assert b"PRIVATE KEY" not in b"".join(a["content"] for a in issue["attachments"])

    assert workflow.check_ticket(env.deps, ticket)["state"] == "waiting_for_certificate"

    new = env.sign_and_attach(ticket)
    assert workflow.check_ticket(env.deps, ticket)["state"] == "waiting_for_approval"
    assert workflow.LABEL_VALIDATED in env.labels(ticket)

    assert workflow.install_ticket(env.deps, ticket)["state"] == "waiting_for_approval"
    assert env.installed() == env.first  # nothing installed without approval

    env.approve(ticket)
    result = workflow.install_ticket(env.deps, ticket)
    assert result["state"] == "installed"
    assert result["new_certificate"]["fingerprint_sha256"] == fingerprint(new)
    assert env.installed() == new
    assert workflow.LABEL_INSTALLED in env.labels(ticket) and workflow.LABEL_VALIDATED not in env.labels(ticket)
    assert issue["status"] == "Done"
    assert "Installed and verified" in env.comments(ticket)

    again = workflow.scan_and_request(env.deps)  # the new certificate is not due
    assert again[0]["action"] == "none" and len(env.jira.issues) == 1


def test_only_one_open_ticket_per_certificate(env):
    first = workflow.scan_and_request(env.deps)[0]
    second = workflow.scan_and_request(env.deps)[0]
    assert second["action"] == "ticket already open" and second["ticket"] == first["ticket"]
    assert len(env.jira.issues) == 1


def test_certificate_that_is_not_due_gets_no_ticket(make_env):
    env = make_env(days_left=200)
    assert workflow.scan_and_request(env.deps)[0]["action"] == "none"
    assert not env.jira.issues


def test_dry_runs_change_nothing(env):
    assert workflow.scan_and_request(env.deps, dry_run=True)[0]["action"] == "would request renewal"
    assert not env.jira.issues

    ticket = env.open_ticket()
    env.sign_and_attach(ticket)
    env.approve(ticket)
    before = json.dumps(env.jira.issues[ticket], default=repr)
    assert workflow.process_open_tickets(env.deps, dry_run=True)[0]["state"] == "ready_to_install"
    assert json.dumps(env.jira.issues[ticket], default=repr) == before
    assert env.installed() == env.first


def test_sandbox_target_installs_without_approval(make_env):
    env = make_env(approval_required=False)
    ticket = env.open_ticket()
    new = env.sign_and_attach(ticket)
    assert workflow.process_open_tickets(env.deps)[0]["state"] == "installed"
    assert env.installed() == new


def test_one_broken_target_or_certificate_does_not_stop_the_scan(env):
    env.deps.targets["broken"] = Target(name="broken", type="no-such-type", certs=env.target.certs)
    env.target.certs.insert(0, CertRef(id="missing"))  # listed in the inventory, not on the target
    env.deps.driver_factory = lambda target: get_driver(target, env.settings)
    rows = workflow.scan_and_request(env.deps, dry_run=True)
    assert rows[0]["cert_id"] == "missing" and "no certificate" in rows[0]["error"]
    assert rows[1]["action"] == "would request renewal"
    assert rows[2]["target"] == "broken" and "unknown type" in rows[2]["error"]
    assert ["error" in row for row in workflow.list_certificates(env.deps)] == [True, False, True]


# ---------------------------------------------------------------- bad certificates

def test_wrong_file_is_rejected_and_commented_once(env):
    ticket = env.open_ticket()
    env.attach_signed(ticket, env.issuing.sign(env.csr(ticket), public_key=new_key().public_key()))
    for _ in range(3):
        result = workflow.check_ticket(env.deps, ticket)
        assert result["state"] == "rejected" and "key of the CSR" in result["problems"][0]
    assert len(env.jira.issues[ticket]["comments"]) == 1
    env.approve(ticket)
    assert workflow.install_ticket(env.deps, ticket)["state"] == "rejected"
    assert env.installed() == env.first


@pytest.mark.parametrize(
    "make_cert, reason",
    [
        (lambda env, csr: env.rogue.sign(csr), "no issuing CA certificate"),
        (lambda env, csr: env.issuing.sign(csr, days=10), "expires too soon"),
        (lambda env, csr: env.issuing.sign(csr, names=["evil.example.internal"]), "is missing from the certificate"),
    ],
)
def test_untrusted_short_or_misnamed_certificate_is_rejected(env, make_cert, reason):
    ticket = env.open_ticket()
    env.attach_signed(ticket, make_cert(env, env.csr(ticket)))
    result = workflow.check_ticket(env.deps, ticket)
    assert result["state"] == "rejected" and reason in result["problems"][0]


def test_good_file_after_a_bad_one_is_accepted(env):
    ticket = env.open_ticket()
    env.jira.add_attachment(ticket, "readme.pem", b"this is not a certificate")
    assert workflow.check_ticket(env.deps, ticket)["state"] == "rejected"
    env.sign_and_attach(ticket)
    assert workflow.check_ticket(env.deps, ticket)["state"] == "waiting_for_approval"


# ---------------------------------------------------------------- tampering with the ticket

def test_changed_meta_file_stops_the_ticket(env):
    ticket = env.open_ticket()
    meta = json.loads(env.jira.attachment(ticket, workflow.META_FILE))
    meta["target"] = "another-target"
    env.jira.remove_attachment(ticket, workflow.META_FILE)
    env.jira.add_attachment(ticket, workflow.META_FILE, json.dumps(meta).encode())
    with pytest.raises(workflow.WorkflowError, match="was changed"):
        workflow.check_ticket(env.deps, ticket)
    assert workflow.process_open_tickets(env.deps)[0]["state"] == "failed"
    assert workflow.LABEL_FAILED in env.labels(ticket)


def test_second_meta_file_is_ignored(env):
    ticket = env.open_ticket()
    env.jira.add_attachment(ticket, workflow.META_FILE, b'{"target": "another-target"}')
    assert workflow.check_ticket(env.deps, ticket)["state"] == "waiting_for_certificate"


def test_replaced_csr_stops_the_ticket(env):
    ticket = env.open_ticket()
    env.jira.remove_attachment(ticket, "demo_main.csr")
    env.jira.add_attachment(ticket, "demo_main.csr", certcheck.to_pem(make_csr(new_key())).encode())
    with pytest.raises(workflow.WorkflowError, match="was changed"):
        workflow.check_ticket(env.deps, ticket)


def test_ticket_of_someone_else_is_refused(env):
    key = env.jira.create_issue("CERT", "Task", "unrelated", "", [])
    other = env.jira.create_issue("OTHER", "Task", "unrelated", "", [workflow.LABEL_AGENT])
    for ticket in (key, other):
        with pytest.raises(workflow.WorkflowError, match="not a ticket of the certificate agent"):
            workflow.install_ticket(env.deps, ticket)
    with pytest.raises(workflow.WorkflowError, match="not a Jira issue key"):
        workflow.check_ticket(env.deps, "CERT-1 OR 1=1")


# ---------------------------------------------------------------- failed installs

def ready_ticket(env):
    ticket = env.open_ticket()
    new = env.sign_and_attach(ticket)
    env.approve(ticket)
    return ticket, new


def test_install_error_marks_the_ticket_failed(env):
    class Broken(FakeDriver):
        def install(self, cert_id, leaf, chain):
            raise DriverError("target is down")

    ticket, _ = ready_ticket(env)
    env.driver_class = Broken
    result = workflow.install_ticket(env.deps, ticket)
    assert result["state"] == "failed" and "target is down" in result["problems"][0]
    assert "No rollback needed" in result["problems"][1]
    assert env.installed() == env.first
    assert workflow.LABEL_FAILED in env.labels(ticket) and env.jira.issues[ticket]["status"] == "Approved"

    env.driver_class = FakeDriver  # the agent does not retry until a person removes the label
    assert workflow.process_open_tickets(env.deps)[0]["state"] == "failed"
    assert env.installed() == env.first
    env.labels(ticket).remove(workflow.LABEL_FAILED)
    assert workflow.process_open_tickets(env.deps)[0]["state"] == "installed"


def test_new_certificate_not_served_is_rolled_back(make_env, monkeypatch):
    env = make_env(endpoint="demo.example.internal:443")
    old_fp = fingerprint(env.first)
    monkeypatch.setattr(workflow.tlscheck, "fetch_served_certificate", lambda endpoint: env.first)
    monkeypatch.setattr(workflow.tlscheck, "wait_until_served", lambda endpoint, fp, *a: fp == old_fp)

    ticket, _ = ready_ticket(env)
    result = workflow.install_ticket(env.deps, ticket)
    assert result["state"] == "failed"
    assert "does not serve the new certificate" in result["problems"][0]
    assert result["problems"][1] == "Rolled back to the old certificate."
    assert env.installed() == env.first
    assert "Rolled back" in env.comments(ticket)


def test_install_is_verified_through_the_endpoint(make_env, monkeypatch):
    env = make_env(endpoint="demo.example.internal:443")
    served = lambda endpoint: env.installed()  # the endpoint serves what is on the target
    monkeypatch.setattr(workflow.tlscheck, "fetch_served_certificate", served)
    monkeypatch.setattr(workflow.tlscheck, "wait_until_served", lambda endpoint, fp, *a: fingerprint(served(endpoint)) == fp)
    ticket, new = ready_ticket(env)
    assert workflow.install_ticket(env.deps, ticket)["state"] == "installed"
    assert env.installed() == new


def test_wrong_endpoint_in_inventory_blocks_the_install(make_env, monkeypatch):
    env = make_env(endpoint="proxy.example.internal:443")
    monkeypatch.setattr(workflow.tlscheck, "fetch_served_certificate", lambda endpoint: env.issuing.cert)
    ticket, _ = ready_ticket(env)
    result = workflow.install_ticket(env.deps, ticket)
    assert result["state"] == "failed" and "serves a different certificate" in result["problems"][0]
    assert env.installed() == env.first


def test_target_changed_after_the_request(env):
    ticket, _ = ready_ticket(env)
    renewed_by_hand = env.issuing.sign(env.csr(ticket), days=300)
    FakeDriver(env.target, env.settings).install("main", renewed_by_hand, [env.issuing.cert])
    result = workflow.install_ticket(env.deps, ticket)
    assert result["state"] == "failed" and "changed after this request" in result["problems"][0]
    assert env.installed() == renewed_by_hand


def test_certificate_that_is_already_on_the_target_closes_the_ticket(env):
    ticket, new = ready_ticket(env)
    FakeDriver(env.target, env.settings).install("main", new, [env.issuing.cert])
    assert workflow.install_ticket(env.deps, ticket)["state"] == "installed"
    assert "already has this certificate" in env.comments(ticket)


def test_certificate_that_expires_earlier_is_not_installed(env):
    env.settings.min_valid_days = 5
    ticket = env.open_ticket()
    # valid for 7 more days: passes the minimum, but the installed one still has 10
    env.attach_signed(ticket, env.issuing.sign(env.csr(ticket), not_before=NOW - timedelta(days=1), days=8))
    env.approve(ticket)
    result = workflow.install_ticket(env.deps, ticket)
    assert result["state"] == "failed" and "does not expire later" in result["problems"][0]
    assert env.installed() == env.first
