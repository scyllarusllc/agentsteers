"""Fail-closed access-token verification for a future remote AgentSteers MCP gateway.

Google Sign-In identity tokens MUST NOT be accepted as MCP access tokens.
Configure an OAuth authorization server that issues resource-audience tokens.
This module is not wired into the local development server.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Collection, Mapping

try:
    import jwt
    from jwt import PyJWKClient
    from jwt.exceptions import InvalidTokenError, PyJWKClientError
except ImportError as exc:
    raise ImportError("Install OAuth dependencies: pip install 'agentsteers[oauth]'") from exc


class AuthorizationError(Exception):
    """Client authentication or authorization was rejected."""


@dataclass(frozen=True)
class Principal:
    subject: str
    scopes: frozenset[str]


class AccessTokenVerifier:
    """Validate signed JWT access tokens from the configured OAuth issuer.

    Configure issuer/JWKS from trusted server-side deployment settings, never
    from an incoming request. Do not use this with a Google ID token.
    """

    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        jwks_url: str,
        allowed_subjects: Collection[str],
    ) -> None:
        if not (issuer.startswith("https://") and audience.startswith("https://")
                and jwks_url.startswith("https://") and allowed_subjects):
            raise ValueError("HTTPS issuer, audience, JWKS URL and owner allowlist required")
        self._issuer = issuer
        self._audience = audience
        self._allowed_subjects = frozenset(allowed_subjects)
        self._jwks = PyJWKClient(jwks_url)

    def verify(self, authorization_header: str | None) -> Principal:
        if not authorization_header:
            raise AuthorizationError("Missing bearer access token")
        scheme, separator, token = authorization_header.partition(" ")
        if scheme.lower() != "bearer" or not separator or not token or token.strip() != token:
            raise AuthorizationError("Invalid Authorization header")
        try:
            key = self._jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                issuer=self._issuer,
                audience=self._audience,
                options={"require": ["iss", "aud", "sub", "exp", "iat"]},
                leeway=30,
            )
        except (InvalidTokenError, PyJWKClientError, ValueError) as exc:
            raise AuthorizationError("Invalid access token") from exc

        sub = claims.get("sub")
        if not isinstance(sub, str) or sub not in self._allowed_subjects:
            raise AuthorizationError("Identity is not authorized")
        scope = claims.get("scope", "")
        if not isinstance(scope, str):
            raise AuthorizationError("Invalid scope claim")
        return Principal(subject=sub, scopes=frozenset(scope.split()))


ACTION_SCOPE: Mapping[str, str] = {
    "submit_task": "agentsteers:submit",
    "get_task_status": "agentsteers:read",
    "get_task_result": "agentsteers:read",
    "cancel_task": "agentsteers:cancel",
}


def authorize_task(
    principal: Principal,
    *,
    action: str,
    repository: str,
    repository_allowlist: Collection[str],
    task_owner: str | None = None,
) -> None:
    """Authorize an action; call BEFORE any task read, update, or execution.

    The repository allowlist and persisted task_owner must be resolved
    server-side. Do not derive either from client-supplied approval flags.
    """
    scope = ACTION_SCOPE.get(action)
    if scope is None or scope not in principal.scopes:
        raise AuthorizationError("Action not permitted")
    if not repository or repository not in repository_allowlist:
        raise AuthorizationError("Repository not permitted")
    if action != "submit_task" and (task_owner is None or task_owner != principal.subject):
        raise AuthorizationError("Task is not owned by this caller")
