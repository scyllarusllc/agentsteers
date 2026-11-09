"""Offline protocol/security tests for opt-in HTTP mock MCP."""
import io
import json
import os
import unittest
from unittest.mock import patch

from agentsteers import mock_http_mcp as server

TOKEN = "test-token-" + "a" * 48
SETTINGS = {
    "AGENTSTEERS_MCP_MOCK_ENABLED": "1",
    "AGENTSTEERS_MCP_MOCK_TOKEN": TOKEN,
    "AGENTSTEERS_MCP_MOCK_HOST": "mcp.agentsteers.com",
    "AGENTSTEERS_MCP_MOCK_REPOS": "scyllarusllc/agentsteers",
}


def call(method="initialize", params=None, *, token=TOKEN, host="mcp.agentsteers.com",
         scheme="https", enabled=True, origin=None, raw=None, verb="POST"):
    if raw is None:
        raw = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                          "params": params or {}}).encode()
    env = {
        "PATH_INFO": "/mcp", "REQUEST_METHOD": verb, "wsgi.url_scheme": scheme,
        "HTTP_HOST": host, "HTTP_AUTHORIZATION": "Bearer " + token,
        "HTTP_ACCEPT": "application/json, text/event-stream",
        "CONTENT_LENGTH": str(len(raw)), "wsgi.input": io.BytesIO(raw),
    }
    if origin is not None:
        env["HTTP_ORIGIN"] = origin
    got = {}

    def start_response(status, headers):
        got["status"] = int(status.split()[0])
        got["headers"] = dict(headers)

    config = dict(SETTINGS)
    if not enabled:
        config.pop("AGENTSTEERS_MCP_MOCK_ENABLED")
    with patch.dict(os.environ, config, clear=True):
        payload = b"".join(server.application(env, start_response))
    got["body"] = json.loads(payload) if payload else None
    return got


class MockHttpMCPTests(unittest.TestCase):
    def test_disabled_by_default(self):
        self.assertEqual(call(enabled=False)["status"], 404)

    def test_initialize_and_list_four_tools(self):
        initialized = call()
        self.assertEqual(initialized["status"], 200)
        self.assertEqual(initialized["body"]["result"]["protocolVersion"], server.PROTOCOL)
        tools = call("tools/list")["body"]["result"]["tools"]
        self.assertEqual({x["name"] for x in tools}, {
            "submit_task", "get_task_status", "get_task_result", "cancel_task"})

    def test_lifecycle_mock_only(self):
        def tool(name, args):
            result = call("tools/call", {"name": name, "arguments": args})
            self.assertEqual(result["status"], 200)
            payload = result["body"]["result"]
            return json.loads(payload["content"][0]["text"])
        created = tool("submit_task", {
            "repository": "scyllarusllc/agentsteers", "instruction": "Describe project"})
        self.assertTrue(created["ok"])
        job_id = created["task_id"]
        self.assertEqual(tool("get_task_status", {"task_id": job_id})["status"], "queued_mock")
        self.assertIn("No server or Codex", tool("get_task_result", {
            "task_id": job_id})["result"]["message"])
        self.assertEqual(tool("cancel_task", {"task_id": job_id})["status"], "cancelled")

    def test_denies_bad_token(self):
        self.assertEqual(call(token="wrong")["status"], 401)

    def test_requires_trusted_https_and_host(self):
        self.assertEqual(call(scheme="http")["status"], 403)
        self.assertEqual(call(host="attacker.example")["status"], 403)
        self.assertEqual(call(origin="https://attacker.example")["status"], 403)

    def test_rejects_unlisted_repository(self):
        payload = call("tools/call", {"name": "submit_task", "arguments": {
            "repository": "other/repo", "instruction": "test"}})["body"]["result"]
        self.assertTrue(payload["isError"])

    def test_denies_unknown_tool(self):
        payload = call("tools/call", {"name": "run_shell", "arguments": {}})["body"]
        self.assertEqual(payload["error"]["code"], -32602)

    def test_rejects_oversized_json(self):
        result = call(raw=b"x" * (server.MAX_BODY + 1))
        self.assertEqual(result["body"]["error"]["code"], -32700)

    def test_denies_get(self):
        self.assertEqual(call(verb="GET")["status"], 405)


if __name__ == "__main__":
    unittest.main()
