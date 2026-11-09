"""Regression tests for opt-in remote MCP WSGI authentication boundary.

These tests do not deploy, open a listener, or invoke Codex.
"""
import unittest
from unittest.mock import Mock

from agentsteers.remote_mcp_guard import RemoteMCPGuard


class Principal:
    subject = "test-actor"


class RemoteMCPGuardTests(unittest.TestCase):
    def setUp(self):
        self.verifier = Mock()
        self.verifier.verify.return_value = Principal()
        self.received = []

        def downstream(env, start_response):
            self.received.append(env)
            start_response("200 OK", [("Content-Type", "text/plain")])
            return [b"mock-only"]

        self.guard = RemoteMCPGuard(
            downstream, self.verifier, public_origin="https://mcp.agentsteers.com"
        )
        self.base = {
            "wsgi.url_scheme": "https",
            "HTTP_HOST": "mcp.agentsteers.com",
            "HTTP_AUTHORIZATION": "Bearer example-test-value",
        }

    def call(self, **overrides):
        env = dict(self.base)
        env.update(overrides)
        result = {}

        def start_response(status, headers):
            result["status"] = int(status.split()[0])

        result["body"] = b"".join(self.guard(env, start_response))
        return result

    def test_valid_authenticated_request_reaches_downstream(self):
        result = self.call()
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["body"], b"mock-only")
        self.assertEqual(self.received[0]["agentsteers.principal"].subject, "test-actor")

    def test_invalid_token_is_rejected(self):
        self.verifier.verify.side_effect = ValueError("invalid")
        result = self.call(HTTP_AUTHORIZATION="Bearer bad")
        self.assertEqual(result["status"], 401)
        self.assertEqual(self.received, [])
        self.assertNotIn(b"invalid", result["body"])

    def test_missing_token_is_rejected(self):
        self.verifier.verify.side_effect = ValueError("missing")
        self.assertEqual(self.call(HTTP_AUTHORIZATION="")["status"], 401)

    def test_https_is_required(self):
        self.assertEqual(self.call(**{"wsgi.url_scheme": "http"})["status"], 403)
        self.assertEqual(self.received, [])

    def test_host_and_origin_are_checked(self):
        self.assertEqual(self.call(HTTP_HOST="evil.example")["status"], 403)
        self.assertEqual(self.call(HTTP_ORIGIN="https://evil.example")["status"], 403)
        self.assertEqual(self.call(HTTP_ORIGIN="https://mcp.agentsteers.com")["status"], 200)

    def test_rejects_ambiguous_authorization(self):
        self.assertEqual(self.call(HTTP_AUTHORIZATION="Bearer one,Bearer two")["status"], 401)
        self.assertEqual(self.call(HTTP_AUTHORIZATION="Bearer x\r\nInjected: true")["status"], 401)

    def test_rejects_inconsistent_forwarded_protocol(self):
        self.assertEqual(self.call(HTTP_X_FORWARDED_PROTO="http")["status"], 403)

    def test_public_origin_must_be_https(self):
        with self.assertRaises(ValueError):
            RemoteMCPGuard(lambda *_: [], self.verifier, public_origin="http://mcp.agentsteers.com")


if __name__ == "__main__":
    unittest.main()
