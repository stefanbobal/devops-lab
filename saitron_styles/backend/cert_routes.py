"""API for the Monitoring > URLs (S8) and Monitoring > Certificates (S7) panes - cert lifecycle Phase 3.

Read-only: rows come from Postgres only (``url_check``, ``cert_inventory``, ``pki_check_report``), written by
the ``url-check`` / ``cert-inventory`` / ``pki-check`` monitoring Jobs. Nothing here contacts SAP, the PKI or
any URL. The only action is starting those Jobs (admin, audited). Public certificate facts only - never a
key, password, PKCS12 or certificate file.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from . import cloudrun
from .auth import User, require_admin, require_user
from .config import get_settings
from .database import get_db
from .services import audit

logger = logging.getLogger("sapops.cert_routes")

router = APIRouter(prefix="/api", tags=["certificates"])

URL_PROFILE = "url-check"
CERT_PROFILE = "cert-inventory"
# url-check runs every 5 min: a row older than this is shown UNKNOWN, never with its last verdict.
URL_STALE_MINUTES = 15
TIER_ORDER = ("production", "preproduction", "simulation", "development", "sandbox", "service_zone",
              "infrastructure")
_URL_COLS = ("entry_id, sid, system, tier, category, kind, access, url, check_mode, verdict, http_status, "
             "latency_ms, error_type, checked_at, last_up_at, fail_count")
_JSON_COLS = ("flags", "compliance", "sans", "summary")


def _utc(v: Any) -> datetime | None:
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, str) and v:
        try:
            d = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return None
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    return None


def _iso(v: Any) -> Any:
    return v.isoformat() if hasattr(v, "isoformat") else v


def _rows(db: Session, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Rows as dicts with JSON columns decoded. A missing table (Job not run yet) = no rows."""
    try:
        res = db.execute(text(sql), params or {}).fetchall()
    except Exception as exc:  # noqa: BLE001 - tables are created by the Jobs
        db.rollback()
        logger.info("cert read skipped (%s)", type(exc).__name__)
        return []
    out = []
    for r in res:
        row = {}
        for k, v in r._mapping.items():
            if isinstance(v, str) and k in _JSON_COLS:
                try:
                    v = json.loads(v)
                except ValueError:
                    pass
            row[k] = v
        out.append(row)
    return out


def _tier_rank(tier: Any) -> int:
    t = str(tier or "").lower()
    return TIER_ORDER.index(t) if t in TIER_ORDER else len(TIER_ORDER)


def _job_name(profile: str) -> str:
    return f"{get_settings().monitor_job_prefix}-{profile}"


def _audit(db: Session, email: str, action: str, detail: str) -> None:
    try:
        audit(db, email, action, detail)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("cert audit %s not written (%s)", action, type(exc).__name__)


def _start_job(db: Session, user: User, profile: str, action: str) -> dict[str, Any]:
    job = _job_name(profile)
    try:
        result = cloudrun.run_job(get_settings(), job)
    except Exception as exc:  # noqa: BLE001
        reason = (f"HTTP {exc.response.status_code}" if isinstance(exc, httpx.HTTPStatusError)
                  else type(exc).__name__)
        logger.warning("%s Job start failed: %s", profile, reason)
        _audit(db, user.email, f"{action}_failed", f"job={job} error={reason}")
        raise HTTPException(status_code=502, detail=f"Could not start {job} ({reason})") from None
    _audit(db, user.email, action, f"job={job}")
    execution = (result.get("metadata") or {}).get("name") if isinstance(result, dict) else None
    return {"status": "started", "job": job, "execution": execution}


# --- S8: URLs ------------------------------------------------------------------------------
def _url_view(r: dict[str, Any], cert: dict[str, Any] | None, now: datetime) -> dict[str, Any]:
    checked = _utc(r.get("checked_at"))
    stale = checked is None or (now - checked) > timedelta(minutes=URL_STALE_MINUTES)
    verdict = r.get("verdict") or "UNKNOWN"
    if stale and r.get("check_mode") == "probe":
        verdict = "UNKNOWN"
    out = {k: _iso(r.get(k)) for k in ("entry_id", "sid", "system", "tier", "category", "kind", "access", "url",
                                       "check_mode", "http_status", "latency_ms", "error_type", "checked_at",
                                       "last_up_at", "fail_count")}
    out.update(verdict=verdict, last_verdict=r.get("verdict"), stale=bool(stale and r.get("check_mode") == "probe"))
    if cert:
        out.update(cert_days=cert.get("days_left"), cert_state=cert.get("state"), cert_flags=cert.get("flags") or [],
                   cert_checked_at=_iso(cert.get("checked_at")))
    else:
        out.update(cert_days=None, cert_state=None, cert_flags=[], cert_checked_at=None)
    return out


