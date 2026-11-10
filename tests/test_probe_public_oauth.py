"""Offline tests for the credential-free public OAuth discovery probe."""
import io
import json
import unittest

from scripts.probe_public_oauth import (
    PublicOAuthProbeError, RESOURCE, main, probe, validate_resource_metadata,
)

ISSUER = "https://frappe.example.test"
RESOURCE_METADATA_URL = (
    "https://mcp.agentsteers.com/.well-known/oauth-protected-resource/mcp"
)
ISSUER_METADATA_URL = ISSUER + "/.well-known/oauth-authorization-server"


def resource_metadata(**overrides):
    result = {
        "resource": RESOURCE,
        "authorization_servers": [ISSUER],
        "scopes_supported": [
            "agentsteers:read", "agentsteers:submit", "agentsteers:cancel",
        ],
        "bearer_methods_supported": ["header"],
    }
    result.update(overrides)
    return result


def authorization_metadata(**overrides):
    result = {
        "issuer": ISSUER,
        "authorization_endpoint": (
            ISSUER + "/api/method/frappe.integrations.oauth2.authorize"
        ),
        "token_endpoint": ISSUER + "/api/method/frappe.integrations.oauth2.get_token",
        "introspection_endpoint": (
            ISSUER + "/api/method/frappe.integrations.oauth2.introspect_token"
        ),
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["client_secret_basic"],
        "introspection_endpoint_auth_methods_supported": ["client_secret_basic"],
    }
    result.update(overrides)
    return result


class FakeResponse:
    def __init__(self, data, *, status=200, content_type="application/json"):
        self.status = status
        self.headers = {"Content-Type": content_type}
        self._stream = io.BytesIO(
            data if isinstance(data, bytes) else json.dumps(data).encode()
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, count=-1):
        return self._stream.read(count)


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.documents = {
            RESOURCE_METADATA_URL: resource_metadata(),
            ISSUER_METADATA_URL: authorization_metadata(),
        }
        self.requests = []

    def opener(self, request, timeout):
        self.requests.append(request)
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.get_header("Accept"), "application/json")
        self.assertEqual(timeout, 5)
        self.assertIsNone(request.get_header("Authorization"))
        return FakeResponse(self.documents[request.full_url])

    def test_passes_two_exact_credential_free_discovery_requests(self):
        probe(issuer=ISSUER, opener=self.opener)
        self.assertEqual(
            [request.full_url for request in self.requests],
            [RESOURCE_METADATA_URL, ISSUER_METADATA_URL],
        )

    def test_rejects_resource_owner_or_scope_mismatch_before_frappe_fetch(self):
        bad = [
            {"resource": "https://other.example.test/mcp"},
            {"authorization_servers": ["https://evil.example.test"]},
            {"scopes_supported": ["agentsteers:read"]},
            {"scopes_supported": "agentsteers:read"},
            {"bearer_methods_supported": ["query"]},
        ]
        for update in bad:
            with self.subTest(update=update):
                self.requests.clear()
                self.documents[RESOURCE_METADATA_URL] = resource_metadata(**update)
                with self.assertRaises(PublicOAuthProbeError):
                    probe(issuer=ISSUER, opener=self.opener)
                self.assertEqual(len(self.requests), 1)
        self.documents[RESOURCE_METADATA_URL] = resource_metadata()

    def test_fails_closed_for_missing_pkce_or_wrong_frappe_issuer(self):
        for update in (
            {"code_challenge_methods_supported": ["plain"]},
            {"issuer": "https://evil.example.test"},
            {"introspection_endpoint": "https://evil.example.test/api/introspect"},
        ):
            with self.subTest(update=update):
                self.documents[ISSUER_METADATA_URL] = authorization_metadata(**update)
                with self.assertRaises(ValueError):
                    probe(issuer=ISSUER, opener=self.opener)

    def test_non_https_and_unexpected_issuer_rejected_without_requests(self):
        for issuer in (
            "http://frappe.example.test",
            "https://user:pass@frappe.example.test",
            "https://frappe.example.test/",
            "https://frappe.example.test?token=abc",
            "",
        ):
            with self.subTest(issuer=issuer):
                with self.assertRaises(PublicOAuthProbeError):
                    probe(issuer=issuer, opener=self.opener)
        self.assertEqual(self.requests, [])

    def test_bad_http_status_mime_and_large_response_fail_closed(self):
        for response in (
            FakeResponse({}, status=302),
            FakeResponse({}, content_type="text/html"),
            FakeResponse(b"x" * 65537),
            FakeResponse(b"not json"),
        ):
            with self.subTest(status=response.status, mime=response.headers["Content-Type"]):
                with self.assertRaises(PublicOAuthProbeError):
                    probe(issuer=ISSUER, opener=lambda *_a, **_kw: response)

    def test_network_failure_reports_generic_error(self):
        def offline(*args, **kwargs):
            raise OSError("fake sensitive diagnostic")
        with self.assertRaisesRegex(PublicOAuthProbeError, "HTTPS discovery request failed") as ctx:
            probe(issuer=ISSUER, opener=offline)
        self.assertNotIn("fake sensitive diagnostic", str(ctx.exception))

    def test_validation_rejects_unknown_metadata_structures(self):
        for obj in (None, [], {}, {"resource": RESOURCE}, resource_metadata(scopes_supported=[None])):
            with self.subTest(obj=obj):
                with self.assertRaises(PublicOAuthProbeError):
                    validate_resource_metadata(obj, issuer=ISSUER)


if __name__ == "__main__":
    unittest.main()
