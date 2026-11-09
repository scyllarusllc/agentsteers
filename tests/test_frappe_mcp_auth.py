"""Offline tests for Frappe OAuth opaque token verification and isolated WSGI."""
import io
import json
import time
import unittest
from unittest.mock import patch

from agentsteers.frappe_oauth import FrappeTokenVerifier
from agentsteers.oauth_security import AuthorizationError
from agentsteers.frappe_oauth_wsgi import build_application
from agentsteers.oauth_mock_mcp import OAuthMockMCP
from agentsteers.oauth_security import Principal

ISSUER = "https://frappe.example.test"
RESOURCE = "https://mcp.agentsteers.com/mcp"


class FakeResponse:
    status = 200
    def __init__(self, data):
        self._stream = io.BytesIO(json.dumps(data).encode())
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, amount=-1):
        return self._stream.read(amount)


def claims(**changes):
    result = {
        "active": True, "exp": time.time() + 300, "iat": time.time() - 10,
        "iss": ISSUER, "sub": "owner", "client_id": "mcp-client",
        "aud": ["mcp-client"], "scope": "agentsteers:read agentsteers:submit agentsteers:cancel",
    }
    result.update(changes)
    return result


def make_verifier(data):
    def opener(request, timeout):
        assert request.full_url == ISSUER + "/api/method/frappe.integrations.oauth2.introspect_token"
        assert request.get_method() == "POST"
        assert timeout > 0
        return FakeResponse(data)
    return FrappeTokenVerifier(
        issuer=ISSUER, client_id="mcp-client", client_secret="s" * 32,
        allowed_subjects={"owner"}, opener=opener)


class FrappeAuthTests(unittest.TestCase):
    def test_valid_token(self):
        p = make_verifier(claims()).verify("Bearer opaque-access-token")
        self.assertEqual(p.subject, "owner")
        self.assertIn("agentsteers:read", p.scopes)

    def test_invalid_claims_fail_closed(self):
        samples = [
            {"active": False}, {"exp": time.time() - 2},
            {"iss": "https://other.example"}, {"sub": "other"},
            {"client_id": "unrelated"}, {"aud": ["unrelated"]},
            {"scope": "openid all"}, {"scope": None},
        ]
        for values in samples:
            with self.subTest(values=values):
                with self.assertRaises(AuthorizationError):
                    make_verifier(claims(**values)).verify("Bearer valid-token")

    def test_header_rejected(self):
        for header in (None, "", "Basic xyz", "Bearer ", "Bearer a b", "Bearer a\\nb"):
            with self.subTest(header=header):
                with self.assertRaises(AuthorizationError):
                    make_verifier(claims()).verify(header)

    def test_unavailable_introspection_denied(self):
        def unavailable(*args, **kwargs):
            raise OSError("offline")
        verifier = FrappeTokenVerifier(issuer=ISSUER, client_id="mcp-client",
                                      client_secret="s" * 32, allowed_subjects={"owner"},
                                      opener=unavailable)
        with self.assertRaises(AuthorizationError):
            verifier.verify("Bearer opaque")

    def test_wsgi_disabled_or_missing_config(self):
        for env in ({}, {"AGENTSTEERS_FRAPPE_OAUTH_ENABLED": "1"}):
            output = {}
            def start(status, headers):
                output["status"] = status
            body = b"".join(build_application(env)({}, start))
            self.assertIn("503", output["status"])
            self.assertIn(b"not_configured", body)

    def test_wsgi_valid_config_creates_app(self):
        env = {
            "AGENTSTEERS_FRAPPE_OAUTH_ENABLED": "1",
            "AGENTSTEERS_FRAPPE_ISSUER": ISSUER,
            "AGENTSTEERS_FRAPPE_CLIENT_ID": "mcp-client",
            "AGENTSTEERS_FRAPPE_CLIENT_SECRET": "s" * 32,
            "AGENTSTEERS_FRAPPE_SUBJECTS": "owner",
            "AGENTSTEERS_FRAPPE_REPOS": "scyllarusllc/agentsteers",
            "AGENTSTEERS_FRAPPE_MCP_RESOURCE": RESOURCE,
        }
        with patch("agentsteers.frappe_oauth_wsgi.FrappeTokenVerifier") as cls:
            cls.return_value = make_verifier(claims())
            app = build_application(env)
            self.assertTrue(callable(app))
            cls.assert_called_once()


if __name__ == "__main__":
    unittest.main()
