"""Disabled-by-default, OAuth-authenticated MCP handshake integration.

Preflight only: no tool calls, Codex, shell, Frappe or public proxy activation.
An OAuth provider is external; this service verifies its JWT access tokens.
"""
from __future__ import annotations

import io
import json
import os

from agentsteers.oauth_resource_metadata import ProtectedResourceDiscovery
from agentsteers.remote_mcp_guard import RemoteMCPGuard

MAX_BODY = 16 * 1024
PROTOCOL_VERSION = "2025-06-18"


def _send(start_response, status: str, payload, *, extra=()):
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    start_response(status, [
        ("Content-Type", "application/json"),
        ("Content-Length", str(len(body))),
        ("Cache-Control", "no-store"),
        ("X-Content-Type-Options", "nosniff"),
        *extra,
    ])
    return [body]


def _rpc(start_response, request_id, *, result=None, error=None):
    response = {"jsonrpc": "2.0", "id": request_id}
    if error is None:
        response["result"] = result
    else:
        response["error"] = {"code": error[0], "message": error[1]}
    return _send(start_response, "200 OK", response)


def _handshake(environ, start_response):
    """This handler must remain behind RemoteMCPGuard."""
    if not getattr(environ.get("agentsteers.principal"), "subject", None):
        return _send(start_response, "401 Unauthorized", {"error": "unauthorized"})
    if environ.get("PATH_INFO") != "/mcp":
        return _send(start_response, "404 Not Found", {"error": "not_found"})
    if environ.get("REQUEST_METHOD") != "POST":
        return _send(start_response, "405 Method Not Allowed", {"error": "method_not_allowed"},
                     extra=(("Allow", "POST"),))
    accept = environ.get("HTTP_ACCEPT", "")
    if "application/json" not in accept or "text/event-stream" not in accept:
        return _send(start_response, "406 Not Acceptable", {"error": "bad_accept"})
    if environ.get("CONTENT_TYPE", "").split(";", 1)[0].strip().lower() != "application/json":
        return _send(start_response, "415 Unsupported Media Type", {"error": "unsupported_media_type"})
    try:
        length = int(environ.get("CONTENT_LENGTH", ""))
        if length < 1 or length > MAX_BODY:
            raise ValueError("bad length")
        raw = environ["wsgi.input"].read(length)
        if len(raw) != length:
            raise ValueError("truncated body")
        request = json.loads(raw)
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
            raise ValueError("invalid json rpc")
    except (ValueError, TypeError, KeyError, UnicodeDecodeError):
        return _rpc(start_response, None, error=(-32700, "Invalid JSON-RPC request"))

    method, request_id = request.get("method"), request.get("id")
    if method == "notifications/initialized" and request_id is None:
        start_response("202 Accepted", [("Content-Length", "0"), ("Cache-Control", "no-store")])
        return [b""]
    if isinstance(request_id, bool) or not isinstance(request_id, (int, str)):
        return _rpc(start_response, None, error=(-32600, "Invalid request id"))
    if method == "initialize":
        return _rpc(start_response, request_id, result={
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "AgentSteers OAuth Preflight", "version": "0.1.0"},
            "instructions": "OAuth preflight only. No tools or Codex execution.",
        })
    if method == "ping":
        return _rpc(start_response, request_id, result={})
    if method == "tools/list":
        return _rpc(start_response, request_id, result={"tools": []})
    if method == "tools/call":
        return _rpc(start_response, request_id, error=(-32601, "Tools unavailable"))
    return _rpc(start_response, request_id, error=(-32601, "Method not found"))


def create_app(*, verifier, resource: str, authorization_server: str):
    """Inject a real AccessTokenVerifier (or test double). Never trust client claims."""
    if verifier is None or not callable(getattr(verifier, "verify", None)):
        raise ValueError("A verifying OAuth access-token validator is required")
    from urllib.parse import urlsplit
    parsed = urlsplit(resource)
    if parsed.scheme != "https" or parsed.path != "/mcp":
        raise ValueError("Expected HTTPS /mcp resource")
    origin = f"https://{parsed.netloc}"
    guarded = RemoteMCPGuard(_handshake, verifier, public_origin=origin)
    return ProtectedResourceDiscovery(guarded, resource=resource,
                                      authorization_server=authorization_server)


def from_environment():
    """Explicit opt-in factory, never invoked at module import."""
    if os.environ.get("AGENTSTEERS_OAUTH_PREFLIGHT_ENABLED") != "1":
        raise RuntimeError("OAuth preflight disabled")
    required = ("AGENTSTEERS_OAUTH_ISSUER", "AGENTSTEERS_OAUTH_JWKS_URL",
                "AGENTSTEERS_OAUTH_ALLOWED_SUBJECTS")
    if any(not os.environ.get(name) for name in required):
        raise RuntimeError("Missing OAuth preflight server-side configuration")
    from agentsteers.oauth_security import AccessTokenVerifier
    resource = "https://mcp.agentsteers.com/mcp"
    verifier = AccessTokenVerifier(
        issuer=os.environ["AGENTSTEERS_OAUTH_ISSUER"],
        audience=resource,
        jwks_url=os.environ["AGENTSTEERS_OAUTH_JWKS_URL"],
        allowed_subjects=set(os.environ["AGENTSTEERS_OAUTH_ALLOWED_SUBJECTS"].split(",")),
    )
    return create_app(verifier=verifier, resource=resource,
                      authorization_server=os.environ["AGENTSTEERS_OAUTH_ISSUER"])
