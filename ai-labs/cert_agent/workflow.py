"""The renewal workflow. Every safety check lives here, not in the caller.

Requester side: list_certificates, request_renewal, scan_and_request.
Installer side: check_ticket, install_ticket, process_open_tickets.

The Jira ticket is the state of record. The agent keeps its own state in labels:
cert-agent (ours), cert-fp-<fingerprint> (which certificate), cert-validated,
cert-installed, cert-failed (a human must look).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from cryptography import x509

from . import certcheck, tlscheck
from .certcheck import ValidationResult, fingerprint, spki
from .config import Settings, load_inventory
from .drivers import Driver, get_driver
from .jira_client import ISSUE_KEY, JiraClient
from .log import step, timed
from .models import CertInfo, CertRef, Target

LABEL_AGENT = "cert-agent"
LABEL_VALIDATED = "cert-validated"
LABEL_INSTALLED = "cert-installed"
LABEL_FAILED = "cert-failed"
META_FILE = "cert-agent-meta.json"
CERT_EXTENSIONS = (".crt", ".cer", ".pem", ".p7b", ".p7c", ".der")
MAX_CERT_FILE = 200_000
MARK = "[cert-agent]"


class WorkflowError(RuntimeError):
    pass


@dataclass
class Deps:
    """Everything the workflow needs from outside. Tests pass in stand-ins."""

    settings: Settings
    jira: Any
    targets: dict[str, Target]
    trusted_roots: list[x509.Certificate]
    driver_factory: Callable[[Target], Driver]
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)


def build_deps() -> Deps:
    settings = Settings.from_env()
    return Deps(
        settings=settings,
        jira=JiraClient(settings.jira_base_url, settings.jira_token, verify=settings.jira_ca_bundle or True),
        targets=load_inventory(settings.inventory_path),
        trusted_roots=certcheck.load_certificates(settings.trusted_cas_path.read_bytes()),
        driver_factory=lambda target: get_driver(target, settings),
    )


# ================================================================ requester side

def _targets(deps: Deps, target_name: str = "") -> list[Target]:
    if not target_name:
        return list(deps.targets.values())
    if target_name not in deps.targets:
        raise WorkflowError(f"unknown target {target_name!r}; known: {', '.join(sorted(deps.targets))}")
    return [deps.targets[target_name]]


def _describe(info: CertInfo, target: Target, now: datetime) -> dict:
    cert = info.certificate
    days_left = info.days_left(now)
    return {
        "target": target.name,
        "cert_id": info.cert_id,
        "subject": certcheck.subject(cert),
        "dns_names": certcheck.dns_names(cert),
        "issuer": cert.issuer.rfc4514_string(),
        "not_after": f"{cert.not_valid_after_utc:%Y-%m-%d}",
        "days_left": days_left,
        "renewal_due": days_left <= target.renew_days_before,
        "fingerprint_sha256": fingerprint(cert),
    }


def _discover(deps: Deps, target: Target) -> tuple[Driver | None, list[CertInfo | dict]]:
    """Read every certificate the inventory lists for a target. A certificate or a
    whole target that cannot be read becomes an error row and does not stop the rest."""
    try:
        driver = deps.driver_factory(target)
    except Exception as exc:
        step(f"{target.name}: cannot be reached: {exc}")
        return None, [{"target": target.name, "error": str(exc)}]
    found: list[CertInfo | dict] = []
    for ref in target.certs:
        try:
            with timed(f"{target.name}/{ref.id}: reading the installed certificate ({target.type})"):
                found.append(driver.current_certificate(ref.id))
        except Exception as exc:
            found.append({"target": target.name, "cert_id": ref.id, "error": str(exc)})
    return driver, found


def list_certificates(deps: Deps, target_name: str = "") -> list[dict]:
    """Read-only: the certificates of all targets (or one) with their expiry."""
    rows: list[dict] = []
    for target in _targets(deps, target_name):
        _, found = _discover(deps, target)
        rows.extend(item if isinstance(item, dict) else _describe(item, target, deps.now()) for item in found)
    return rows


def _meta_mac(key: bytes, meta: dict) -> str:
    body = json.dumps({k: v for k, v in meta.items() if k != "mac"}, sort_keys=True, separators=(",", ":"))
    return hmac.new(key, body.encode(), hashlib.sha256).hexdigest()


def request_renewal(deps: Deps, target_name: str, cert_id: str, driver: Driver | None = None) -> dict:
    """Create the CSR on the target and open a Jira ticket with it. Never opens a second
    ticket for the same certificate while one is still open."""
    target = _targets(deps, target_name)[0]
    ref = target.cert(cert_id)
    driver = driver or deps.driver_factory(target)
    current = driver.current_certificate(cert_id).certificate
    old_fp = fingerprint(current)
    fp_label = f"cert-fp-{old_fp[:16]}"

    project = deps.settings.jira_project
    existing = deps.jira.find_open_issues(project, [LABEL_AGENT, fp_label])
    if existing:
        step(f"{target.name}/{cert_id}: open ticket {existing[0]['key']} already exists")
        return {"ticket": existing[0]["key"], "created": False}

    with timed(f"{target.name}/{cert_id}: creating the CSR on the target"):
        csr = certcheck.load_csr(driver.create_csr(cert_id).encode())
    if not csr.is_signature_valid:
        raise WorkflowError("the target returned a CSR with an invalid signature")
    if driver.key_reuse and spki(csr) != spki(current):
        raise WorkflowError("the CSR does not use the key of the installed certificate; wrong PSE or entry?")
    csr_pem = certcheck.to_pem(csr).encode()

    csr_file = re.sub(r"[^A-Za-z0-9._-]+", "_", f"{target.name}_{cert_id}") + ".csr"
    meta = {
        "version": 1,
        "target": target.name,
        "cert_id": cert_id,
        "old_fingerprint_sha256": old_fp,
        "csr_filename": csr_file,
        "csr_sha256": hashlib.sha256(csr_pem).hexdigest(),
        "created": f"{deps.now():%Y-%m-%dT%H:%M:%SZ}",
    }
    meta["mac"] = _meta_mac(deps.settings.hmac_key, meta)

    names = certcheck.required_names(csr, ref.names)
    summary = f"Certificate renewal: {target.name} / {cert_id} (expires {current.not_valid_after_utc:%Y-%m-%d})"
    description = "\n".join(
        [
            "Certificate renewal request, created by the certificate agent.",
            "",
            f"* Target: {target.name} ({target.type}, {target.environment})",
            f"* Certificate: {cert_id}",
            f"* Subject: {certcheck.subject(csr)}",
            f"* DNS names: {', '.join(names) or 'none'}",
            f"* Current certificate expires: {current.not_valid_after_utc:%Y-%m-%d}",
            f"* Current certificate SHA-256: {old_fp}",
            "",
            f"Please sign the attached request {csr_file} and attach the signed certificate "
            "with its CA chain to this ticket (PEM, DER or P7B).",
            f"Do not change or remove {csr_file} and {META_FILE}; the agent checks them.",
        ]
    )
    with timed(f"{target.name}/{cert_id}: creating the Jira ticket"):
        key = deps.jira.create_issue(project, deps.settings.jira_issue_type, summary, description, [LABEL_AGENT, fp_label])
    try:
        deps.jira.add_attachment(key, csr_file, csr_pem)
        deps.jira.add_attachment(key, META_FILE, json.dumps(meta, indent=2).encode())
    except Exception as exc:
        _fail(deps, key, [f"The ticket was created but the files could not be attached: {exc}"])
        raise
    step(f"{target.name}/{cert_id}: ticket {key} created with {csr_file}")
    return {"ticket": key, "created": True}


def scan_and_request(deps: Deps, target_name: str = "", dry_run: bool = False) -> list[dict]:
    """The requester run: discover everything and request a renewal where one is due."""
    rows: list[dict] = []
    for target in _targets(deps, target_name):
        driver, found = _discover(deps, target)
        for info in found:
            if isinstance(info, dict):
                rows.append(info)
                continue
            row = _describe(info, target, deps.now())
            if not row["renewal_due"]:
                row["action"] = "none"
            elif dry_run:
                row["action"] = "would request renewal"
            else:
                try:
                    result = request_renewal(deps, target.name, info.cert_id, driver=driver)
                    row["ticket"] = result["ticket"]
                    row["action"] = "ticket created" if result["created"] else "ticket already open"
                except Exception as exc:
                    row["error"] = str(exc)
            outcome = row.get("error") or row["action"]
            step(f"{target.name}/{info.cert_id}: {row['days_left']} day(s) left, {outcome}")
            rows.append(row)
    return rows


# ================================================================ installer side

@dataclass
class Evaluation:
    ticket: str
    state: str = ""
    target: Target | None = None
    ref: CertRef | None = None
    meta: dict = field(default_factory=dict)
    validation: ValidationResult | None = None
    problems: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        data: dict = {"ticket": self.ticket, "state": self.state}
        if self.target:
            data["target"] = self.target.name
            data["cert_id"] = self.meta.get("cert_id", "")
        if self.validation and self.validation.leaf is not None:
            leaf = self.validation.leaf
            data["new_certificate"] = {
                "subject": certcheck.subject(leaf),
                "not_after": f"{leaf.not_valid_after_utc:%Y-%m-%d}",
                "fingerprint_sha256": fingerprint(leaf),
            }
        if self.problems:
            data["problems"] = self.problems
        return data


def _load_context(deps: Deps, key: str) -> tuple[dict, Evaluation, x509.CertificateSigningRequest, list[dict]]:
    """Read the ticket and prove that it is one of ours and was not tampered with."""
    if not ISSUE_KEY.match(key):
        raise WorkflowError(f"not a Jira issue key: {key!r}")
    issue = deps.jira.get_issue(key)
    if issue["project"] != deps.settings.jira_project or LABEL_AGENT not in issue["labels"]:
        raise WorkflowError(f"{key} is not a ticket of the certificate agent")

    attachments = deps.jira.list_attachments(key)
    # Oldest wins: the agent attached its two files first, a later file with the same name is ignored.
    by_name = {a["filename"]: a for a in sorted(attachments, key=lambda a: a["created"], reverse=True)}
    if META_FILE not in by_name:
        raise WorkflowError(f"{key}: the file {META_FILE} is missing")
    try:
        meta = json.loads(deps.jira.download_attachment(by_name[META_FILE]))
        mac_ok = hmac.compare_digest(str(meta.get("mac", "")), _meta_mac(deps.settings.hmac_key, meta))
    except (ValueError, AttributeError):
        mac_ok = False
    if not mac_ok:
        raise WorkflowError(f"{key}: {META_FILE} was changed or was not written by this agent")

    csr_att = by_name.get(meta["csr_filename"])
    if csr_att is None:
        raise WorkflowError(f"{key}: the request file {meta['csr_filename']} is missing")
    csr_bytes = deps.jira.download_attachment(csr_att)
    if hashlib.sha256(csr_bytes).hexdigest() != meta["csr_sha256"]:
        raise WorkflowError(f"{key}: the request file {meta['csr_filename']} was changed")

    if meta["target"] not in deps.targets:
        raise WorkflowError(f"{key}: target {meta['target']!r} is no longer in the inventory")
    target = deps.targets[meta["target"]]
    try:
        ref = target.cert(meta["cert_id"])
    except KeyError as exc:
        raise WorkflowError(f"{key}: {exc.args[0]}") from exc
    return issue, Evaluation(ticket=key, target=target, ref=ref, meta=meta), certcheck.load_csr(csr_bytes), attachments


def _find_signed(deps: Deps, ev: Evaluation, csr, attachments: list[dict], write: bool):
    """Look for an attachment that is a valid answer to the CSR. Newest file first."""
    candidates = [
        a for a in attachments if a["filename"].lower().endswith(CERT_EXTENSIONS) and a["filename"] != META_FILE
    ]
    candidates.sort(key=lambda a: a["created"], reverse=True)
    if not candidates:
        return None, []
    comments = deps.jira.list_comments(ev.ticket) if write else []
    rejected: list[str] = []
    for att in candidates:
        if att["size"] > MAX_CERT_FILE:
            problems = ["the file is too large to be a certificate"]
        else:
            try:
                certs = certcheck.load_certificates(deps.jira.download_attachment(att))
            except ValueError as exc:
                problems = [str(exc)]
            else:
                result = certcheck.validate(
                    csr,
                    certs,
                    deps.trusted_roots,
                    now=deps.now(),
                    min_valid_days=deps.settings.min_valid_days,
                    extra_names=ev.ref.names,
                )
                if result.ok:
                    return result, []
                problems = result.problems
        rejected.append(f"{att['filename']}: " + "; ".join(problems))
        marker = f"{MARK} attachment {att['id']} rejected"
        if write and not any(marker in comment for comment in comments):  # comment on each file only once
            step(f"{ev.ticket}: rejected {att['filename']}: {'; '.join(problems)}")
            lines = [f"{marker}: {att['filename']} cannot be installed."] + [f"* {p}" for p in problems]
            deps.jira.add_comment(ev.ticket, "\n".join(lines))
    return None, rejected


def _evaluate(deps: Deps, key: str, write: bool = True) -> Evaluation:
    issue, ev, csr, attachments = _load_context(deps, key)
    if LABEL_INSTALLED in issue["labels"]:
        ev.state = "installed"
        return ev
    if LABEL_FAILED in issue["labels"]:
        ev.state = "failed"
        ev.problems = [f"a person must look at the ticket and remove the label {LABEL_FAILED} to retry"]
        return ev

    ev.validation, ev.problems = _find_signed(deps, ev, csr, attachments, write)
    if ev.validation is None:
        ev.state = "rejected" if ev.problems else "waiting_for_certificate"
        return ev

    approved_statuses = {status.lower() for status in deps.settings.jira_approved_statuses}
    approved = not ev.target.approval_required or issue["status"].lower() in approved_statuses
    ev.state = "ready_to_install" if approved else "waiting_for_approval"

    if write and LABEL_VALIDATED not in issue["labels"]:
        leaf = ev.validation.leaf
        lines = [
            f"{MARK} The signed certificate passed all checks.",
            f"* Subject: {certcheck.subject(leaf)}",
            f"* DNS names: {', '.join(certcheck.dns_names(leaf)) or 'none'}",
            f"* Issuer: {leaf.issuer.rfc4514_string()}",
            f"* Valid until: {leaf.not_valid_after_utc:%Y-%m-%d}",
            f"* SHA-256: {fingerprint(leaf)}",
        ]
        if ev.target.approval_required:
            statuses = " or ".join(deps.settings.jira_approved_statuses)
            lines.append(f"The install on {ev.target.name} starts after this ticket is moved to: {statuses}.")
        else:
            lines.append(f"{ev.target.name} needs no approval; the install starts on the next installer run.")
        deps.jira.update_labels(key, add=[LABEL_VALIDATED])
        deps.jira.add_comment(key, "\n".join(lines))
        step(f"{key}: signed certificate validated")
    return ev


def check_ticket(deps: Deps, key: str, write: bool = True) -> dict:
    """Validate what is attached to the ticket. Never installs anything."""
    return _evaluate(deps, key, write).as_dict()


def _fail(deps: Deps, key: str, problems: list[str], driver: Driver | None = None) -> None:
    step(f"{key}: FAILED: {' '.join(problems)}")
    lines = [f"{MARK} Stopped. A person must look at this ticket."] + [f"* {p}" for p in problems]
    lines.append(f"Remove the label {LABEL_FAILED} to let the agent try again.")
    try:
        deps.jira.update_labels(key, add=[LABEL_FAILED])
        deps.jira.add_comment(key, "\n".join(lines))
        _attach_evidence(deps, key, driver)
    except Exception as exc:  # the failure itself must still be reported to the caller
        step(f"{key}: could not write the failure to Jira: {exc}")


def _attach_evidence(deps: Deps, key: str, driver: Driver | None) -> None:
    for path in driver.evidence if driver else []:
        try:
            deps.jira.add_attachment(key, path.name, path.read_bytes())
        except Exception as exc:
            step(f"{key}: could not attach {path.name}: {exc}")


def _verify(deps: Deps, driver: Driver, ref: CertRef, expected_fp: str) -> bool:
    """True when the target really has the expected certificate."""
    if ref.endpoint:
        return tlscheck.wait_until_served(
            ref.endpoint, expected_fp, deps.settings.verify_timeout, deps.settings.verify_interval
        )
    return fingerprint(driver.current_certificate(ref.id).certificate) == expected_fp


def _rollback(deps: Deps, driver: Driver, ref: CertRef, old: x509.Certificate, chain: list) -> str:
    old_fp = fingerprint(old)
    try:
        if fingerprint(driver.current_certificate(ref.id).certificate) == old_fp:
            return "No rollback needed: the target still has the old certificate."
        step(f"{driver.target.name}/{ref.id}: rolling back to the old certificate")
        driver.rollback(ref.id, old, chain)
        if _verify(deps, driver, ref, old_fp):
            return "Rolled back to the old certificate."
        return "A rollback was sent, but the old certificate is not active yet. Check the target by hand."
    except NotImplementedError:
        return "Automatic rollback is not available for this target type. Roll back by hand."
    except Exception as exc:
        return f"The rollback failed ({exc}). Check the target by hand."


def install_ticket(deps: Deps, key: str) -> dict:
    """Install the signed certificate of a ticket, if it is valid and approved."""
    ev = _evaluate(deps, key)
    if ev.state != "ready_to_install":
        step(f"{key}: {ev.state}, nothing to install")
        return ev.as_dict()

    target, ref, leaf, chain = ev.target, ev.ref, ev.validation.leaf, ev.validation.chain
    new_fp = fingerprint(leaf)
    driver = deps.driver_factory(target)

    def failed(problems: list[str]) -> dict:
        _fail(deps, key, problems, driver)
        ev.state, ev.problems = "failed", problems
        return ev.as_dict()

    def installed(note: str) -> dict:
        deps.jira.update_labels(key, add=[LABEL_INSTALLED], remove=[LABEL_VALIDATED])
        lines = [f"{MARK} {note}", f"* Valid until: {leaf.not_valid_after_utc:%Y-%m-%d}", f"* SHA-256: {new_fp}"]
        deps.jira.add_comment(key, "\n".join(lines))
        _attach_evidence(deps, key, driver)
        step(f"{key}: {note}")
        done = deps.settings.jira_done_transition
        if done:  # closing the ticket is a convenience; the install is already recorded above
            try:
                closed = deps.jira.transition(key, done)
            except Exception as exc:
                step(f"{key}: transition {done!r} failed: {exc}")
                closed = False
            if not closed:
                deps.jira.add_comment(key, f"{MARK} The transition {done!r} could not be run, so the ticket stays open.")
        ev.state = "installed"
        return ev.as_dict()

    # ---- checks against the live target, before anything is changed
    try:
        current = driver.current_certificate(ref.id).certificate
    except Exception as exc:
        return failed([f"The current certificate of {target.name}/{ref.id} cannot be read: {exc}"])
    old_fp = fingerprint(current)
    if old_fp == new_fp:
        return installed(f"{target.name}/{ref.id} already has this certificate.")
    problems = []
    if old_fp != ev.meta["old_fingerprint_sha256"]:
        problems.append("The certificate on the target changed after this request was created.")
    if driver.key_reuse and spki(leaf) != spki(current):
        problems.append("The new certificate does not belong to the key that is on the target.")
    if leaf.not_valid_after_utc <= current.not_valid_after_utc:
        problems.append("The new certificate does not expire later than the installed one.")
    if ref.endpoint:
        try:
            if fingerprint(tlscheck.fetch_served_certificate(ref.endpoint)) != old_fp:
                problems.append(
                    f"The endpoint {ref.endpoint} serves a different certificate than the target reports. "
                    "Correct the endpoint in the inventory, otherwise the install cannot be verified."
                )
        except OSError as exc:
            problems.append(f"The endpoint {ref.endpoint} cannot be reached, so the install could not be verified: {exc}")
    if problems:
        return failed(problems)

    # ---- install, verify, roll back if the new certificate is not active
    error = ""
    try:
        with timed(f"{key}: installing on {target.name}/{ref.id}"):
            driver.install(ref.id, leaf, chain)
    except Exception as exc:
        error = f"The install failed: {exc}"
    if not error:
        try:
            with timed(f"{key}: verifying {target.name}/{ref.id}"):
                if not _verify(deps, driver, ref, new_fp):
                    error = "After the install the target does not serve the new certificate."
        except Exception as exc:
            error = f"The install could not be verified: {exc}"
    if error:
        return failed([error, _rollback(deps, driver, ref, current, chain)])
    return installed(f"Installed and verified on {target.name}/{ref.id}.")


def process_open_tickets(deps: Deps, dry_run: bool = False) -> list[dict]:
    """The installer run: go through all open tickets of the agent."""
    issues = deps.jira.find_open_issues(deps.settings.jira_project, [LABEL_AGENT])
    step(f"{len(issues)} open certificate ticket(s)")
    results: list[dict] = []
    for number, issue in enumerate(issues, 1):
        key = issue["key"]
        step(f"ticket {number}/{len(issues)}: {key}")
        finished = next((label for label in (LABEL_INSTALLED, LABEL_FAILED) if label in issue["labels"]), "")
        if finished:  # nothing left for the agent to do; a person closes or reopens it
            step(f"{key}: has the label {finished}, skipped")
            results.append({"ticket": key, "state": finished.removeprefix("cert-")})
            continue
        try:
            result = check_ticket(deps, key, write=False) if dry_run else install_ticket(deps, key)
        except WorkflowError as exc:  # the ticket itself is broken or was tampered with
            if not dry_run and LABEL_FAILED not in issue["labels"]:
                _fail(deps, key, [str(exc)])
            result = {"ticket": key, "state": "failed", "problems": [str(exc)]}
        except Exception as exc:  # Jira or network trouble: try again on the next run
            step(f"{key}: error: {exc}")
            result = {"ticket": key, "state": "error", "problems": [str(exc)]}
        results.append(result)
    return results
