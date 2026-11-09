import json
import unittest

from agentsteers.oauth_resource_metadata import (
    ProtectedResourceDiscovery, ROOT_PATH, MCP_PATH,
)


class ProtectedResourceTests(unittest.TestCase):
    def setUp(self):
        def protected(environ, respond):
            respond("401 Unauthorized", [("Content-Type", "text/plain")])
            return [b"unauthorized"]
        self.app = ProtectedResourceDiscovery(
            protected, resource="https://mcp.agentsteers.com/mcp",
            authorization_server="https://auth.example.com")

    def call(self, path, method="GET", host="mcp.agentsteers.com", scheme="https"):
        captured = {}
        def respond(status, headers, exc_info=None):
            captured["status"], captured["headers"] = status, dict(headers)
        body = b"".join(self.app({
            "PATH_INFO": path, "REQUEST_METHOD": method,
            "HTTP_HOST": host, "wsgi.url_scheme": scheme,
        }, respond))
        return captured["status"], captured["headers"], body

    def test_discovery_paths(self):
        for path in (ROOT_PATH, MCP_PATH):
            with self.subTest(path=path):
                status, headers, body = self.call(path)
                data = json.loads(body)
                self.assertEqual(status, "200 OK")
                self.assertEqual(data["resource"], "https://mcp.agentsteers.com/mcp")
                self.assertEqual(data["authorization_servers"], ["https://auth.example.com"])
                self.assertIn("agentsteers:read", data["scopes_supported"])
                self.assertEqual(headers["Cache-Control"], "no-store")

    def test_unauthorized_challenge(self):
        status, headers, _ = self.call("/mcp", "POST")
        self.assertEqual(status, "401 Unauthorized")
        self.assertIn('resource_metadata="https://mcp.agentsteers.com/.well-known/oauth-protected-resource/mcp"',
                      headers["WWW-Authenticate"])

    def test_untrusted_connection_rejected(self):
        for host, scheme in (("evil.example", "https"), ("mcp.agentsteers.com", "http")):
            with self.subTest(host=host, scheme=scheme):
                self.assertEqual(self.call(ROOT_PATH, host=host, scheme=scheme)[0],
                                 "403 Forbidden")

    def test_other_paths_and_methods(self):
        self.assertEqual(self.call(ROOT_PATH, "POST")[0], "405 Method Not Allowed")
        self.assertEqual(self.call("/private")[0], "404 Not Found")

    def test_invalid_configuration_rejected(self):
        for issuer in ("http://auth.example.com", "https://auth.example.com/?x=1",
                       "https://user:pass@auth.example.com"):
            with self.subTest(issuer=issuer), self.assertRaises(ValueError):
                ProtectedResourceDiscovery(lambda e, r: [], resource="https://mcp.agentsteers.com/mcp",
                                           authorization_server=issuer)
        with self.assertRaises(ValueError):
            ProtectedResourceDiscovery(lambda e, r: [], resource="https://mcp.agentsteers.com/",
                                       authorization_server="https://auth.example.com")


if __name__ == "__main__":
    unittest.main()
