"""Default-deny Frappe OAuth Mock MCP WSGI application.

Configure a dedicated confidential Frappe OAuth client with custom MCP scopes.
DO NOT route public traffic to this app until OAuth compatibility is proven.
"""
import os
from agentsteers.frappe_oauth import FrappeTokenVerifier
from agentsteers.oauth_mock_mcp import create_app

RESOURCE = "https://mcp.agentsteers.com/mcp"


def _unconfigured(environ, start_response):
    data = b'{"error":"frappe_oauth_not_configured"}'
    start_response("503 Service Unavailable", [
        ("Content-Type", "application/json"), ("Cache-Control", "no-store"),
        ("Content-Length", str(len(data)))])
    return [data]


def build_application(env=None, *, opener=None):
    env = os.environ if env is None else env
    if env.get("AGENTSTEERS_FRAPPE_OAUTH_ENABLED") != "1":
        return _unconfigured
    issuer = env.get("AGENTSTEERS_FRAPPE_ISSUER", "")
    client_id = env.get("AGENTSTEERS_FRAPPE_CLIENT_ID", "")
    client_secret = env.get("AGENTSTEERS_FRAPPE_CLIENT_SECRET", "")
    subjects = frozenset(x.strip() for x in env.get(
        "AGENTSTEERS_FRAPPE_SUBJECTS", "").split(",") if x.strip())
    repos = frozenset(x.strip() for x in env.get(
        "AGENTSTEERS_FRAPPE_REPOS", "").split(",") if x.strip())
    if (not issuer or not client_id or not client_secret or not subjects or not repos
            or env.get("AGENTSTEERS_FRAPPE_MCP_RESOURCE") != RESOURCE):
        return _unconfigured
    try:
        verifier = FrappeTokenVerifier(
            issuer=issuer, client_id=client_id, client_secret=client_secret,
            allowed_subjects=subjects, opener=opener)
        return create_app(verifier=verifier, resource=RESOURCE,
                          authorization_server=issuer, repositories=repos)
    except ValueError:
        return _unconfigured


application = build_application()
