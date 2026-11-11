"""Settings from environment variables, and the target inventory from YAML."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from .models import CertRef, Target

HERE = Path(__file__).resolve().parent
TARGET_KEYS = {"name", "type", "environment", "approval_required", "renew_days_before", "certs"}


class ConfigError(RuntimeError):
    pass


@dataclass
class Settings:
    jira_base_url: str
    jira_token: str
    jira_project: str
    hmac_key: bytes
    inventory_path: Path
    trusted_cas_path: Path
    work_dir: Path
    jira_issue_type: str = "Task"
    jira_approved_statuses: tuple[str, ...] = ("Approved",)
    jira_done_transition: str = ""
    jira_ca_bundle: str = ""
    min_valid_days: int = 30
    verify_timeout: int = 300
    verify_interval: int = 15

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv()
        required = ["JIRA_BASE_URL", "JIRA_TOKEN", "JIRA_PROJECT", "CERT_AGENT_HMAC_KEY", "CERT_AGENT_TRUSTED_CAS"]
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            raise ConfigError("missing environment variables: " + ", ".join(missing))
        statuses = os.environ.get("JIRA_APPROVED_STATUSES", "Approved")
        return cls(
            jira_base_url=os.environ["JIRA_BASE_URL"].rstrip("/"),
            jira_token=os.environ["JIRA_TOKEN"],
            jira_project=os.environ["JIRA_PROJECT"],
            hmac_key=os.environ["CERT_AGENT_HMAC_KEY"].encode(),
            inventory_path=_path(os.environ.get("CERT_AGENT_INVENTORY", "inventory.yaml")),
            trusted_cas_path=_path(os.environ["CERT_AGENT_TRUSTED_CAS"]),
            work_dir=_path(os.environ.get("CERT_AGENT_WORK_DIR", "results")),
            jira_issue_type=os.environ.get("JIRA_ISSUE_TYPE", "Task"),
            jira_approved_statuses=tuple(s.strip() for s in statuses.split(",") if s.strip()),
            jira_done_transition=os.environ.get("JIRA_DONE_TRANSITION", ""),
            jira_ca_bundle=os.environ.get("JIRA_CA_BUNDLE", ""),
            min_valid_days=int(os.environ.get("CERT_AGENT_MIN_VALID_DAYS", "30")),
            verify_timeout=int(os.environ.get("CERT_AGENT_VERIFY_TIMEOUT", "300")),
            verify_interval=int(os.environ.get("CERT_AGENT_VERIFY_INTERVAL", "15")),
        )


def _path(value: str) -> Path:
    """Relative paths are relative to this folder, wherever the job is started from."""
    path = Path(value).expanduser()
    return path if path.is_absolute() else HERE / path


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(HERE / ".env")


def load_inventory(path: Path) -> dict[str, Target]:
    """Read the inventory file. Returns the targets by name."""
    if not Path(path).exists():
        raise ConfigError(f"inventory file not found: {path}")
    data = yaml.safe_load(Path(path).read_text()) or {}
    defaults = data.get("defaults") or {}
    targets: dict[str, Target] = {}
    for raw in data.get("targets") or []:
        for key in ("name", "type"):
            if not raw.get(key):
                raise ConfigError(f"inventory: a target has no {key!r}: {raw}")
        name = raw["name"]
        if name in targets:
            raise ConfigError(f"inventory: target name {name!r} is used twice")
        certs = [
            CertRef(
                id=str(item["id"]),
                endpoint=str(item.get("endpoint") or ""),
                names=tuple(str(n).lower() for n in item.get("names") or ()),
            )
            for item in raw.get("certs") or []
        ]
        if not certs:
            raise ConfigError(f"inventory: target {name!r} lists no certificates")
        targets[name] = Target(
            name=name,
            type=raw["type"],
            environment=raw.get("environment", defaults.get("environment", "sandbox")),
            approval_required=bool(raw.get("approval_required", defaults.get("approval_required", True))),
            renew_days_before=int(raw.get("renew_days_before", defaults.get("renew_days_before", 30))),
            certs=certs,
            options={k: v for k, v in raw.items() if k not in TARGET_KEYS},
        )
    if not targets:
        raise ConfigError(f"inventory {path} contains no targets")
    return targets
