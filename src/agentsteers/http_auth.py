"""Single-tenant *development-only* ASGI guard for loopback MCP HTTP.

Not OAuth, not multi-user authorization, and never suitable for public exposure.
"""
from __future__ import annotations
import hmac

_ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost"})

class LoopbackBearerGuard:
    def __init__(self, app, token: str):
        if not isinstance(token, str) or len(token) < 32 or any(c in token for c in "\r\n"):
            raise ValueError("A random bearer token of at least 32 characters is required")
        self.app, self.token = app, token

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            # Preserve ASGI lifespan for the underlying MCP server.
            await self.app(scope, receive, send)
            return
        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        host = headers.get(b"host", b"").decode("latin1").split(":")[0].lower()
        if host not in _ALLOWED_HOSTS:
            await self._reject(send, 403, b"untrusted_host")
            return
        # Browser-initiated requests should never be accepted from foreign origins.
        origin = headers.get(b"origin")
        if origin:
            from urllib.parse import urlparse
            parsed = urlparse(origin.decode("latin1"))
            if parsed.scheme != "http" or parsed.hostname not in _ALLOWED_HOSTS:
                await self._reject(send, 403, b"untrusted_origin")
                return
        bearer = headers.get(b"authorization", b"").decode("latin1")
        expected = "Bearer " + self.token
        if not hmac.compare_digest(bearer.encode(), expected.encode()):
            await self._reject(send, 401, b"unauthorized")
            return
        await self.app(scope, receive, send)

    @staticmethod
    async def _reject(send, code: int, body: bytes):
        await send({"type": "http.response.start", "status": code,
                    "headers": [(b"content-type", b"text/plain; charset=utf-8"),
                                (b"cache-control", b"no-store")]})
        await send({"type": "http.response.body", "body": body})