@router.get("/urls")
def urls_list(db: Session = Depends(get_db), user: User = Depends(require_user)) -> dict[str, Any]:
    """Every URL of the reviewed catalog with its last availability result and, where the URL has a
    certificate, the served certificate's days left from the daily ``cert-inventory`` scan."""
    now = datetime.now(timezone.utc)
    rows = _rows(db, f"SELECT {_URL_COLS} FROM url_check")
    certs = {c["entry_id"]: c for c in _rows(
        db, "SELECT entry_id, days_left, state, flags, checked_at FROM cert_inventory WHERE source = 'tls_scan'")}
    out = [_url_view(r, certs.get(r.get("entry_id")), now) for r in rows]
    out.sort(key=lambda r: (_tier_rank(r.get("tier")), str(r.get("sid") or r.get("system") or ""),
                            str(r.get("entry_id") or "")))
    checked = [r["checked_at"] for r in rows if r.get("checked_at")]
    return {"urls": out, "last_checked": _iso(max(checked)) if checked else None,
            "stale_minutes": URL_STALE_MINUTES, "job": _job_name(URL_PROFILE)}


@router.post("/urls/run", status_code=202)
def urls_run(db: Session = Depends(get_db), user: User = Depends(require_admin)) -> dict[str, Any]:
    """Start the ``url-check`` Job now (it also runs every 5 minutes on its own)."""
    return _start_job(db, user, URL_PROFILE, "urls_run")


# --- S7: Certificates ----------------------------------------------------------------------
CATEGORIES = ("sap_abap", "sap_java", "web_dispatcher", "bobj", "gclb", "non_sap")
DUE_STATES = ("WARN", "CRITICAL", "EXPIRED")
GREY_STATES = ("UNREACHABLE", "UNREADABLE", "UNKNOWN", "MISSING")
OUTLOOK_WEEKS = 13
OUTLOOK_RED_DAYS = 14
OUTLOOK_AMBER_DAYS = 30
_CERT_COLS = ("inventory_key, source, entry_id, sid, system, tier, category, endpoint, expected_ca, subject, sans, "
              "issuer, issuer_ca, not_after, days_left, key_profile, aid, state, flags, compliance, error_type, "
              "reason, checked_at, pse_context, pse_applic, pse_instance, pse_state, cert_role, list_date")
_TRUSTED_AGG = ("SELECT sid, pse_context, pse_applic, pse_instance, COUNT(*) AS total, "
                "SUM(CASE WHEN state = 'EXPIRED' THEN 1 ELSE 0 END) AS expired, "
                "SUM(CASE WHEN state IN ('WARN', 'CRITICAL') THEN 1 ELSE 0 END) AS expiring, "
                "SUM(CASE WHEN CAST(flags AS TEXT) LIKE '%LEGACY_CA_TRUSTED%' THEN 1 ELSE 0 END) AS legacy "
                "FROM cert_inventory WHERE cert_role = 'trusted' GROUP BY sid, pse_context, pse_applic, pse_instance")


def _cert_view(r: dict[str, Any]) -> dict[str, Any]:
    out = {k: _iso(v) for k, v in r.items()}
    out["flags"] = r.get("flags") if isinstance(r.get("flags"), list) else []
    out["compliance"] = r.get("compliance") if isinstance(r.get("compliance"), list) else []
    out["sans"] = r.get("sans") if isinstance(r.get("sans"), list) else []
    return out


def _pse_key(r: dict[str, Any]) -> tuple:
    return (r.get("sid"), r.get("pse_context"), r.get("pse_applic"), r.get("pse_instance"))


