"""Small client for the Jira Data Center REST API (version 2).

Authentication is a personal access token of a dedicated technical Jira user,
sent as a Bearer token. Only the calls the certificate workflow needs exist here.
"""
from __future__ import annotations

import re

import requests

PROJECT_KEY = re.compile(r"^[A-Z][A-Z0-9_]+$")
ISSUE_KEY = re.compile(r"^[A-Z][A-Z0-9_]+-\d+$")
LABEL = re.compile(r"^[A-Za-z0-9_.-]+$")


class JiraError(RuntimeError):
    pass


class JiraClient:
    def __init__(self, base_url: str, token: str, verify: bool | str = True, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/json"})
        self._session.verify = verify

    # ------------------------------------------------------------ plumbing

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        if not url.startswith("http"):
            url = self.base_url + url
        if not url.startswith(self.base_url + "/"):
            # Attachment links come from Jira data. Never send the token anywhere else.
            raise JiraError(f"refusing to call a URL outside Jira: {url}")
        try:
            response = self._session.request(method, url, timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            raise JiraError(f"{method} {url}: {exc}") from exc
        if response.status_code >= 400:
            raise JiraError(f"{method} {url}: HTTP {response.status_code}: {response.text[:300]}")
        return response

    @staticmethod
    def _key(key: str) -> str:
        if not ISSUE_KEY.match(key):
            raise JiraError(f"not a Jira issue key: {key!r}")
        return key

    @staticmethod
    def _simple(issue: dict) -> dict:
        fields = issue.get("fields") or {}
        return {
            "key": issue["key"],
            "project": (fields.get("project") or {}).get("key", issue["key"].rsplit("-", 1)[0]),
            "summary": fields.get("summary", ""),
            "status": (fields.get("status") or {}).get("name", ""),
            "labels": list(fields.get("labels") or []),
        }

    # ------------------------------------------------------------ issues

    def find_open_issues(self, project: str, labels: list[str]) -> list[dict]:
        """Issues of the project that carry all the labels and are not done, oldest first."""
        if not PROJECT_KEY.match(project):
            raise JiraError(f"not a Jira project key: {project!r}")
        for label in labels:
            if not LABEL.match(label):
                raise JiraError(f"label not allowed in a search: {label!r}")
        clauses = [f'project = "{project}"'] + [f'labels = "{label}"' for label in labels]
        jql = " AND ".join(clauses) + " AND statusCategory != Done ORDER BY created ASC"
        issues: list[dict] = []
        while True:
            body = {
                "jql": jql,
                "startAt": len(issues),
                "maxResults": 50,
                "fields": ["summary", "status", "labels", "project"],
            }
            page = self._request("POST", "/rest/api/2/search", json=body).json()
            batch = page.get("issues") or []
            issues.extend(self._simple(item) for item in batch)
            if not batch or len(issues) >= page.get("total", 0):
                return issues

    def get_issue(self, key: str) -> dict:
        response = self._request(
            "GET", f"/rest/api/2/issue/{self._key(key)}", params={"fields": "summary,status,labels,project"}
        )
        return self._simple(response.json())

    def create_issue(self, project: str, issue_type: str, summary: str, description: str, labels: list[str]) -> str:
        fields = {
            "project": {"key": project},
            "issuetype": {"name": issue_type},
            "summary": summary,
            "description": description,
            "labels": labels,
        }
        return self._request("POST", "/rest/api/2/issue", json={"fields": fields}).json()["key"]

    def update_labels(self, key: str, add: list[str] = (), remove: list[str] = ()) -> None:
        operations = [{"add": label} for label in add] + [{"remove": label} for label in remove]
        if operations:
            self._request("PUT", f"/rest/api/2/issue/{self._key(key)}", json={"update": {"labels": operations}})

    def transition(self, key: str, name: str) -> bool:
        """Run the workflow transition with this name. False if the ticket does not offer it."""
        path = f"/rest/api/2/issue/{self._key(key)}/transitions"
        for item in self._request("GET", path).json().get("transitions") or []:
            if item["name"].lower() == name.lower():
                self._request("POST", path, json={"transition": {"id": item["id"]}})
                return True
        return False

    # ------------------------------------------------------------ comments

    def add_comment(self, key: str, body: str) -> None:
        self._request("POST", f"/rest/api/2/issue/{self._key(key)}/comment", json={"body": body})

    def list_comments(self, key: str) -> list[str]:
        data = self._request("GET", f"/rest/api/2/issue/{self._key(key)}/comment").json()
        return [item.get("body") or "" for item in data.get("comments") or []]

    # ------------------------------------------------------------ attachments

    def add_attachment(self, key: str, filename: str, content: bytes) -> dict:
        response = self._request(
            "POST",
            f"/rest/api/2/issue/{self._key(key)}/attachments",
            files={"file": (filename, content, "application/octet-stream")},
            headers={"X-Atlassian-Token": "no-check"},
        )
        return self._attachment(response.json()[0])

    def list_attachments(self, key: str) -> list[dict]:
        response = self._request("GET", f"/rest/api/2/issue/{self._key(key)}", params={"fields": "attachment"})
        items = (response.json().get("fields") or {}).get("attachment") or []
        return [self._attachment(item) for item in items]

    def download_attachment(self, attachment: dict) -> bytes:
        return self._request("GET", attachment["content"], headers={"Accept": "*/*"}).content

    @staticmethod
    def _attachment(item: dict) -> dict:
        return {
            "id": str(item["id"]),
            "filename": item.get("filename", ""),
            "size": int(item.get("size") or 0),
            "created": item.get("created", ""),
            "content": item.get("content", ""),
        }
