"""The MCP server's tool list, the tools themselves, and the settings from the environment."""
import asyncio

import pytest

from cert_agent.config import ConfigError, Settings

REQUIRED = {
    "JIRA_BASE_URL": "https://jira.example.internal/", "JIRA_TOKEN": "t", "JIRA_PROJECT": "CERT",
    "CERT_AGENT_HMAC_KEY": "secret", "CERT_AGENT_TRUSTED_CAS": "/etc/ssl/cas.pem",
}
ALL = list(REQUIRED) + [
    "JIRA_APPROVED_STATUSES", "JIRA_DONE_TRANSITION", "JIRA_ISSUE_TYPE", "JIRA_CA_BUNDLE",
    "CERT_AGENT_INVENTORY", "CERT_AGENT_WORK_DIR", "CERT_AGENT_MIN_VALID_DAYS",
    "CERT_AGENT_VERIFY_TIMEOUT", "CERT_AGENT_VERIFY_INTERVAL",
]


@pytest.fixture
def clean_env(monkeypatch):
    monkeypatch.setattr("cert_agent.config._load_dotenv", lambda: None)
    for name in ALL:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_settings_from_environment(clean_env):
    for name, value in REQUIRED.items():
        clean_env.setenv(name, value)
    clean_env.setenv("JIRA_APPROVED_STATUSES", "Approved, Ready for install")
    settings = Settings.from_env()
    assert settings.jira_base_url == "https://jira.example.internal"
    assert settings.jira_approved_statuses == ("Approved", "Ready for install")
    assert settings.hmac_key == b"secret" and settings.min_valid_days == 30
    assert str(settings.trusted_cas_path) == "/etc/ssl/cas.pem"
    assert settings.inventory_path.name == "inventory.yaml" and settings.inventory_path.is_absolute()


def test_missing_settings_are_all_named(clean_env):
    clean_env.setenv("JIRA_PROJECT", "CERT")
    with pytest.raises(ConfigError) as error:
        Settings.from_env()
    for name in ("JIRA_BASE_URL", "JIRA_TOKEN", "CERT_AGENT_HMAC_KEY", "CERT_AGENT_TRUSTED_CAS"):
        assert name in str(error.value)


def test_mcp_server_offers_the_five_tools_and_they_work(env, monkeypatch):
    pytest.importorskip("mcp")
    from cert_agent import mcp_server

    tools = asyncio.run(mcp_server.server.list_tools())
    assert sorted(tool.name for tool in tools) == [
        "check_ticket", "find_cert_tickets", "install_ticket", "list_certificates", "request_renewal",
    ]
    assert all(tool.description for tool in tools)

    monkeypatch.setattr(mcp_server, "_deps", env.deps)
    listed = mcp_server.list_certificates("")["certificates"]
    assert listed[0]["target"] == "demo" and listed[0]["renewal_due"] is True

    ticket = mcp_server.request_renewal("demo", "main")["ticket"]
    assert [t["key"] for t in mcp_server.find_cert_tickets()["tickets"]] == [ticket]
    assert mcp_server.check_ticket(ticket)["state"] == "waiting_for_certificate"

    new = env.sign_and_attach(ticket)
    assert mcp_server.install_ticket(ticket)["state"] == "waiting_for_approval"  # the tool cannot approve
    env.approve(ticket)
    assert mcp_server.install_ticket(ticket)["state"] == "installed"
    assert env.installed() == new

    # expected problems come back as a readable error, not as an exception
    assert "unknown target" in mcp_server.list_certificates("no-such-target")["error"]
    assert "not in the inventory" in mcp_server.request_renewal("demo", "other")["error"]
    assert "not a Jira issue key" in mcp_server.install_ticket("CERT-1 OR 1=1")["error"]
    foreign = env.jira.create_issue("CERT", "Task", "unrelated", "", [])
    assert "not a ticket of the certificate agent" in mcp_server.check_ticket(foreign)["error"]

    tool = next(tool for tool in tools if tool.name == "request_renewal")
    schema = getattr(tool, "inputSchema", None) or tool.input_schema  # the name differs between mcp 1.x and 2.x
    assert sorted(schema["properties"]) == ["cert_id", "target"] and sorted(schema["required"]) == ["cert_id", "target"]