def outlook(rows: list[dict[str, Any]], weeks: int = OUTLOOK_WEEKS) -> list[dict[str, Any]]:
    """Certificates expiring per week for the next ``weeks`` weeks (week 0 includes already-expired
    ones still in use): red <= 14 days, amber <= 30, blue later."""
    buckets = [{"week": i, "red": 0, "amber": 0, "blue": 0} for i in range(weeks)]
    for r in rows:
        d = r.get("days_left")
        if not isinstance(d, int) or r.get("state") in GREY_STATES or d >= weeks * 7:
            continue
        b = buckets[max(0, d) // 7]
        b["red" if d <= OUTLOOK_RED_DAYS else "amber" if d <= OUTLOOK_AMBER_DAYS else "blue"] += 1
    return buckets


def summary(rows: list[dict[str, Any]], trusted: dict[tuple, dict[str, Any]]) -> dict[str, Any]:
    """Deterministic summary (until the AI insight of UI-4): counts per state and flag, the three
    certificates with the fewest days left. Grey states are never counted as healthy."""
    states: dict[str, int] = {}
    flags: dict[str, int] = {}
    for r in rows:
        if r.get("cert_role") == "list":
            continue
        states[r.get("state") or "UNKNOWN"] = states.get(r.get("state") or "UNKNOWN", 0) + 1
        for f in r.get("flags") or []:
            flags[f] = flags.get(f, 0) + 1
    ranked = sorted((r for r in rows if isinstance(r.get("days_left"), int) and r.get("state") not in GREY_STATES),
                    key=lambda r: r["days_left"])
    urgent = [{"key": r.get("inventory_key"), "sid": r.get("sid") or r.get("system"), "endpoint": r.get("endpoint"),
               "days_left": r.get("days_left"), "state": r.get("state")} for r in ranked[:3]]
    t_expired = sum(int(t.get("expired") or 0) for t in trusted.values())
    t_legacy = sum(int(t.get("legacy") or 0) for t in trusted.values())
    due = sum(states.get(s, 0) for s in DUE_STATES)
    unknown = sum(states.get(s, 0) for s in ("UNREACHABLE", "UNREADABLE", "UNKNOWN"))
    verdict = ("RED" if states.get("EXPIRED") or states.get("CRITICAL") else
               "AMBER" if due or flags.get("LEGACY_CA") or flags.get("WRONG_CA") or flags.get("DB_MISMATCH") else
               "UNKNOWN" if not states or unknown == sum(states.values()) else "GREEN")
    return {"verdict": verdict, "states": states, "flags": flags, "urgent": urgent, "due": due, "unknown": unknown,
            "trusted_expired": t_expired, "trusted_legacy": t_legacy}


def _pki_strip(db: Session) -> dict[str, Any] | None:
    rows = _rows(db, "SELECT summary, created_at FROM pki_check_report ORDER BY created_at DESC, report_id DESC LIMIT 1")
    if not rows:
        return None
    s = rows[0].get("summary") if isinstance(rows[0].get("summary"), dict) else {}
    return {"created_at": _iso(rows[0].get("created_at")), "p0": s.get("p0") or [], "p1": s.get("p1") or [],
            "p1_note": s.get("p1_note")}


@router.get("/certificates")
def certificates_list(category: str | None = None, tier: str | None = None, due: bool = False,
                      db: Session = Depends(get_db), user: User = Depends(require_user)) -> dict[str, Any]:
    """Own / served certificates (TLS scan, HANA SQL, STRUST own certificates and list status rows),
    per-PSE trusted-list counts, the 13-week outlook, a deterministic summary and the PKI strip."""
    if category and category not in CATEGORIES:
        raise HTTPException(status_code=400, detail="unknown category")
    if tier and tier.lower() not in TIER_ORDER:
        raise HTTPException(status_code=400, detail="unknown tier")
    rows = _rows(db, f"SELECT {_CERT_COLS} FROM cert_inventory WHERE COALESCE(cert_role, 'own') <> 'trusted'")
    trusted = {_pse_key(t): t for t in _rows(db, _TRUSTED_AGG)}
    out = []
    for r in rows:
        v = _cert_view(r)
        t = trusted.get(_pse_key(r)) if r.get("source") == "strust" else None
        v["trusted"] = ({"total": int(t.get("total") or 0), "expired": int(t.get("expired") or 0),
                         "expiring": int(t.get("expiring") or 0), "legacy": int(t.get("legacy") or 0)} if t else None)
        out.append(v)
    if category:
        out = [r for r in out if r.get("category") == category]
    if tier:
        out = [r for r in out if str(r.get("tier") or "").lower() == tier.lower()]
    if due:
        out = [r for r in out if r.get("state") in DUE_STATES]
    out.sort(key=lambda r: (_tier_rank(r.get("tier")), str(r.get("sid") or r.get("system") or ""),
                            r.get("days_left") if isinstance(r.get("days_left"), int) else 10 ** 6,
                            str(r.get("inventory_key") or "")))
    counts = {c: sum(1 for r in out if r.get("category") == c) for c in CATEGORIES}
    checked = [r["checked_at"] for r in rows if r.get("checked_at")]
    return {"certificates": out, "counts": counts, "outlook": outlook(out), "summary": summary(out, trusted),
            "pki": _pki_strip(db), "last_checked": _iso(max(checked)) if checked else None,
            "job": _job_name(CERT_PROFILE)}


@router.get("/certificates/item")
def certificate_item(key: str, db: Session = Depends(get_db), user: User = Depends(require_user)) -> dict[str, Any]:
    """One certificate (key as a query parameter - keys contain ':' and '/') plus, for a STRUST PSE,
    its full trusted list."""
    if not key or len(key) > 300:
        raise HTTPException(status_code=400, detail="invalid key")
    rows = _rows(db, f"SELECT {_CERT_COLS} FROM cert_inventory WHERE inventory_key = :k", {"k": key})
    if not rows:
        raise HTTPException(status_code=404, detail="certificate not found")
    item = _cert_view(rows[0])
    trusted: list[dict[str, Any]] = []
    if item.get("source") == "strust" and item.get("cert_role") == "own":
        trusted = [_cert_view(t) for t in _rows(
            db, f"SELECT {_CERT_COLS} FROM cert_inventory WHERE cert_role = 'trusted' AND sid = :s "
                "AND pse_context = :c AND pse_applic = :a AND COALESCE(pse_instance, '') = :i "
                "ORDER BY days_left NULLS LAST, subject",
            {"s": item.get("sid"), "c": item.get("pse_context"), "a": item.get("pse_applic"),
             "i": item.get("pse_instance") or ""})]
    return {"certificate": item, "trusted": trusted}


@router.post("/certificates/run", status_code=202)
def certificates_run(db: Session = Depends(get_db), user: User = Depends(require_admin)) -> dict[str, Any]:
    """Start the ``cert-inventory`` Job now (TLS scan + HANA + STRUST; it also runs daily at 05:45)."""
    return _start_job(db, user, CERT_PROFILE, "certificates_run")
