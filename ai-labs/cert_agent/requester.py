"""Requester job: find certificates that expire soon and open a Jira ticket with a CSR.

    python -m cert_agent.requester --dry-run        # only report, change nothing
    python -m cert_agent.requester                  # all targets
    python -m cert_agent.requester --target NAME    # one target

Progress goes to stderr with timestamps. The result is JSON on stdout.
The exit code is 1 if any target or certificate ended with an error,
and 2 if the run could not start (configuration, Jira not reachable).
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from .config import ConfigError
from .jira_client import JiraError
from .log import step
from .workflow import WorkflowError, build_deps, scan_and_request


def main() -> int:
    parser = argparse.ArgumentParser(description="Request certificate renewals through Jira.")
    parser.add_argument("--target", default="", help="only this target from the inventory")
    parser.add_argument("--dry-run", action="store_true", help="discover and report, create no CSR and no ticket")
    args = parser.parse_args()

    started = time.monotonic()
    step("requester: loading configuration")
    deps = build_deps()
    step(f"requester: {len(deps.targets)} target(s) in the inventory" + (", dry run" if args.dry_run else ""))
    rows = scan_and_request(deps, args.target, args.dry_run)

    errors = [row for row in rows if row.get("error")]
    due = [row for row in rows if row.get("renewal_due")]
    step(
        f"requester: finished in {time.monotonic() - started:.1f}s: "
        f"{len(rows)} row(s), {len(due)} due for renewal, {len(errors)} error(s)"
    )
    print(json.dumps(rows, indent=2))
    return 1 if errors else 0


def run() -> int:
    try:
        return main()
    except (ConfigError, JiraError, WorkflowError) as exc:
        step(f"requester: stopped: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(run())
