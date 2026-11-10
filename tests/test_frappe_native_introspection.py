"""Offline tests for the explicitly configured Frappe native introspection format.

The Frappe develop source returns active/exp/client_id/scope and includes sub
when openid was granted; iss/aud are not guaranteed. These tests are NOT
evidence of a deployed Frappe v17 instance or an actual ChatGPT OAuth login.
"""
import io
import json
import time
import unittest

from agentsteers.frappe_oauth import FrappeTokenVerifier
from agentsteers.oauth_security import AuthorizationError
from agentsteers.frappe_oauth_wsgi import build_application
from scripts.check_frappe_mcp_auth import validate

ISSUER = "https://frappe.example.test"
RESOURCE = "https://mcp.agentsteers.com/mcp"


class FakeResponse:
    status = 200

    def __init__(self, payload):
        self.stream = io.BytesIO(json.dumps(payload).encode())

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, n=-1):
        return self.stream.read(n)


def native_claims(**changes):
    data = {
        "active": True,
        "exp": time.time() + 180,
        "client_id": "dedicated-mcp-client",
        "sub": "allowed-user",
        "scope": "openid agentsteers:read agentsteers:submit",
    }
    data.update(changes)
    return data


def verifier(data, *, mode="frappe_native"):
    def opener(request, timeout):
        assert request.get_method() == "POST"
        assert request.full_url == ISSUER + "/api/method/frappe.integrations.oauth2.introspect_token"
        assert request.get_header("Authorization").startswith("Basic ")
        assert timeout <= 5
        return FakeResponse(data)

    return FrappeTokenVerifier(
        issuer=ISSUER, client_id="dedicated-mcp-client",
        client_secret="test-secret-not-real", allowed_subjects={"allowed-user"},
        opener=opener, claim_mode=mode,
    )


class NativeIntrospectionTests(unittest.TestCase):
    def test_native_response_without_iss_or_aud(self):
        principal = verifier(native_claims()).verify("Bearer test-access-token")
        self.assertEqual(principal.subject, "allowed-user")
        self.assertIn("agentsteers:read", principal.scopes)

    def test_strict_mode_still_rejects_omitted_issuer_and_audience(self):
        with self.assertRaises(AuthorizationError):
            verifier(native_claims(), mode="strict").verify("Bearer test-token")
        with self.assertRaises(AuthorizationError):
            verifier(native_claims(iss=ISSUER), mode="strict").verify("Bearer test-token")

    def test_native_mode_rejects_present_wrong_claims(self):
        invalid = [
            {"active": False},
            {"exp": time.time() - 10},
            {"client_id": "another-client"},
            {"sub": "another-user"},
            {"sub": None},
            {"scope": "openid all"},
            {"scope": "agentsteers:read"},
            {"iss": "https://wrong.example.test"},
            {"aud": "another-client"},
            {"aud": None},
        ]
        for fields in invalid:
            with self.subTest(fields=fields):
                with self.assertRaises(AuthorizationError):
                    verifier(native_claims(**fields)).verify("Bearer test-token")

    def test_native_mode_checks_optional_present_valid_claims(self):
        principal = verifier(native_claims(iss=ISSUER, aud=["dedicated-mcp-client"])).verify(
            "Bearer test-token"
        )
        self.assertEqual(principal.subject, "allowed-user")

    def test_unknown_mode_fails_before_token_verification(self):
        with self.assertRaises(ValueError):
            verifier(native_claims(), mode="guess")

    def test_wsgi_configuration_opt_in_and_preflight(self):
        env = {
            "AGENTSTEERS_FRAPPE_OAUTH_ENABLED": "1",
            "AGENTSTEERS_FRAPPE_ISSUER": ISSUER,
            "AGENTSTEERS_FRAPPE_CLIENT_ID": "dedicated-mcp-client",
            "AGENTSTEERS_FRAPPE_CLIENT_SECRET": "test-secret-not-real",
            "AGENTSTEERS_FRAPPE_SUBJECTS": "allowed-user",
            "AGENTSTEERS_FRAPPE_REPOS": "scyllarusllc/agentsteers",
            "AGENTSTEERS_FRAPPE_MCP_RESOURCE": RESOURCE,
            "AGENTSTEERS_FRAPPE_INTROSPECTION_FORMAT": "frappe_native",
        }
        self.assertTrue(validate(env))
        app = build_application(env, opener=lambda req, timeout: FakeResponse(native_claims()))
        self.assertTrue(callable(app))
        env["AGENTSTEERS_FRAPPE_INTROSPECTION_FORMAT"] = "allow_any"
        with self.assertRaises(ValueError):
            validate(env)
        unavailable = build_application(env)
        captured = {}
        body = b"".join(unavailable({}, lambda status, headers: captured.update(status=status)))
        self.assertTrue(captured["status"].startswith("503"))
        self.assertIn(b"not_configured", body)


if __name__ == "__main__":
    unittest.main()
