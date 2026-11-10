"""No network or Frappe instance needed: negative tests for OAuth boundary."""
import base64
import hashlib
import time
import unittest
from dataclasses import replace

from agentsteers.frappe_oauth_compat import (
    RESOURCE, OAuthBridgeRejected, PendingAuthorization,
    RegisteredClient, verify_exchange, validate_introspection_claims,
)

REDIRECT = "https://chatgpt.com/connector/oauth/test-callback"
VERIFIER = "a" * 43
CHALLENGE = base64.urlsafe_b64encode(
    hashlib.sha256(VERIFIER.encode("ascii")).digest()
).rstrip(b"=").decode("ascii")
NOW = 1900000000.0


def registration():
    return RegisteredClient("test-client", "short", REDIRECT)


def pending():
    return PendingAuthorization(
        client_id="test-client", subject="owner@example.com",
        redirect_uri=REDIRECT, resource=RESOURCE, code_challenge=CHALLENGE,
        code_challenge_method="S256", scopes=frozenset(["agentsteers:read"]),
        expires_at=NOW + 60,
    )


def exchange(**changes):
    values = dict(registered=registration(), request_client_id="test-client",
                  request_client_secret="short", request_redirect_uri=REDIRECT,
                  request_resource=RESOURCE, code_verifier=VERIFIER,
                  pending=pending(), now=NOW)
    values.update(changes)
    return verify_exchange(**values)


class OAuthCompatibilityContractTests(unittest.TestCase):
    def test_valid_s256_and_short_provider_secret(self):
        self.assertIsNone(exchange())

    def test_bad_or_missing_secret(self):
        for secret in ("wrong", "", None):
            with self.subTest(secret=secret), self.assertRaises(OAuthBridgeRejected):
                exchange(request_client_secret=secret)

    def test_mismatched_client(self):
        for client in ("other", ""):
            with self.subTest(client=client), self.assertRaises(OAuthBridgeRejected):
                exchange(request_client_id=client)

    def test_redirect_must_match_registered_and_code(self):
        with self.assertRaises(OAuthBridgeRejected):
            exchange(request_redirect_uri="https://evil.example/callback")
        with self.assertRaises(OAuthBridgeRejected):
            exchange(pending=replace(pending(), redirect_uri="https://evil.example/callback"))

    def test_resource_binding(self):
        with self.assertRaises(OAuthBridgeRejected):
            exchange(request_resource="https://elsewhere.example/mcp")
        with self.assertRaises(OAuthBridgeRejected):
            exchange(pending=replace(pending(), resource="https://elsewhere.example/mcp"))

    def test_pkce_s256_required(self):
        for change in (dict(code_challenge_method="plain"),
                       dict(code_challenge="bad"),
                       dict(code_challenge="A" * 43)):
            with self.subTest(change=change), self.assertRaises(OAuthBridgeRejected):
                exchange(pending=replace(pending(), **change))
        for verifier in ("", "wrong", "a" * 42, "a" * 129, None):
            with self.subTest(verifier=verifier), self.assertRaises(OAuthBridgeRejected):
                exchange(code_verifier=verifier)

    def test_expiration_owner_and_scopes(self):
        with self.assertRaises(OAuthBridgeRejected):
            exchange(pending=replace(pending(), expires_at=NOW))
        with self.assertRaises(OAuthBridgeRejected):
            exchange(pending=replace(pending(), subject=""))
        for scopes in (frozenset(), frozenset(["openid", "all"])):
            with self.assertRaises(OAuthBridgeRejected):
                exchange(pending=replace(pending(), scopes=scopes))

    def test_invalid_registration(self):
        for redirect in ("http://chatgpt.com/connector/oauth/a",
                         "https://evil.example/path?code=1"):
            with self.assertRaises(ValueError):
                RegisteredClient("client", "secret", redirect)


class IntrospectionContractTests(unittest.TestCase):
    def setUp(self):
        self.claims = {
            "active": True, "exp": NOW + 60,
            "iss": "https://agentsteers.com", "sub": "owner@example.com",
            "client_id": "test-client", "aud": RESOURCE,
            "scope": "agentsteers:read",
        }

    def validate(self, **changes):
        return validate_introspection_claims(
            claims={**self.claims, **changes},
            issuer="https://agentsteers.com", client_id="test-client",
            subject_allowlist=frozenset(["owner@example.com"]), now=NOW
        )

    def test_correct_mcp_claims(self):
        self.assertEqual(self.validate(), ("owner@example.com", frozenset(["agentsteers:read"])))

    def test_frappe_missing_claims_rejected(self):
        for key in ("active", "exp", "iss", "sub", "client_id", "aud", "scope"):
            stripped = dict(self.claims)
            stripped.pop(key)
            with self.subTest(key=key), self.assertRaises(OAuthBridgeRejected):
                validate_introspection_claims(
                    claims=stripped, issuer="https://agentsteers.com",
                    client_id="test-client",
                    subject_allowlist=frozenset(["owner@example.com"]), now=NOW)

    def test_cross_client_resource_and_subject(self):
        for changed in (
            {"client_id": "other"}, {"aud": "test-client"},
            {"aud": "https://other.example/mcp"},
            {"sub": "stranger"}, {"scope": "openid all"},
            {"scope": "agentsteers:read admin"}, {"active": False},
            {"exp": NOW - 10},
        ):
            with self.subTest(changed=changed), self.assertRaises(OAuthBridgeRejected):
                self.validate(**changed)


if __name__ == "__main__":
    unittest.main()
