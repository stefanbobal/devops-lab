"""JiraClient against a small local HTTP server that answers like the Jira REST API v2."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from cert_agent.jira_client import JiraClient, JiraError

ISSUE = {
    "key": "CERT-7",
    "fields": {
        "project": {"key": "CERT"}, "summary": "Certificate renewal: demo / main",
        "status": {"name": "Approved"}, "labels": ["cert-agent", "cert-fp-0123456789abcdef"],
    },
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, status=200, body=b"", content_type="application/json"):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        record = {"method": self.command, "path": self.path, "headers": dict(self.headers), "body": body}
        self.server.calls.append(record)
        base = f"http://127.0.0.1:{self.server.server_port}"
        attachment = {
            "id": 501, "filename": "signed.pem", "size": 11, "created": "2026-11-11T12:00:00.000+0000",
            "content": f"{base}/secure/attachment/501/signed.pem",
        }
        if self.headers.get("Authorization") != "Bearer secret-token":
            return self._send(401, {"errorMessages": ["no token"]})
        path, method = self.path.split("?")[0], self.command
        if (method, path) == ("POST", "/rest/api/2/search"):
            start = json.loads(body)["startAt"]
            page = [ISSUE, {**ISSUE, "key": "CERT-8"}][start:start + 1]  # one issue per page, to test paging
            return self._send(body={"total": 2, "issues": page})
        if (method, path) == ("POST", "/rest/api/2/issue"):
            return self._send(201, {"key": "CERT-9"})
        if (method, path) == ("GET", "/rest/api/2/issue/CERT-7"):
            fields = dict(ISSUE["fields"], attachment=[attachment])
            return self._send(body={"key": "CERT-7", "fields": fields})
        if (method, path) == ("PUT", "/rest/api/2/issue/CERT-7"):
            return self._send(204)
        if (method, path) == ("POST", "/rest/api/2/issue/CERT-7/attachments"):
            return self._send(body=[attachment])
        if (method, path) == ("GET", "/secure/attachment/501/signed.pem"):
            return self._send(body=b"certificate", content_type="application/octet-stream")
        if (method, path) == ("GET", "/rest/api/2/issue/CERT-7/comment"):
            return self._send(body={"comments": [{"body": "first"}, {"body": "second"}]})
        if (method, path) == ("POST", "/rest/api/2/issue/CERT-7/comment"):
            return self._send(201, {})
        if (method, path) == ("GET", "/rest/api/2/issue/CERT-7/transitions"):
            return self._send(body={"transitions": [{"id": "31", "name": "Done"}, {"id": "21", "name": "Approve"}]})
        if (method, path) == ("POST", "/rest/api/2/issue/CERT-7/transitions"):
            return self._send(204)
        self._send(404, {"errorMessages": ["not found"]})

    do_GET = do_POST = do_PUT = _handle


@pytest.fixture
def jira():
    server = HTTPServer(("127.0.0.1", 0), Handler)
    server.calls = []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    client = JiraClient(f"http://127.0.0.1:{server.server_port}", "secret-token")
    client.calls = server.calls
    yield client
    server.shutdown()


def last(jira):
    call = jira.calls[-1]
    return call, (json.loads(call["body"]) if call["body"][:1] in (b"{", b"[") else None)


def test_search_builds_jql_and_follows_pages(jira):
    issues = jira.find_open_issues("CERT", ["cert-agent", "cert-fp-0123456789abcdef"])
    assert [i["key"] for i in issues] == ["CERT-7", "CERT-8"]
    assert issues[0] == {
        "key": "CERT-7", "project": "CERT", "summary": "Certificate renewal: demo / main",
        "status": "Approved", "labels": ["cert-agent", "cert-fp-0123456789abcdef"],
    }
    _, body = last(jira)
    assert body["jql"] == (
        'project = "CERT" AND labels = "cert-agent" AND labels = "cert-fp-0123456789abcdef" '
        "AND statusCategory != Done ORDER BY created ASC"
    )
    assert body["startAt"] == 1


def test_search_refuses_values_that_could_change_the_query(jira):
    with pytest.raises(JiraError):
        jira.find_open_issues('CERT" OR project = "HR', ["cert-agent"])
    with pytest.raises(JiraError):
        jira.find_open_issues("CERT", ['x" OR labels = "y'])
    assert not jira.calls


def test_create_issue(jira):
    assert jira.create_issue("CERT", "Task", "summary", "text", ["cert-agent"]) == "CERT-9"
    _, body = last(jira)
    assert body == {"fields": {
        "project": {"key": "CERT"}, "issuetype": {"name": "Task"},
        "summary": "summary", "description": "text", "labels": ["cert-agent"],
    }}


def test_attachments_upload_list_download(jira):
    uploaded = jira.add_attachment("CERT-7", "demo_main.csr", b"-----BEGIN CERTIFICATE REQUEST-----")
    call, _ = last(jira)
    assert call["headers"]["X-Atlassian-Token"] == "no-check"
    assert call["headers"]["Content-Type"].startswith("multipart/form-data")
    assert b'name="file"; filename="demo_main.csr"' in call["body"]
    assert b"-----BEGIN CERTIFICATE REQUEST-----" in call["body"]
    assert uploaded["id"] == "501"

    listed = jira.list_attachments("CERT-7")
    assert listed[0]["filename"] == "signed.pem" and listed[0]["size"] == 11
    assert jira.download_attachment(listed[0]) == b"certificate"


def test_token_is_never_sent_to_another_host(jira):
    with pytest.raises(JiraError, match="outside Jira"):
        jira.download_attachment({"content": "http://127.0.0.1:1/secure/attachment/1/x"})
    with pytest.raises(JiraError, match="outside Jira"):
        jira.download_attachment({"content": jira.base_url + ".attacker.example/x"})


def test_labels_comments_and_transitions(jira):
    jira.update_labels("CERT-7", add=["cert-installed"], remove=["cert-validated"])
    _, body = last(jira)
    assert body == {"update": {"labels": [{"add": "cert-installed"}, {"remove": "cert-validated"}]}}

    jira.add_comment("CERT-7", "hello")
    assert last(jira)[1] == {"body": "hello"}
    assert jira.list_comments("CERT-7") == ["first", "second"]

    assert jira.transition("CERT-7", "done") is True
    assert last(jira)[1] == {"transition": {"id": "31"}}
    assert jira.transition("CERT-7", "Reject") is False


def test_errors_are_reported_with_status_and_bad_keys_are_refused(jira):
    with pytest.raises(JiraError, match="HTTP 404"):
        jira.get_issue("CERT-404")
    with pytest.raises(JiraError, match="not a Jira issue key"):
        jira.get_issue("CERT-7/../../admin")
    bad = JiraClient(jira.base_url, "wrong-token")
    with pytest.raises(JiraError, match="HTTP 401"):
        bad.get_issue("CERT-7")
