"""Offline OAuth Bridge tests. No Frappe login or HTTP server is invoked."""
import secrets
import unittest

from agentsteers.oauth_bridge_core import (
    OAuthBridgeCore, OAuthBridgeError, OAuthClient, RESOURCE, pkce_s256,
)


class TestBridge(unittest.TestCase):
    def setUp(self):
        self.now = 10000
        self.redirect = "https://chatgpt.com/connector/oauth/example"
        self.bridge = OAuthBridgeCore(
            issuer="https://auth.agentsteers.com",
            clients=(OAuthClient("my-client", frozenset({self.redirect}), "secret"),),
            clock=lambda: self.now,
        )
        self.verifier = secrets.token_urlsafe(48)

    def issue(self, **kwargs):
        params = dict(verified_subject="owner", client_id="my-client",
                      redirect_uri=self.redirect, resource=RESOURCE,
                      scopes=frozenset({"agentsteers:read"}),
                      code_challenge=pkce_s256(self.verifier),
                      code_challenge_method="S256")
        params.update(kwargs)
        return self.bridge.authorize(**params)

    def exchange(self, code, **kwargs):
        params = dict(code=code, client_id="my-client", client_secret="secret",
                      redirect_uri=self.redirect, resource=RESOURCE,
                      code_verifier=self.verifier)
        params.update(kwargs)
        return self.bridge.exchange(**params)

    def test_metadata_s256_and_https(self):
        d = self.bridge.metadata()
        self.assertEqual(d["code_challenge_methods_supported"], ["S256"])
        self.assertEqual(d["issuer"], "https://auth.agentsteers.com")

    def test_success_and_replay_rejection(self):
        code = self.issue()
        token = self.exchange(code)["access_token"]
        info = self.bridge.introspect(token, requesting_client_id="my-client",
                                      requesting_client_secret="secret")
        self.assertTrue(info["active"])
        self.assertEqual(info["aud"], RESOURCE)
        self.assertEqual(info["scope"], "agentsteers:read")
        with self.assertRaises(OAuthBridgeError):
            self.exchange(code)

    def test_wrong_verifier_consumes_code(self):
        code = self.issue()
        with self.assertRaises(OAuthBridgeError):
            self.exchange(code, code_verifier=secrets.token_urlsafe(48))
        with self.assertRaises(OAuthBridgeError):
            self.exchange(code)

    def test_expiry(self):
        code = self.issue()
        self.now += 91
        with self.assertRaises(OAuthBridgeError):
            self.exchange(code)
        token = self.exchange(self.issue())["access_token"]
        self.now += 601
        self.assertFalse(self.bridge.introspect(
            token, requesting_client_id="my-client",
            requesting_client_secret="secret")["active"])

    def test_invalid_resource_redirect_scopes_method(self):
        for overrides in ({"resource": "https://attacker.example/mcp"},
                          {"redirect_uri": "https://attacker.example/callback"},
                          {"scopes": frozenset({"admin"})},
                          {"code_challenge_method": "plain"},
                          {"verified_subject": ""}):
            with self.subTest(overrides=overrides):
                with self.assertRaises(OAuthBridgeError):
                    self.issue(**overrides)

    def test_client_secret_mismatch(self):
        code = self.issue()
        with self.assertRaises(OAuthBridgeError):
            self.exchange(code, client_secret="bad")
        self.exchange(code)

    def test_introspection_requires_confidential_client(self):
        token = self.exchange(self.issue())["access_token"]
        with self.assertRaises(OAuthBridgeError):
            self.bridge.introspect(token, requesting_client_id="my-client",
                                   requesting_client_secret="wrong")


if __name__ == "__main__":
    unittest.main()
