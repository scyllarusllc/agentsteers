"""Offline Frappe v17-facing OAuth MCP contract tests.

These tests deliberately use fake introspection responses: they do NOT claim
that a particular deployed Frappe v17 site, PKCE flow, or ChatGPT client works.
There is no network traffic, no credential material and no Codex invocation.
"""
import io
import json
import time
import unittest

from agentsteers.frappe_oauth_wsgi import build_application

ISSUER = "https://frappe.example.test"
RESOURCE = "https://mcp.agentsteers.com/mcp"
REPO = "scyllarusllc/agentsteers"


class FakeResponse:
    status = 200

    def __init__(self, claims):
        self.data = io.BytesIO(json.dumps(claims).encode())

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, amount=-1):
        return self.data.read(amount)


class FrappeV17OAuthContractTests(unittest.TestCase):
    def setUp(self):
        self.claims = {
            "active": True, "iss": ISSUER, "sub": "alice",
            "client_id": "dedicated-agentsteers-client",
            "aud": "dedicated-agentsteers-client",
            "exp": time.time() + 300,
            "scope": "agentsteers:read agentsteers:submit agentsteers:cancel",
        }
        self.introspection_requests = []

        def fake_opener(request, timeout):
            self.introspection_requests.append(request)
            self.assertEqual(
                request.full_url,
                ISSUER + "/api/method/frappe.integrations.oauth2.introspect_token",
            )
            self.assertEqual(request.get_method(), "POST")
            self.assertIn(b"token_type_hint=access_token", request.data)
            self.assertTrue(request.get_header("Authorization").startswith("Basic "))
            return FakeResponse(self.claims)

        self.app = build_application({
            "AGENTSTEERS_FRAPPE_OAUTH_ENABLED": "1",
            "AGENTSTEERS_FRAPPE_ISSUER": ISSUER,
            "AGENTSTEERS_FRAPPE_CLIENT_ID": "dedicated-agentsteers-client",
            "AGENTSTEERS_FRAPPE_CLIENT_SECRET": "fake-test-only-secret",
            "AGENTSTEERS_FRAPPE_SUBJECTS": "alice,bob",
            "AGENTSTEERS_FRAPPE_REPOS": REPO,
            "AGENTSTEERS_FRAPPE_MCP_RESOURCE": RESOURCE,
        }, opener=fake_opener)

    def call(self, method, params=None, token="offline-test-token"):
        request = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
        raw = json.dumps(request).encode()
        env = {
            "wsgi.url_scheme": "https", "HTTP_HOST": "mcp.agentsteers.com",
            "PATH_INFO": "/mcp", "REQUEST_METHOD": "POST",
            "HTTP_ACCEPT": "application/json, text/event-stream",
            "CONTENT_LENGTH": str(len(raw)), "wsgi.input": io.BytesIO(raw),
            "HTTP_AUTHORIZATION": "Bearer " + token,
        }
        response = {}

        def start(status, headers):
            response["status"] = int(status.split()[0])
            response["headers"] = dict(headers)

        body = b"".join(self.app(env, start))
        response["body"] = json.loads(body) if body else None
        return response

    def invoke(self, name, arguments):
        response = self.call("tools/call", {"name": name, "arguments": arguments})
        self.assertEqual(response["status"], 200)
        return json.loads(response["body"]["result"]["content"][0]["text"])

    def test_valid_frappe_access_token_can_use_mock_only(self):
        self.assertEqual(self.call("initialize")["status"], 200)
        submitted = self.invoke("submit_task", {"repository": REPO, "instruction": "mock only"})
        self.assertTrue(submitted["ok"])
        result = self.invoke("get_task_status", {"task_id": submitted["task_id"]})
        self.assertEqual(result["status"], "queued_mock")
        self.assertGreaterEqual(len(self.introspection_requests), 2)

    def test_openid_all_never_grants_agentsteers_permissions(self):
        self.claims["scope"] = "openid all"
        self.assertEqual(self.call("initialize")["status"], 401)

    def test_expired_or_wrong_client_tokens_are_denied(self):
        for updates in (
            {"active": False},
            {"exp": time.time() - 1},
            {"client_id": "other-app"},
            {"aud": "other-app"},
            {"iss": "https://evil.example"},
            {"sub": "someone-else"},
        ):
            with self.subTest(updates=updates):
                previous = self.claims.copy()
                self.claims.update(updates)
                self.assertEqual(self.call("initialize")["status"], 401)
                self.claims = previous

    def test_read_scope_cannot_submit_or_cancel(self):
        self.claims["scope"] = "agentsteers:read"
        response = self.call("tools/call", {
            "name": "submit_task",
            "arguments": {"repository": REPO, "instruction": "should fail"},
        })
        self.assertTrue(response["body"]["result"]["isError"])
        self.assertIn("insufficient_scope",
                      response["body"]["result"]["_meta"]["mcp/www_authenticate"][0])

    def test_cross_user_task_isolation(self):
        submitted = self.invoke("submit_task", {"repository": REPO, "instruction": "mock only"})
        self.claims["sub"] = "bob"
        for name in ("get_task_status", "get_task_result", "cancel_task"):
            with self.subTest(tool=name):
                result = self.invoke(name, {"task_id": submitted["task_id"]})
                self.assertEqual(result["error"], "task_not_found")


if __name__ == "__main__":
    unittest.main()
