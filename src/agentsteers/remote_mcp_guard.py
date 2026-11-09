"""Opt-in WSGI boundary for a future HTTPS OAuth-protected MCP service.

Not wired to the public Frappe route. The verifier MUST validate signature,
issuer, audience, expiry and subject, e.g. AccessTokenVerifier. The upstream
proxy must set wsgi.url_scheme from a trusted connection, not client headers.
"""
from __future__ import annotations

from urllib.parse import urlsplit


def _reject(start_response, status: str, message: bytes):
    headers = [("Content-Type", "text/plain; charset=utf-8"),
               ("Cache-Control", "no-store"),
               ("X-Content-Type-Options", "nosniff"),
               ("Content-Length", str(len(message)))]
    start_response(status, headers)
    return [message]


class RemoteMCPGuard:
    """Authenticate before MCP processing; never authorize tasks by a client flag.

    This middleware is not sufficient to enable task tools: downstream must
    authorize scopes, repository access and persisted task ownership separately.
    """

    def __init__(self, app, verifier, *, public_origin: str):
        origin = urlsplit(public_origin)
        if (origin.scheme != "https" or not origin.hostname or
                origin.username or origin.password or origin.query or
                origin.fragment or origin.path not in ("", "/")):
            raise ValueError("public_origin must be an HTTPS origin")
        self.app = app
        self.verifier = verifier
        self.origin = f"https://{origin.netloc.lower()}"
        self.hostname = origin.netloc.lower()

    def __call__(self, environ, start_response):
        if environ.get("wsgi.url_scheme") != "https":
            return _reject(start_response, "403 Forbidden", b"https_required")
        if environ.get("HTTP_HOST", "").lower() != self.hostname:
            return _reject(start_response, "403 Forbidden", b"untrusted_host")
        if environ.get("HTTP_X_FORWARDED_PROTO") and environ.get("HTTP_X_FORWARDED_PROTO") != "https":
            return _reject(start_response, "403 Forbidden", b"untrusted_forwarded_proto")
        origin = environ.get("HTTP_ORIGIN")
        if origin is not None and origin != self.origin:
            return _reject(start_response, "403 Forbidden", b"untrusted_origin")
        auth = environ.get("HTTP_AUTHORIZATION", "")
        if not isinstance(auth, str) or "," in auth or "\r" in auth or "\n" in auth:
            return _reject(start_response, "401 Unauthorized", b"unauthorized")
        try:
            principal = self.verifier.verify(auth)
        except Exception:
            # Fail closed. Never expose token or verification errors to caller.
            return _reject(start_response, "401 Unauthorized", b"unauthorized")
        if not getattr(principal, "subject", None):
            return _reject(start_response, "401 Unauthorized", b"unauthorized")
        # Internal per-request context, not a caller-controlled HTTP header.
        environ["agentsteers.principal"] = principal
        return self.app(environ, start_response)
