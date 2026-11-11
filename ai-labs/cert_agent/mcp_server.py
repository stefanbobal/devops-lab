"""MCP server: the renewal steps as tools for an agent.

    python -m cert_agent.mcp_server                           # stdio
    MCP_TRANSPORT=streamable-http python -m cert_agent.mcp_server   # HTTP on MCP_HOST:MCP_PORT

Five coarse tools. Each one runs the complete, checked step in code, so the model
cannot skip the validation or the approval. The server talks to Jira with the
technical user's token; the model never sees a credential or a private key.

Works with version 1 and version 2 of the `mcp` library.
"""
from __future__ import annotations

import os

try:
    from mcp.server.mcpserver import MCPServer  # mcp 2.x

    MCP_V2 = True
except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer  # mcp 1.x

    MCP_V2 = False

import functools

from . import workflow
from .config import ConfigError
from .drivers import DriverError
from .jira_client import JiraError

server = MCPServer("cert-agent")
_deps: workflow.Deps | None = None


def deps() -> workflow.Deps:
    global _deps
    if _deps is None:
        _deps = workflow.build_deps()
    return _deps


def report_errors(tool):
    """Return an expected problem as {"error": ...}, so the model can read the reason.
    (The mcp library hides the text of a raised exception in some versions.)"""

    @functools.wraps(tool)
    def wrapper(*args, **kwargs):
        try:
            return tool(*args, **kwargs)
        except (workflow.WorkflowError, JiraError, DriverError, ConfigError) as exc:
            return {"error": str(exc)}
        except KeyError as exc:
            return {"error": str(exc.args[0]) if exc.args else "not found"}

    return wrapper


@server.tool()
@report_errors
def list_certificates(target: str = "") -> dict:
    """List the certificates of all targets in the inventory, or of one target.

    Read-only. Each row has the target, the certificate id, the subject, the expiry
    date, the days left and whether a renewal is due.
    """
    return {"certificates": workflow.list_certificates(deps(), target)}


@server.tool()
@report_errors
def find_cert_tickets() -> dict:
    """List the open Jira tickets of the certificate agent with their status and labels.

    Read-only. The labels cert-validated, cert-installed and cert-failed show how far
    each renewal is.
    """
    project = deps().settings.jira_project
    return {"tickets": deps().jira.find_open_issues(project, [workflow.LABEL_AGENT])}


@server.tool()
@report_errors
def request_renewal(target: str, cert_id: str) -> dict:
    """Create a CSR on the target and open a Jira ticket with the CSR attached.

    If an open ticket for the same certificate already exists, that ticket is
    returned and nothing new is created.
    """
    return workflow.request_renewal(deps(), target, cert_id)


@server.tool()
@report_errors
def check_ticket(ticket: str) -> dict:
    """Check the signed certificate attached to a ticket. Installs nothing.

    Returns one state: waiting_for_certificate, rejected (with the reasons),
    waiting_for_approval, ready_to_install, installed or failed.
    """
    return workflow.check_ticket(deps(), ticket)


@server.tool()
@report_errors
def install_ticket(ticket: str) -> dict:
    """Install the signed certificate of a ticket on its target and verify it.

    Does nothing unless the certificate passes all checks and the ticket is
    approved. Approval is given by a person in Jira, never through this tool.
    """
    return workflow.install_ticket(deps(), ticket)


def main() -> None:
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "stdio":
        server.run()
        return
    host = os.environ.get("MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("MCP_PORT", "8000"))
    if MCP_V2:
        server.run(transport, host=host, port=port)
    else:
        server.settings.host = host
        server.settings.port = port
        server.run(transport)


if __name__ == "__main__":
    main()
