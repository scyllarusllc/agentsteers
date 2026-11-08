import unittest
from unittest.mock import Mock, patch

from agentsteers.oauth_security import (
    AccessTokenVerifier, AuthorizationError, Principal, authorize_task
)


class OAuthSecurityTests(unittest.TestCase):
    def test_configuration_fails_closed(self):
        with self.assertRaises(ValueError):
            AccessTokenVerifier(issuer="http://insecure", audience="https://mcp.agentsteers.com",
                                jwks_url="https://issuer.example/jwks", allowed_subjects={"owner"})

    @patch("agentsteers.oauth_security.PyJWKClient")
    @patch("agentsteers.oauth_security.jwt.decode")
    def test_valid_access_token(self, decode, jwks):
        jwks.return_value.get_signing_key_from_jwt.return_value.key = "key"
        decode.return_value = {"sub": "owner", "scope": "agentsteers:read"}
        verifier = AccessTokenVerifier(
            issuer="https://auth.example", audience="https://mcp.agentsteers.com",
            jwks_url="https://auth.example/jwks", allowed_subjects={"owner"})
        self.assertEqual(verifier.verify("Bearer signed-token").subject, "owner")
        decode.assert_called_once()
        self.assertEqual(decode.call_args.kwargs["audience"], "https://mcp.agentsteers.com")
        self.assertEqual(decode.call_args.kwargs["algorithms"], ["RS256"])

    @patch("agentsteers.oauth_security.PyJWKClient")
    @patch("agentsteers.oauth_security.jwt.decode")
    def test_unknown_subject_rejected(self, decode, jwks):
        jwks.return_value.get_signing_key_from_jwt.return_value.key = "key"
        decode.return_value = {"sub": "stranger", "scope": "agentsteers:submit"}
        verifier = AccessTokenVerifier(
            issuer="https://auth.example", audience="https://mcp.agentsteers.com",
            jwks_url="https://auth.example/jwks", allowed_subjects={"owner"})
        with self.assertRaises(AuthorizationError):
            verifier.verify("Bearer signed-token")

    @patch("agentsteers.oauth_security.PyJWKClient")
    def test_missing_header_rejected(self, jwks):
        verifier = AccessTokenVerifier(
            issuer="https://auth.example", audience="https://mcp.agentsteers.com",
            jwks_url="https://auth.example/jwks", allowed_subjects={"owner"})
        with self.assertRaises(AuthorizationError):
            verifier.verify(None)
        with self.assertRaises(AuthorizationError):
            verifier.verify("Basic secret")

    def test_task_permissions_default_deny(self):
        caller = Principal("owner", frozenset({"agentsteers:submit", "agentsteers:read"}))
        authorize_task(caller, action="submit_task", repository="org/allowed",
                       repository_allowlist={"org/allowed"})
        for change in (
            dict(action="cancel_task", repository="org/allowed"),
            dict(action="submit_task", repository="org/other"),
            dict(action="get_task_result", repository="org/allowed"),
            dict(action="get_task_status", repository="org/allowed", task_owner="another"),
            dict(action="arbitrary_shell", repository="org/allowed"),
        ):
            with self.subTest(change=change), self.assertRaises(AuthorizationError):
                authorize_task(caller, repository_allowlist={"org/allowed"}, **change)
        authorize_task(caller, action="get_task_result", repository="org/allowed",
                       repository_allowlist={"org/allowed"}, task_owner="owner")


if __name__ == "__main__":
    unittest.main()
