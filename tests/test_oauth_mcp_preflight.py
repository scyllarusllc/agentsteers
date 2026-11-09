"""Offline OAuth-integrated MCP handshake tests; never start services."""
import io
import json
import os
import unittest
from unittest.mock import Mock, patch

from agentsteers.oauth_mcp_preflight import create_app, from_environment


class OAuthPreflightTests(unittest.TestCase):
    def setUp(self):
        self.verifier = Mock()
        self.verifier.verify.return_value = type("Principal", (), {"subject": "owner"})()
        self.app = create_app(
            verifier=self.verifier,
            resource="https://mcp.agentsteers.com/mcp",
            authorization_server="https://auth.example.com",
        )

    def call(self, method="POST", rpc_method="initialize", *, token="Bearer valid",
             path="/mcp", scheme="https", host="mcp.agentsteers.com"):
        payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": rpc_method}).encode()
        result = {}
        def start(status, headers, exc_info=None):
            result["status"], result["headers"] = status, dict(headers)
        body = b"".join(self.app({
            "wsgi.url_scheme": scheme,
            "HTTP_HOST": host, "PATH_INFO": path,
            "REQUEST_METHOD": method, "HTTP_AUTHORIZATION": token,
            "HTTP_ACCEPT": "application/json, text/event-stream",
            "CONTENT_TYPE": "application/json",
            "CONTENT_LENGTH": str(len(payload)), "wsgi.input": io.BytesIO(payload),
        }, start))
        result["body"] = json.loads(body) if body else None
        return result

    def test_valid_initialize(self):
        out = self.call()
        self.assertEqual(out["status"], "200 OK")
        self.assertEqual(out["body"]["result"]["protocolVersion"], "2025-06-18")
        self.verifier.verify.assert_called_once_with("Bearer valid")

    def test_tools_are_not_executable(self):
        self.assertEqual(self.call(rpc_method="tools/list")["body"]["result"]["tools"], [])
        self.assertEqual(self.call(rpc_method="tools/call")["body"]["error"]["code"], -32601)

    def test_no_token_fails_closed(self):
        self.verifier.verify.side_effect = ValueError("invalid token")
        out = self.call(token="")
        self.assertEqual(out["status"], "401 Unauthorized")
        self.assertIn("resource_metadata", out["headers"]["WWW-Authenticate"])

    def test_public_discovery_bypasses_token_only(self):
        out = self.call(method="GET", path="/.well-known/oauth-protected-resource/mcp", token="")
        self.assertEqual(out["status"], "200 OK")
        self.assertEqual(out["body"]["resource"], "https://mcp.agentsteers.com/mcp")

    def test_host_and_https_fail_closed(self):
        self.assertEqual(self.call(host="evil.example")["status"], "403 Forbidden")
        self.assertEqual(self.call(scheme="http")["status"], "403 Forbidden")

    def test_cannot_enable_implicitly(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "disabled"):
                from_environment()

    def test_reject_missing_verifier(self):
        with self.assertRaises(ValueError):
            create_app(verifier=None, resource="https://mcp.agentsteers.com/mcp",
                       authorization_server="https://auth.example.com")


if __name__ == "__main__":
    unittest.main()
