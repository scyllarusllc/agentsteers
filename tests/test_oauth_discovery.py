"""Offline tests for opt-in OAuth protected-resource discovery."""
import io
import json
import unittest

from agentsteers.oauth_discovery import OAuthDiscovery, oauth_challenge_headers


def next_app(environ, start_response):
    start_response("204 No Content", [])
    return [b""]


class OAuthDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.app = OAuthDiscovery(
            next_app, resource="https://mcp.agentsteers.com/mcp",
            authorization_server="https://auth.agentsteers.com")

    def request(self, path, method="GET", scheme="https", host="mcp.agentsteers.com"):
        headers = []
        def start(status, h):
            headers.append((status, dict(h)))
        body = b"".join(self.app({
            "PATH_INFO": path, "REQUEST_METHOD": method, "wsgi.url_scheme": scheme,
            "HTTP_HOST": host, "wsgi.input": io.BytesIO(b"")
        }, start))
        return headers[0][0], headers[0][1], body

    def test_discovery(self):
        status, headers, body = self.request("/.well-known/oauth-protected-resource")
        self.assertEqual(status, "200 OK")
        self.assertEqual(headers["Cache-Control"], "no-store")
        doc = json.loads(body)
        self.assertEqual(doc["resource"], "https://mcp.agentsteers.com/mcp")
        self.assertEqual(doc["authorization_servers"], ["https://auth.agentsteers.com"])
        self.assertIn("agentsteers:submit", doc["scopes_supported"])

    def test_pass_through(self):
        self.assertEqual(self.request("/mcp")[0], "204 No Content")

    def test_reject_insecure_transport_or_host(self):
        self.assertEqual(self.request("/mcp", scheme="http")[0], "403 Forbidden")
        self.assertEqual(self.request("/mcp", host="evil.example")[0], "403 Forbidden")

    def test_reject_metadata_post(self):
        self.assertEqual(self.request("/.well-known/oauth-protected-resource", method="POST")[0],
                         "405 Method Not Allowed")

    def test_config_validation(self):
        for resource in ("http://mcp.agentsteers.com/mcp",
                         "https://mcp.agentsteers.com/other",
                         "https://user:secret@mcp.agentsteers.com/mcp"):
            with self.assertRaises(ValueError):
                OAuthDiscovery(next_app, resource=resource,
                               authorization_server="https://auth.agentsteers.com")

    def test_challenge(self):
        value = dict(oauth_challenge_headers(
            resource="https://mcp.agentsteers.com/mcp",
            scopes=("agentsteers:read",)))["WWW-Authenticate"]
        self.assertIn("resource_metadata=", value)
        self.assertIn('scope="agentsteers:read"', value)


if __name__ == "__main__":
    unittest.main()
