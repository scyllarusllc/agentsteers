"""Opt-in OAuth discovery/401 challenge wrapper for a future AgentSteers MCP.

Does not issue tokens, authenticate users, or enable public routes. Mount behind
a trusted HTTPS reverse proxy only after configuring a real authorization server.
"""
from __future__ import annotations

import json
from urllib.parse import urlsplit


class OAuthDiscovery:
    """Serve protected-resource metadata and an RFC 9728 Bearer challenge.

    Protect the actual MCP endpoint using RemoteMCPGuard and AccessTokenVerifier;
    this wrapper is metadata plumbing, not a substitute for either.
    """

    def __init__(self, app, *, resource: str, authorization_server: str,
                 scopes: tuple[str, ...] = ("agentsteers:read", "agentsteers:submit",
                                              "agentsteers:cancel")):
        for name, value in (("resource", resource), ("authorization_server", authorization_server)):
            parsed = urlsplit(value)
            if (parsed.scheme != "https" or not parsed.netloc or parsed.username or
                    parsed.password or parsed.query or parsed.fragment):
                raise ValueError(f"{name} must be an HTTPS URL without credentials or query")
        resource_url = urlsplit(resource)
        if resource_url.path != "/mcp":
            raise ValueError("resource must end with /mcp")
        if not scopes or any(not s or not isinstance(s, str) or '"' in s for s in scopes):
            raise ValueError("scopes must be nonempty safe strings")
        self.app = app
        self.resource = resource
        self.auth_server = authorization_server
        self.scopes = scopes
        self.host = resource_url.netloc.lower()
        # RFC 9728 inserts the well-known segment before the resource path.
        # Preserve the origin-level URL for older clients that use the
        # location from legacy WWW-Authenticate challenges.
        self.metadata_path = "/.well-known/oauth-protected-resource" + resource_url.path
        self.legacy_metadata_path = "/.well-known/oauth-protected-resource"

    @staticmethod
    def _send(start_response, status, payload, *, content_type="application/json"):
        start_response(status, [("Content-Type", content_type),
                                ("Cache-Control", "no-store"),
                                ("X-Content-Type-Options", "nosniff"),
                                ("Content-Length", str(len(payload)))])
        return [payload]

    def __call__(self, environ, start_response):
        # Do not trust client-controlled X-Forwarded-* headers.
        if (environ.get("wsgi.url_scheme") != "https" or
                environ.get("HTTP_HOST", "").lower() != self.host):
            return self._send(start_response, "403 Forbidden", b'{"error":"untrusted_transport"}')
        path = environ.get("PATH_INFO")
        if path in (self.metadata_path, self.legacy_metadata_path):
            if environ.get("REQUEST_METHOD") != "GET":
                return self._send(start_response, "405 Method Not Allowed",
                                  b'{"error":"method_not_allowed"}')
            payload = json.dumps({
                "resource": self.resource,
                "authorization_servers": [self.auth_server],
                "scopes_supported": list(self.scopes),
                "bearer_methods_supported": ["header"]
            }).encode("utf-8")
            return self._send(start_response, "200 OK", payload)
        return self.app(environ, start_response)


def oauth_challenge_headers(*, resource: str, scopes: tuple[str, ...] = ()) -> list[tuple[str, str]]:
    """Use on MCP HTTP 401 responses when OAuth is required.

    Caller MUST independently validate the OAuth token and authorize the task.
    """
    parsed = urlsplit(resource)
    if parsed.scheme != "https" or not parsed.netloc or parsed.path != "/mcp":
        raise ValueError("Expected HTTPS MCP resource")
    # RFC 9728: insert the well-known path between the origin and /mcp.
    metadata = (f"{parsed.scheme}://{parsed.netloc}"
                f"/.well-known/oauth-protected-resource{parsed.path}")
    scope_part = f', scope="{" ".join(scopes)}"' if scopes else ""
    return [("WWW-Authenticate", f'Bearer resource_metadata="{metadata}"{scope_part}')]
