"""Isolated security primitives for a future Frappe-backed MCP OAuth bridge.

NOT wired into Frappe, Caddy, /mcp, or the token endpoint.
The eventual authorization-code issuer must validate these properties BEFORE
issuing a token. Never treat Frappe's native token endpoint as sufficient.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

RESOURCE = "https://mcp.agentsteers.com/mcp"
SCOPES = frozenset(("agentsteers:read", "agentsteers:submit", "agentsteers:cancel"))
_VERIFIER = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")
_CHALLENGE = re.compile(r"^[A-Za-z0-9_-]{43}$")


class OAuthBridgeRejected(ValueError):
    """Refuse an unsafe or unverified OAuth exchange without leaking secrets."""


@dataclass(frozen=True)
class RegisteredClient:
    """Server-owned configuration. Never accept these values from an OAuth request."""
    client_id: str
    secret: str
    redirect_uri: str
    resource: str = RESOURCE

    def __post_init__(self):
        u = urlsplit(self.redirect_uri)
        if not self.client_id or not self.secret or not (
            u.scheme == "https" and u.netloc and not u.username and not u.password
            and not u.fragment and not u.query
        ):
            raise ValueError("Invalid confidential OAuth client registration")
        if self.resource != RESOURCE:
            raise ValueError("MCP resource is not allowlisted")


@dataclass(frozen=True)
class PendingAuthorization:
    """Trusted, one-time authorization-code record from an external secure store."""
    client_id: str
    subject: str
    redirect_uri: str
    resource: str
    code_challenge: str
    code_challenge_method: str
    scopes: frozenset[str]
    expires_at: float


def verify_exchange(*, registered: RegisteredClient,
                    request_client_id: str, request_client_secret: str,
                    request_redirect_uri: str, request_resource: str,
                    code_verifier: str, pending: PendingAuthorization,
                    now: float) -> None:
    """Fail-closed predicate for a code exchange (does NOT redeem or issue codes).

    Caller MUST atomically claim/invalidate a code in a transactional store,
    bind it to the authenticated Frappe user, and issue server-side scoped tokens.
    """
    if not isinstance(request_client_secret, str) or not hmac.compare_digest(
        request_client_secret.encode("utf-8"), registered.secret.encode("utf-8")
    ):
        raise OAuthBridgeRejected("Invalid client credentials")
    if (not isinstance(request_client_id, str) or
            not hmac.compare_digest(request_client_id, registered.client_id)):
        raise OAuthBridgeRejected("Invalid client credentials")
    if (request_redirect_uri != registered.redirect_uri or
            request_redirect_uri != pending.redirect_uri):
        raise OAuthBridgeRejected("Invalid redirect URI")
    if (request_resource != RESOURCE or request_resource != registered.resource or
            request_resource != pending.resource):
        raise OAuthBridgeRejected("Invalid resource")
    if pending.client_id != registered.client_id or not pending.subject:
        raise OAuthBridgeRejected("Invalid authorization code binding")
    if pending.expires_at <= now:
        raise OAuthBridgeRejected("Expired authorization code")
    if pending.code_challenge_method != "S256" or not isinstance(
            pending.code_challenge, str) or not _CHALLENGE.fullmatch(pending.code_challenge):
        raise OAuthBridgeRejected("Invalid PKCE challenge")
    if not isinstance(code_verifier, str) or not _VERIFIER.fullmatch(code_verifier):
        raise OAuthBridgeRejected("Invalid PKCE verifier")
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    if not hmac.compare_digest(expected, pending.code_challenge):
        raise OAuthBridgeRejected("Invalid PKCE verifier")
    if not pending.scopes or not pending.scopes.issubset(SCOPES):
        raise OAuthBridgeRejected("Invalid MCP scopes")


def validate_introspection_claims(*, claims: dict, issuer: str, client_id: str,
                                  subject_allowlist: frozenset[str],
                                  now: float) -> tuple[str, frozenset[str]]:
    """Adapter contract: requires actual audience, issuer, client and expiry.

    Frappe responses missing these fields MUST NOT be padded with guessed values.
    A future bridge can generate its OWN signed/opaque resource-bound tokens.
    """
    if not isinstance(claims, dict) or claims.get("active") is not True:
        raise OAuthBridgeRejected("Inactive token")
    exp = claims.get("exp")
    if isinstance(exp, bool) or not isinstance(exp, (float, int)) or exp <= now:
        raise OAuthBridgeRejected("Invalid expiration")
    if claims.get("iss") != issuer or claims.get("client_id") != client_id:
        raise OAuthBridgeRejected("Wrong issuer or client")
    audience = claims.get("aud")
    if not (audience == RESOURCE or
            isinstance(audience, (tuple, list)) and RESOURCE in audience):
        raise OAuthBridgeRejected("Wrong MCP audience")
    subject = claims.get("sub")
    if not isinstance(subject, str) or subject not in subject_allowlist:
        raise OAuthBridgeRejected("Unknown subject")
    scopes = claims.get("scope")
    if not isinstance(scopes, str):
        raise OAuthBridgeRejected("Invalid scopes")
    scope_set = frozenset(scopes.split())
    if not scope_set or not scope_set.issubset(SCOPES):
        raise OAuthBridgeRejected("Untrusted scopes")
    return subject, scope_set
