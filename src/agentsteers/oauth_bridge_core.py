"""Unmounted OAuth 2.1 bridge primitives for AgentSteers.

No HTTP login, Frappe identity adapter or public MCP route exists here.
The caller MUST independently authenticate and authorize a Frappe user before
calling authorize(). In-memory storage is development-only: replace with a
durable, atomic shared store before multi-worker/public deployment.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import hmac
import re
import secrets
from threading import RLock
import time
from urllib.parse import urlsplit

RESOURCE = "https://mcp.agentsteers.com/mcp"
SCOPES = frozenset({"agentsteers:read", "agentsteers:submit", "agentsteers:cancel"})
_B64URL = re.compile(r"^[A-Za-z0-9_-]{43,128}$")
_CODE_TTL = 90
_TOKEN_TTL = 600


class OAuthBridgeError(ValueError):
    """Invalid OAuth grant, client or request."""


def pkce_s256(verifier: str) -> str:
    if not isinstance(verifier, str) or not re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", verifier):
        raise OAuthBridgeError("invalid PKCE verifier")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


@dataclass(frozen=True)
class OAuthClient:
    client_id: str
    redirect_uris: frozenset[str]
    client_secret: str | None = None

    def __post_init__(self):
        if (not self.client_id or not self.redirect_uris or
                any(not isinstance(uri, str) or not uri.startswith("https://") or
                    urlsplit(uri).fragment or urlsplit(uri).username or
                    urlsplit(uri).password for uri in self.redirect_uris)):
            raise ValueError("client requires exact HTTPS redirect URIs")
        if self.client_secret is not None and not self.client_secret:
            raise ValueError("invalid client secret")


@dataclass(frozen=True)
class _Code:
    subject: str
    client_id: str
    redirect_uri: str
    resource: str
    scopes: frozenset[str]
    challenge: str
    expires: float


@dataclass(frozen=True)
class _Token:
    subject: str
    client_id: str
    resource: str
    scopes: frozenset[str]
    expires: float


class OAuthBridgeCore:
    """Single-process, development-only grant/token engine.

    authorize() is a trusted internal method, NEVER an HTTP endpoint.
    The separately audited HTTP adapter must bind a verified Frappe session,
    state/CSRF, user consent and authorization to the OAuth client.
    """

    def __init__(self, *, issuer: str, clients: tuple[OAuthClient, ...], clock=None):
        parts = urlsplit(issuer)
        if (parts.scheme != "https" or not parts.hostname or parts.username or
                parts.password or parts.path.strip("/") or parts.query or parts.fragment):
            raise ValueError("HTTPS issuer origin required")
        if not clients or len({c.client_id for c in clients}) != len(clients):
            raise ValueError("unique OAuth clients required")
        self.issuer = issuer.rstrip("/")
        self.clients = {c.client_id: c for c in clients}
        self._clock = clock or time.time
        self._codes: dict[str, _Code] = {}
        self._tokens: dict[str, _Token] = {}
        self._lock = RLock()

    def metadata(self) -> dict:
        return {
            "issuer": self.issuer,
            "authorization_endpoint": self.issuer + "/oauth/authorize",
            "token_endpoint": self.issuer + "/oauth/token",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["client_secret_post", "none"],
            "scopes_supported": sorted(SCOPES),
        }

    def authorize(self, *, verified_subject: str, client_id: str,
                  redirect_uri: str, resource: str, scopes: frozenset[str],
                  code_challenge: str, code_challenge_method: str) -> str:
        """Issue code only AFTER trusted caller verifies Frappe identity/consent."""
        client = self.clients.get(client_id)
        if (not isinstance(verified_subject, str) or not verified_subject.strip() or
                len(verified_subject) > 256 or not client or
                redirect_uri not in client.redirect_uris or resource != RESOURCE or
                not isinstance(scopes, frozenset) or not scopes or not scopes <= SCOPES or
                code_challenge_method != "S256" or
                not isinstance(code_challenge, str) or not _B64URL.fullmatch(code_challenge)):
            raise OAuthBridgeError("invalid authorization request")
        code = secrets.token_urlsafe(48)
        with self._lock:
            self._codes[hashlib.sha256(code.encode()).hexdigest()] = _Code(
                verified_subject, client_id, redirect_uri, resource,
                scopes, code_challenge, self._clock() + _CODE_TTL,
            )
        return code

    def exchange(self, *, code: str, client_id: str, client_secret: str | None,
                 redirect_uri: str, resource: str, code_verifier: str) -> dict:
        client = self.clients.get(client_id)
        if not client or not isinstance(code, str) or len(code) > 256:
            raise OAuthBridgeError("invalid grant")
        if client.client_secret is not None and (
            not isinstance(client_secret, str) or
            not hmac.compare_digest(client.client_secret, client_secret)
        ):
            raise OAuthBridgeError("invalid client")
        if client.client_secret is None and client_secret is not None:
            raise OAuthBridgeError("invalid client")
        key = hashlib.sha256(code.encode()).hexdigest()
        # Atomic consumption before examining the grant. Replays always fail.
        with self._lock:
            grant = self._codes.pop(key, None)
            if (grant is None or self._clock() >= grant.expires or
                    client_id != grant.client_id or redirect_uri != grant.redirect_uri or
                    resource != grant.resource or
                    not hmac.compare_digest(pkce_s256(code_verifier), grant.challenge)):
                raise OAuthBridgeError("invalid grant")
            token = secrets.token_urlsafe(48)
            self._tokens[hashlib.sha256(token.encode()).hexdigest()] = _Token(
                grant.subject, grant.client_id, grant.resource, grant.scopes,
                self._clock() + _TOKEN_TTL,
            )
        return {"access_token": token, "token_type": "Bearer", "expires_in": _TOKEN_TTL,
                "scope": " ".join(sorted(grant.scopes))}

    def introspect(self, token: str, *, requesting_client_id: str,
                   requesting_client_secret: str | None) -> dict:
        """Internal introspection; never expose without client authentication."""
        client = self.clients.get(requesting_client_id)
        if (not client or not client.client_secret or
                not isinstance(requesting_client_secret, str) or
                not hmac.compare_digest(client.client_secret, requesting_client_secret) or
                not isinstance(token, str) or len(token) > 256):
            raise OAuthBridgeError("invalid introspection client")
        with self._lock:
            record = self._tokens.get(hashlib.sha256(token.encode()).hexdigest())
            if not record or self._clock() >= record.expires or record.client_id != requesting_client_id:
                return {"active": False}
            return {"active": True, "iss": self.issuer, "sub": record.subject,
                    "aud": record.resource, "client_id": record.client_id,
                    "scope": " ".join(sorted(record.scopes)), "exp": int(record.expires)}
