"""Offline tests for the isolated OAuth Mock MCP route. No network or Codex."""
import io
import json
import unittest

from agentsteers.oauth_mock_mcp import create_app
from agentsteers.oauth_security import Principal, AuthorizationError

RESOURCE = "https://mcp.agentsteers.com/mcp"


class FakeVerifier:
    def verify(self, header):
        if not isinstance(header, str) or not header.startswith("Bearer demo-"):
            raise AuthorizationError("invalid")
        subject = header.split("Bearer demo-", 1)[1]
        if subject not in ("alice", "bob", "reader"):
            raise AuthorizationError("invalid")
        scopes = {"agentsteers:read"} if subject == "reader" else {
            "agentsteers:read", "agentsteers:submit", "agentsteers:cancel"}
        return Principal(subject=subject, scopes=frozenset(scopes))


class OAuthMockMCPTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(verifier=FakeVerifier(), resource=RESOURCE,
                              authorization_server="https://auth.example.com",
                              repositories={"scyllarusllc/agentsteers"})

    def call(self, method="initialize", params=None, *, actor="alice",
             path="/mcp", scheme="https", host="mcp.agentsteers.com",
             origin=None, verb="POST"):
        raw = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                          "params": params or {}}).encode()
        env = {"wsgi.url_scheme": scheme, "HTTP_HOST": host, "PATH_INFO": path,
               "REQUEST_METHOD": verb, "HTTP_ACCEPT": "application/json, text/event-stream",
               "CONTENT_LENGTH": str(len(raw)), "wsgi.input": io.BytesIO(raw)}
        if actor is not None:
            env["HTTP_AUTHORIZATION"] = "Bearer demo-" + actor
        if origin is not None:
            env["HTTP_ORIGIN"] = origin
        result = {}
        def start_response(status, headers):
            result["status"] = int(status.split()[0])
            result["headers"] = dict(headers)
        data = b"".join(self.app(env, start_response))
        result["body"] = json.loads(data) if data else None
        return result

    def invoke(self, actor, name, arguments):
        r = self.call("tools/call", {"name": name, "arguments": arguments}, actor=actor)
        self.assertEqual(r["status"], 200)
        return json.loads(r["body"]["result"]["content"][0]["text"])

    def test_discovery(self):
        r = self.call(path="/.well-known/oauth-protected-resource", verb="GET",
                      actor=None)
        self.assertEqual(r["status"], 200)
        self.assertEqual(r["body"]["resource"], RESOURCE)

    def test_login_challenge_and_reject_invalid(self):
        for actor in (None, "invalid"):
            r = self.call(actor=actor)
            self.assertEqual(r["status"], 401)
            self.assertIn("resource_metadata=", r["headers"]["WWW-Authenticate"])

    def test_initialize_and_four_tools(self):
        self.assertEqual(self.call()["status"], 200)
        names = {tool["name"] for tool in self.call("tools/list")["body"]["result"]["tools"]}
        self.assertEqual(names, {"submit_task", "get_task_status",
                                 "get_task_result", "cancel_task"})
        tools = self.call("tools/list")["body"]["result"]["tools"]
        self.assertEqual(
            {t["name"]: t["_meta"]["securitySchemes"][0]["scopes"] for t in tools},
            {"submit_task": ["agentsteers:submit"],
             "get_task_status": ["agentsteers:read"],
             "get_task_result": ["agentsteers:read"],
             "cancel_task": ["agentsteers:cancel"]})

    def test_lifecycle_and_actor_isolation(self):
        created = self.invoke("alice", "submit_task", {
            "repository": "scyllarusllc/agentsteers", "instruction": "Mock only"})
        self.assertTrue(created["ok"])
        task_id = created["task_id"]
        for name in ("get_task_status", "get_task_result", "cancel_task"):
            self.assertEqual(self.invoke("bob", name, {"task_id": task_id})["error"],
                             "task_not_found")
        self.assertEqual(self.invoke("alice", "get_task_status",
                                     {"task_id": task_id})["status"], "queued_mock")
        self.assertEqual(self.invoke("alice", "cancel_task",
                                     {"task_id": task_id})["status"], "cancelled")

    def test_read_only_actor_gets_linking_challenge(self):
        for name, args in [
            ("submit_task", {"repository": "scyllarusllc/agentsteers",
                             "instruction": "No"}),
            ("cancel_task", {"task_id": "unused"}),
        ]:
            r = self.call("tools/call", {"name": name, "arguments": args},
                          actor="reader")
            result = r["body"]["result"]
            self.assertTrue(result["isError"])
            self.assertIn("insufficient_scope",
                          result["_meta"]["mcp/www_authenticate"][0])
            self.assertIn("resource_metadata",
                          result["_meta"]["mcp/www_authenticate"][0])

    def test_repo_allowlist(self):
        result = self.invoke("alice", "submit_task", {
            "repository": "other/repo", "instruction": "No"})
        self.assertEqual(result["error"], "forbidden")

    def test_transport_and_origin(self):
        self.assertEqual(self.call(scheme="http")["status"], 403)
        self.assertEqual(self.call(host="evil.example")["status"], 403)
        self.assertEqual(self.call(origin="https://evil.example")["status"], 403)

    def test_method_and_unknown_tool(self):
        self.assertEqual(self.call(verb="GET")["status"], 405)
        r = self.call("tools/call", {"name": "run_shell", "arguments": {}})
        self.assertEqual(r["body"]["error"]["code"], -32602)


if __name__ == "__main__":
    unittest.main()
