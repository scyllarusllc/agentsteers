"""Opt-in local MCP -> Frappe task transport; no Codex execution.

Use a dedicated Frappe API user with narrowly limited permissions.
Credentials are server-side configuration, never MCP tool arguments.
"""
from __future__ import annotations

import json
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


class FrappeTaskClient:
    def __init__(self, *, base_url: str, api_key: str, api_secret: str,
                 allowed_repositories: set[str], timeout: float = 10):
        u = urlsplit(base_url)
        if (u.scheme not in ("https", "http") or not u.hostname
                or u.username or u.password or u.query or u.fragment
                or (u.scheme == "http" and u.hostname not in ("127.0.0.1", "localhost", "::1"))):
            raise ValueError("Frappe URL must use HTTPS or loopback HTTP without credentials")
        if not api_key or not api_secret or not allowed_repositories:
            raise ValueError("API credentials and a repository allowlist are required")
        self.base = base_url.rstrip("/")
        self.auth = "token " + api_key + ":" + api_secret
        self.allowed = frozenset(allowed_repositories)
        self.timeout = timeout

    def _call(self, method: str, action: str, arguments: dict) -> dict:
        path = "/api/method/agentsteers_frappe.api." + action
        if method == "GET":
            url = self.base + path + "?" + urlencode(arguments)
            data = None
        else:
            url = self.base + path
            data = json.dumps(arguments).encode("utf-8")
        request = Request(url, data=data, method=method, headers={
            "Authorization": self.auth,
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if data is not None else {}),
        })
        try:
            with urlopen(request, timeout=self.timeout, context=ssl.create_default_context()) as response:
                body = json.load(response)
        except (HTTPError, URLError, OSError, ValueError) as exc:
            # Avoid returning API tokens, server tracebacks or internal URLs.
            raise RuntimeError("Frappe request failed; check server logs") from None
        payload = body.get("message")
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected Frappe response")
        return payload

    def submit_task(self, repository: str, instruction: str, approved: bool = False) -> dict:
        if not approved:
            return {"ok": False, "error": "explicit_approval_required"}
        if not isinstance(repository, str) or repository not in self.allowed:
            return {"ok": False, "error": "repository_not_allowed"}
        if not isinstance(instruction, str) or not instruction.strip() or len(instruction) > 2000:
            return {"ok": False, "error": "invalid_instruction"}
        return self._call("POST", "create_task", {"repository": repository, "instruction": instruction})

    def get_task_status(self, task_id: str) -> dict:
        if not isinstance(task_id, str) or not task_id:
            return {"ok": False, "error": "invalid_task_id"}
        return self._call("GET", "get_task_status", {"task_id": task_id})

    def get_task_result(self, task_id: str) -> dict:
        status = self.get_task_status(task_id)
        return {"ok": True, "task_id": status["task_id"], "status": status["status"],
                "result": {"message": status.get("result_summary") or "Task has not completed."}}

    def cancel_task(self, task_id: str) -> dict:
        return {"ok": False, "error": "frappe_cancellation_not_implemented"}
