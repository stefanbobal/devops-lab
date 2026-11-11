"""Installer job: pick up signed certificates from the Jira tickets and install them.

    python -m cert_agent.installer --dry-run          # only report, change nothing
    python -m cert_agent.installer                    # all open tickets of the agent
    python -m cert_agent.installer --ticket CERT-12   # one ticket

A certificate is installed only if it passes the checks and, for targets that
need it, the ticket is in an approved status.

Progress goes to stderr with timestamps. The result is JSON on stdout.
The exit code is 1 if any ticket ended as failed or with an error,
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
from .workflow import WorkflowError, build_deps, check_ticket, install_ticket, process_open_tickets


def main() -> int:
    parser = argparse.ArgumentParser(description="Install signed certificates from Jira tickets.")
    parser.add_argument("--ticket", default="", help="only this ticket")
    parser.add_argument("--dry-run", action="store_true", help="check and report, install nothing, write nothing to Jira")
    args = parser.parse_args()

    started = time.monotonic()
    step("installer: loading configuration")
    deps = build_deps()
    if args.ticket:
        step(f"installer: ticket {args.ticket}" + (", dry run" if args.dry_run else ""))
        try:
            results = [check_ticket(deps, args.ticket, write=False) if args.dry_run else install_ticket(deps, args.ticket)]
        except WorkflowError as exc:
            step(f"installer: {exc}")
            results = [{"ticket": args.ticket, "state": "failed", "problems": [str(exc)]}]
    else:
        results = process_open_tickets(deps, args.dry_run)

    counts: dict[str, int] = {}
    for result in results:
        counts[result["state"]] = counts.get(result["state"], 0) + 1
    summary = ", ".join(f"{count} {state}" for state, count in sorted(counts.items())) or "no tickets"
    step(f"installer: finished in {time.monotonic() - started:.1f}s: {summary}")
    print(json.dumps(results, indent=2))
    return 1 if counts.get("failed") or counts.get("error") else 0


def run() -> int:
    try:
        return main()
    except (ConfigError, JiraError, WorkflowError) as exc:
        step(f"installer: stopped: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(run())
