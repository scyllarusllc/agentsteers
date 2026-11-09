"""Test default-deny server configuration without real OAuth credentials."""
import unittest
from unittest.mock import patch

from agentsteers.oauth_mock_wsgi import build_application


class OAuthMockWSGITests(unittest.TestCase):
    def call(self, app):
        response = {}
        def start(status, headers):
            response["status"] = status
        response["body"] = b"".join(app({}, start))
        return response

    def test_disabled_without_explicit_enable(self):
        self.assertTrue(self.call(build_application({}))["status"].startswith("503"))

    def test_missing_configuration_denied(self):
        self.assertTrue(self.call(build_application({
            "AGENTSTEERS_OAUTH_MOCK_ENABLED": "1"
        }))["status"].startswith("503"))

    def test_wrong_audience_denied_without_verifier(self):
        conf = {
            "AGENTSTEERS_OAUTH_MOCK_ENABLED": "1",
            "AGENTSTEERS_OAUTH_ISSUER": "https://auth.example",
            "AGENTSTEERS_OAUTH_AUDIENCE": "https://other.example/mcp",
            "AGENTSTEERS_OAUTH_JWKS_URL": "https://auth.example/jwks",
            "AGENTSTEERS_OAUTH_AUTHORIZATION_SERVER": "https://auth.example",
            "AGENTSTEERS_OAUTH_SUBJECTS": "owner",
            "AGENTSTEERS_OAUTH_REPOS": "scyllarusllc/agentsteers"
        }
        with patch("agentsteers.oauth_mock_wsgi.AccessTokenVerifier") as verifier:
            self.assertTrue(self.call(build_application(conf))["status"].startswith("503"))
            verifier.assert_not_called()


if __name__ == "__main__":
    unittest.main()
