"""Default-off WSGI entry point for the OAuth Mock MCP prototype.

This module never starts a listener. It requires a separately configured OAuth
authorization server, trusted HTTPS reverse proxy, and explicit enablement.
Not used by the legacy 'make mcp' process. Never executes Codex.
"""
from __future__ import annotations

import os
from agentsteers.oauth_mock_mcp import create_app
from agentsteers.oauth_security import AccessTokenVerifier


def _unavailable(environ, start_response):
    data = b'{"error":"oauth_mock_not_configured"}'
    start_response("503 Service Unavailable", [
        ("Content-Type", "application/json"),
        ("Cache-Control", "no-store"), ("Content-Length", str(len(data)))
    ])
    return [data]


def build_application(env=None):
    env = os.environ if env is None else env
    if env.get("AGENTSTEERS_OAUTH_MOCK_ENABLED") != "1":
        return _unavailable
    required = {
        "issuer": env.get("AGENTSTEERS_OAUTH_ISSUER", ""),
        "audience": env.get("AGENTSTEERS_OAUTH_AUDIENCE", ""),
        "jwks_url": env.get("AGENTSTEERS_OAUTH_JWKS_URL", ""),
        "authorization_server": env.get("AGENTSTEERS_OAUTH_AUTHORIZATION_SERVER", "")
    }
    subjects = frozenset(x.strip() for x in env.get(
        "AGENTSTEERS_OAUTH_SUBJECTS", "").split(",") if x.strip())
    repositories = frozenset(x.strip() for x in env.get(
        "AGENTSTEERS_OAUTH_REPOS", "").split(",") if x.strip())
    if not all(required.values()) or not subjects or not repositories:
        return _unavailable
    resource = "https://mcp.agentsteers.com/mcp"
    # Audience must be the full resource URI; never accept Google ID tokens.
    if required["audience"] != resource:
        return _unavailable
    try:
        verifier = AccessTokenVerifier(
            issuer=required["issuer"], audience=resource,
            jwks_url=required["jwks_url"], allowed_subjects=subjects)
        return create_app(verifier=verifier, resource=resource,
                          authorization_server=required["authorization_server"],
                          repositories=repositories)
    except ValueError:
        return _unavailable


application = build_application()
