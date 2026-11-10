"""Offline end-to-end Frappe-native opaque-token -> MCP mock task tests.

Fake introspection only. This neither authenticates against a deployed Frappe
instance nor enables a public MCP route, network connection, or Codex.
"""
import io
import json
import time
import unittest
from urllib.parse import parse_qs

from agentsteers.frappe_oauth_wsgi import build_application

ISSUER = "https://frappe.example.test"
RESOURCE = "https://mcp.agentsteers.com/mcp"
REPO = "scyllarusllc/agentsteers"
CLIENT = "dedicated-agentsteers-client"


class FakeResponse:
    status = 200

    def __init__(self, claims):
        self.stream = io.BytesIO(json.dumps(claims).encode("utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        return self.stream.read(size)


class FrappeNativeMCPRoundtripTests(unittest.TestCase):
    def setUp(self):
        # Actual Frappe-native introspection may omit iss/aud, but it must bind
        # the authenticated client's token and expose an OpenID subject.
        self.claims = {
            "active": True,
            "exp": time.time() + 300,
            "client_id": CLIENT,
            "sub": "alice",
            "scope": "openid agentsteers:read agentsteers:submit agentsteers:cancel",
        }
        self.requests = []

        def fake_opener(request, timeout):
            self.requests.append(request)
            self.assertEqual(request.full_url, ISSUER +
                             "/api/method/frappe.integrations.oauth2.introspect_token")
            self.assertEqual(request.get_method(), "POST")
            self.assertTrue(request.get_header("Authorization").startswith("Basic "))
            self.assertEqual(parse_qs(request.data.decode())["token_type_hint"],
                             ["access_token"])
            self.assertLessEqual(timeout, 5)
            return FakeResponse(self.claims)

        self.app = build_application({
            "AGENTSTEERS_FRAPPE_OAUTH_ENABLED": "1",
            "AGENTSTEERS_FRAPPE_ISSUER": ISSUER,
            "AGENTSTEERS_FRAPPE_CLIENT_ID": CLIENT,
            "AGENTSTEERS_FRAPPE_CLIENT_SECRET": "fake-offline-test-secret",
            "AGENTSTEERS_FRAPPE_SUBJECTS": "alice,bob",
            "AGENTSTEERS_FRAPPE_REPOS": REPO,
            "AGENTSTEERS_FRAPPE_MCP_RESOURCE": RESOURCE,
            "AGENTSTEERS_FRAPPE_INTROSPECTION_FORMAT": "frappe_native",
        }, opener=fake_opener)

    def request(self, method, params=None, *, authorization="Bearer fake-token"):
        payload = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": method, "params": params or {},
        }).encode("utf-8")
        environ = {
            "PATH_INFO": "/mcp",
            "REQUEST_METHOD": "POST",
            "wsgi.url_scheme": "https",
            "HTTP_HOST": "mcp.agentsteers.com",
            "HTTP_ACCEPT": "application/json, text/event-stream",
            "CONTENT_LENGTH": str(len(payload)),
            "wsgi.input": io.BytesIO(payload),
            "HTTP_AUTHORIZATION": authorization,
        }
        captured = {}

        def start_response(status, headers):
            captured["status"] = int(status.split()[0])
            captured["headers"] = dict(headers)

        raw = b"".join(self.app(environ, start_response))
        captured["body"] = json.loads(raw) if raw else None
        return captured

    def invoke(self, name, arguments):
        response = self.request("tools/call", {
            "name": name, "arguments": arguments,
        })
        self.assertEqual(response["status"], 200)
        result = response["body"]["result"]
        return json.loads(result["content"][0]["text"])

    def test_native_token_full_mock_lifecycle(self):
        self.assertEqual(self.request("initialize")["status"], 200)
        available = self.request("tools/list")["body"]["result"]["tools"]
        self.assertEqual({tool["name"] for tool in available}, {
            "submit_task", "get_task_status", "get_task_result", "cancel_task",
        })
        created = self.invoke("submit_task", {
            "repository": REPO, "instruction": "simulate a safe change",
        })
        self.assertTrue(created["ok"])
        task_id = created["task_id"]
        self.assertEqual(self.invoke("get_task_status", {
            "task_id": task_id,
        })["status"], "queued_mock")
        simulated = self.invoke("get_task_result", {"task_id": task_id})
        self.assertTrue(simulated["ok"])
        self.assertIn("Simulation only", simulated["result"]["message"])
        cancelled = self.invoke("cancel_task", {"task_id": task_id})
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(self.invoke("get_task_status", {
            "task_id": task_id,
        })["status"], "cancelled")
        self.assertGreaterEqual(len(self.requests), 7)

    def test_different_actor_cannot_read_or_cancel(self):
        task = self.invoke("submit_task", {
            "repository": REPO, "instruction": "mock only",
        })
        self.claims["sub"] = "bob"
        for action in ("get_task_status", "get_task_result", "cancel_task"):
            with self.subTest(action=action):
                response = self.invoke(action, {"task_id": task["task_id"]})
                self.assertEqual(response["error"], "task_not_found")

    def test_read_only_token_cannot_submit_or_cancel(self):
        self.claims["scope"] = "openid agentsteers:read"
        for action, args in (
            ("submit_task", {"repository": REPO, "instruction": "no"}),
            ("cancel_task", {"task_id": "not-owned"}),
        ):
            with self.subTest(action=action):
                response = self.request("tools/call", {
                    "name": action, "arguments": args,
                })
                self.assertTrue(response["body"]["result"]["isError"])
                self.assertIn("insufficient_scope",
                              response["body"]["result"]["_meta"]["mcp/www_authenticate"][0])

    def test_unapproved_repository_rejected(self):
        result = self.invoke("submit_task", {
            "repository": "outsider/other", "instruction": "no",
        })
        self.assertEqual(result["error"], "forbidden")

    def test_invalid_claims_fail_before_mock_task_access(self):
        invalid = (
            {"active": False},
            {"exp": time.time() - 1},
            {"client_id": "unrelated-client"},
            {"sub": "not-allowlisted"},
            {"scope": "openid all"},
            {"scope": "agentsteers:read"},
            {"iss": "https://other.example.test"},
            {"aud": "unrelated-client"},
        )
        baseline = dict(self.claims)
        for changes in invalid:
            with self.subTest(claims=changes):
                self.claims = {**baseline, **changes}
                self.assertEqual(self.request("initialize")["status"], 401)
        self.claims = baseline
        self.assertEqual(self.request("initialize", authorization="")["status"], 401)


if __name__ == "__main__":
    unittest.main()
