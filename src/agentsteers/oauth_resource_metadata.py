"""Opt-in OAuth protected-resource discovery (RFC 9728) for future MCP.

Not connected to the public Frappe route, Caddy or existing mock server.
The wrapped app MUST validate OAuth access tokens before MCP operations.
"""
from __future__ import annotations

import json
from urllib.parse import urlsplit

SCOPES = ("agentsteers:submit", "agentsteers:read", "agentsteers:cancel")
ROOT_PATH = "/.well-known/oauth-protected-resource"
MCP_PATH = ROOT_PATH + "/mcp"


def _url(value: str, *, allow_path: bool) -> str:
    if not isinstance(value, str):
        raise ValueError("HTTPS URL required")
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or
            parsed.password or parsed.query or parsed.fragment or
            parsed.port not in (None, 443) or
            (not allow_path and parsed.path not in ("", "/")) or
            any(ch in value for ch in "\\r\\n")):
        raise ValueError("HTTPS URL without credentials, query or fragment required")
    return value.rstrip("/")


def _response(start_response, status: str, body: bytes, *, content_type="application/json"):
    start_response(status, [
        ("Content-Type", content_type),
        ("Content-Length", str(len(body))),
        ("Cache-Control", "no-store"),
        ("X-Content-Type-Options", "nosniff"),
    ])
    return [body]


class ProtectedResourceDiscovery:
    """Serve public resource metadata and add a discovery pointer to 401s.

    This is not an authorization server or an OAuth login implementation.
    """

    def __init__(self, app, *, resource: str, authorization_server: str):
        resource = _url(resource, allow_path=True)
        issuer = _url(authorization_server, allow_path=True)
        parsed = urlsplit(resource)
        if parsed.path != "/mcp":
            raise ValueError("Resource identifier must be canonical HTTPS /mcp URL")
        self.app = app
        self.host = parsed.netloc.lower()
        self.metadata_url = f"https://{self.host}{ROOT_PATH}{MCP_PATH[len(ROOT_PATH):]}"
        self.body = json.dumps({
            "resource": resource,
            "authorization_servers": [issuer],
            "scopes_supported": list(SCOPES),
            "bearer_methods_supported": ["header"],
        }, separators=(",", ":")).encode("utf-8")

    def __call__(self, environ, start_response):
        # The trusted proxy must set the WSGI scheme. Never honor arbitrary
        # X-Forwarded-* headers directly from an Internet client.
        if (environ.get("wsgi.url_scheme") != "https" or
                environ.get("HTTP_HOST", "").lower() != self.host):
            return _response(start_response, "403 Forbidden", b"forbidden",
                             content_type="text/plain")
        path = environ.get("PATH_INFO")
        if path in (ROOT_PATH, MCP_PATH):
            if environ.get("REQUEST_METHOD") != "GET":
                return _response(start_response, "405 Method Not Allowed", b"",
                                 content_type="text/plain")
            return _response(start_response, "200 OK", self.body)
        if path != "/mcp":
            return _response(start_response, "404 Not Found", b"",
                             content_type="text/plain")

        def challenged(status, headers, exc_info=None):
            if status.startswith("401 "):
                headers = [(k, v) for k, v in headers if k.lower() != "www-authenticate"]
                headers.append(("WWW-Authenticate",
                                f'Bearer resource_metadata="{self.metadata_url}"'))
            return start_response(status, headers, exc_info)

        return self.app(environ, challenged)
