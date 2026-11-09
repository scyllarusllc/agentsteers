"""Frappe opaque OAuth access-token verifier for AgentSteers Mock MCP.

Fail-closed: checks introspection via a confidential OAuth client. This is a
resource-server adapter, NOT a Frappe authorization-server implementation.
No network calls occur on import or construction. Never logs tokens/secrets.
"""
from __future__ import annotations

import base64
import json
import time
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from agentsteers.oauth_security import AuthorizationError, Principal

MAX_TOKEN_LENGTH = 4096
MAX_RESPONSE_BYTES = 32768
ACTION_SCOPES = frozenset(("agentsteers:read", "agentsteers:submit", "agentsteers:cancel"))


def _valid_https(url):
    p = urlsplit(url)
    return (p.scheme == "https" and bool(p.hostname) and not p.username
            and not p.password and not p.query and not p.fragment
            and not p.path.endswith("/"))


class FrappeTokenVerifier:
    """Validate opaque Bearer tokens using Frappe's OAuth introspection API.

    The expected OAuth client_id is a dedicated MCP-only client. Frappe's
    introspection 'aud' may be the OAuth client_id, not the MCP resource URI.
    Because this cannot establish a resource-indicator audience by itself,
    only tokens issued to the dedicated client are accepted.
    """

    def __init__(self, *, issuer: str, client_id: str, client_secret: str,
                 allowed_subjects, required_scopes=ACTION_SCOPES, timeout=4,
                 opener=None):
        if not _valid_https(issuer):
            raise ValueError("HTTPS Frappe issuer required")
        if not isinstance(client_id, str) or not client_id.strip() or not client_secret:
            raise ValueError("Confidential Frappe OAuth client credentials required")
        if not isinstance(client_secret, str) or any(c in client_secret for c in "\r\n"):
            raise ValueError("Invalid client credentials")
        if not allowed_subjects:
            raise ValueError("Explicit Frappe owner allowlist required")
        self.issuer = issuer
        self.client_id = client_id
        self._secret = client_secret
        self.allowed_subjects = frozenset(allowed_subjects)
        self.required_scopes = frozenset(required_scopes)
        self.timeout = timeout
        self._opener = opener or urlopen
        self.endpoint = issuer + "/api/method/frappe.integrations.oauth2.introspect_token"

    def verify(self, authorization_header: str | None) -> Principal:
        if not isinstance(authorization_header, str):
            raise AuthorizationError("Missing Bearer token")
        scheme, sep, token = authorization_header.partition(" ")
        if (scheme.lower() != "bearer" or not sep or not token or
                token != token.strip() or len(token) > MAX_TOKEN_LENGTH or
                any(c in token for c in "\r\n, ")):
            raise AuthorizationError("Invalid Bearer token")
        credentials = base64.b64encode(
            (self.client_id + ":" + self._secret).encode("utf-8")).decode("ascii")
        body = urlencode({"token": token, "token_type_hint": "access_token"}).encode("ascii")
        request = Request(self.endpoint, data=body, method="POST", headers={
            "Authorization": "Basic " + credentials,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json"
        })
        try:
            with self._opener(request, timeout=self.timeout) as response:
                if getattr(response, "status", 200) != 200:
                    raise AuthorizationError("Introspection rejected")
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise AuthorizationError("Oversize introspection response")
            claims = json.loads(raw)
        except AuthorizationError:
            raise
        except (OSError, ValueError, TypeError) as exc:
            raise AuthorizationError("Introspection failed") from exc
        if not isinstance(claims, dict) or claims.get("active") is not True:
            raise AuthorizationError("Inactive token")
        now = time.time()
        exp = claims.get("exp")
        if isinstance(exp, bool) or not isinstance(exp, (int, float)) or exp <= now:
            raise AuthorizationError("Expired or unbounded token")
        issued = claims.get("iat")
        if issued is not None and (not isinstance(issued, (int, float))
                                   or isinstance(issued, bool) or issued > now + 60):
            raise AuthorizationError("Invalid issue time")
        if claims.get("iss") != self.issuer:
            raise AuthorizationError("Wrong token issuer")
        subject = claims.get("sub")
        if not isinstance(subject, str) or subject not in self.allowed_subjects:
            raise AuthorizationError("Unknown token owner")
        if claims.get("client_id") != self.client_id:
            raise AuthorizationError("Wrong OAuth client")
        audience = claims.get("aud")
        audiences = (audience,) if isinstance(audience, str) else audience
        if not isinstance(audiences, (list, tuple)) or self.client_id not in audiences:
            raise AuthorizationError("Wrong token audience")
        scope = claims.get("scope")
        if not isinstance(scope, str):
            raise AuthorizationError("Invalid token scopes")
        scopes = frozenset(scope.split())
        # Do not elevate Frappe's 'openid all' to AgentSteers MCP permissions.
        if not scopes.intersection(self.required_scopes):
            raise AuthorizationError("MCP scopes missing")
        return Principal(subject=subject, scopes=scopes)
