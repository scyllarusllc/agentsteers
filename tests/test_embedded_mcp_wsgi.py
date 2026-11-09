"""Offline safety and handshake tests for Frappe-embedded MCP preflight."""
import importlib.util
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "deploy/embedded_mcp_wsgi.py"
spec = importlib.util.spec_from_file_location("embedded_mcp_wsgi", SCRIPT)
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

TOKEN = "local-only-test-token-" + "x" * 40


def request(method="POST", action="initialize", token=TOKEN, *, enabled=True,
            accept="application/json, text/event-stream", body=None):
    if body is None:
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": action,
                           "params": {"protocolVersion": "2025-06-18",
                                      "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}}).encode()
    env = {"REQUEST_METHOD": method, "PATH_INFO": "/mcp",
           "HTTP_AUTHORIZATION": "Bearer " + token,
           "HTTP_ACCEPT": accept,
           "CONTENT_LENGTH": str(len(body)), "wsgi.input": io.BytesIO(body)}
    captured = {}
    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)
    settings = {"AGENTSTEERS_MCP_EMBEDDED_TOKEN": TOKEN}
    if enabled:
        settings["AGENTSTEERS_MCP_EMBEDDED"] = "1"
    with patch.dict(os.environ, settings, clear=True):
        payload = b"".join(server.application(env, start_response))
    return int(captured["status"].split()[0]), payload, captured["headers"]


class EmbeddedMCPTests(unittest.TestCase):
    def test_disabled_by_default(self):
        status, _, _ = request(enabled=False)
        self.assertEqual(status, 404)

    def test_rejects_bad_token(self):
        status, _, headers = request(token="bad")
        self.assertEqual(status, 401)
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_initialize(self):
        status, body, _ = request()
        self.assertEqual(status, 200)
        result = json.loads(body)["result"]
        self.assertEqual(result["protocolVersion"], "2025-06-18")
        self.assertEqual(result["capabilities"]["tools"]["listChanged"], False)

    def test_discover_no_executable_tools(self):
        status, body, _ = request(action="tools/list")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["result"]["tools"], [])

    def test_tools_call_denied(self):
        status, body, _ = request(action="tools/call")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["error"]["code"], -32601)

    def test_missing_accept_rejected(self):
        status, _, _ = request(accept="application/json")
        self.assertEqual(status, 406)

    def test_notification(self):
        body = b'{"jsonrpc":"2.0","method":"notifications/initialized"}'
        status, response, _ = request(body=body)
        self.assertEqual(status, 202)
        self.assertEqual(response, b"")

    def test_oversized_body(self):
        status, _, _ = request(body=b"x" * (server.MAX_BODY + 1))
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
