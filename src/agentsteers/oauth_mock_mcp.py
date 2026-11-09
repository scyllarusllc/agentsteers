"""Opt-in OAuth-protected Mock MCP, separate from the legacy bearer-token route.

No Codex, shell, Git operations or production data. Does not launch a listener.
Use create_app with a real AccessTokenVerifier and trusted HTTPS termination.
"""
from __future__ import annotations

import io
import json
from urllib.parse import urlsplit

from agentsteers.actor_jobs import ActorScopedMockJobs, Principal as JobPrincipal
from agentsteers.mock_http_mcp import MAX_BODY, METHODS, PROTOCOL
from agentsteers.oauth_discovery import OAuthDiscovery, oauth_challenge_headers
from agentsteers.oauth_security import AuthorizationError, authorize_task, ACTION_SCOPE


def _respond(start_response, status, payload=b"", extra=()):
    start_response(status, [("Content-Type", "application/json; charset=utf-8"),
                            ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"),
                            ("Content-Length", str(len(payload))), *extra])
    return [payload]


def _rpc(start_response, request_id, result=None, error=None):
    obj = {"jsonrpc": "2.0", "id": request_id}
    if error is not None:
        obj["error"] = {"code": error[0], "message": error[1]}
    else:
        obj["result"] = result
    return _respond(start_response, "200 OK", json.dumps(obj).encode("utf-8"))


class OAuthMockMCP:
    """Single-user-friendly OAuth resource server with actor-scoped mock tasks."""

    def __init__(self, *, verifier, resource, repositories, max_jobs=100):
        parsed = urlsplit(resource)
        if parsed.scheme != "https" or not parsed.netloc or parsed.path != "/mcp":
            raise ValueError("HTTPS MCP resource required")
        if not repositories:
            raise ValueError("Explicit repository allowlist required")
        self.verifier = verifier
        self.resource = resource
        self.host = parsed.netloc.lower()
        self.repositories = frozenset(repositories)
        self.jobs = ActorScopedMockJobs(max_jobs=max_jobs)

    def __call__(self, environ, start_response):
        if environ.get("PATH_INFO") != "/mcp":
            return _respond(start_response, "404 Not Found", b'{"error":"not_found"}')
        if (environ.get("wsgi.url_scheme") != "https" or
                environ.get("HTTP_HOST", "").lower() != self.host):
            return _respond(start_response, "403 Forbidden", b'{"error":"untrusted_transport"}')
        origin = environ.get("HTTP_ORIGIN")
        if origin:
            parsed = urlsplit(origin)
            if parsed.scheme != "https" or parsed.netloc.lower() != self.host or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
                return _respond(start_response, "403 Forbidden", b'{"error":"untrusted_origin"}')
        authorization = environ.get("HTTP_AUTHORIZATION", "")
        try:
            if not isinstance(authorization, str) or any(char in authorization for char in "\r\n,"):
                raise AuthorizationError("bad header")
            principal = self.verifier.verify(authorization)
            if not principal.subject:
                raise AuthorizationError("missing subject")
        except Exception:
            return _respond(start_response, "401 Unauthorized", b'{"error":"unauthorized"}',
                            oauth_challenge_headers(resource=self.resource))
        if environ.get("REQUEST_METHOD") != "POST":
            return _respond(start_response, "405 Method Not Allowed", b'{"error":"method_not_allowed"}',
                            (("Allow", "POST"),))
        accept = environ.get("HTTP_ACCEPT", "")
        if "application/json" not in accept or "text/event-stream" not in accept:
            return _respond(start_response, "406 Not Acceptable", b'{"error":"bad_accept"}')
        try:
            length = int(environ.get("CONTENT_LENGTH", "0"))
            if length < 1 or length > MAX_BODY:
                raise ValueError("bad length")
            raw = environ["wsgi.input"].read(length)
            if len(raw) != length:
                raise ValueError("incomplete body")
            req = json.loads(raw)
            if not isinstance(req, dict) or req.get("jsonrpc") != "2.0":
                raise ValueError("bad RPC")
        except (ValueError, TypeError, KeyError, UnicodeDecodeError):
            return _rpc(start_response, None, error=(-32700, "Invalid JSON-RPC request"))
        method, request_id = req.get("method"), req.get("id")
        if request_id is None and method == "notifications/initialized":
            return _respond(start_response, "202 Accepted")
        if not isinstance(request_id, (str, int)) or isinstance(request_id, bool):
            return _rpc(start_response, None, error=(-32600, "Invalid request id"))
        if method == "initialize":
            return _rpc(start_response, request_id, result={
                "protocolVersion": PROTOCOL, "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "AgentSteers OAuth Mock", "version": "0.1.0"},
                "instructions": "Simulated tasks only; no Codex, shell or Git execution."
            })
        if method == "ping":
            return _rpc(start_response, request_id, result={})
        if method == "tools/list":
            return _rpc(start_response, request_id, result={"tools": [
                {"name": name, **details} for name, details in METHODS.items()
            ]})
        if method != "tools/call":
            return _rpc(start_response, request_id, error=(-32601, "Method not found"))
        params = req.get("params")
        if not isinstance(params, dict) or params.get("name") not in METHODS:
            return _rpc(start_response, request_id, error=(-32602, "Invalid parameters"))
        name, arguments = params["name"], params.get("arguments", {})
        schema = METHODS[name]["inputSchema"]
        if (not isinstance(arguments, dict) or set(arguments) != set(schema["required"]) or
                any(not isinstance(x, str) for x in arguments.values())):
            return _rpc(start_response, request_id, error=(-32602, "Invalid arguments"))
        if ACTION_SCOPE[name] not in principal.scopes:
            outcome = {"ok": False, "error": "forbidden"}
        else:
            actor = JobPrincipal(
                subject=principal.subject, repositories=self.repositories,
                can_submit="agentsteers:submit" in principal.scopes,
                can_cancel="agentsteers:cancel" in principal.scopes
            )
            if name == "submit_task":
                repository = arguments["repository"]
                try:
                    authorize_task(principal, action=name, repository=repository,
                                   repository_allowlist=self.repositories)
                    outcome = self.jobs.submit(actor, repository, arguments["instruction"])
                except AuthorizationError:
                    outcome = {"ok": False, "error": "forbidden"}
            else:
                task_id = arguments["task_id"]
                # ActorScopedMockJobs checks persisted task ownership and repository
                # under its lock. It deliberately hides other actors' task existence.
                operation = {"get_task_status": self.jobs.status,
                             "get_task_result": self.jobs.result,
                             "cancel_task": self.jobs.cancel}[name]
                outcome = operation(actor, task_id)
        return _rpc(start_response, request_id, result={
            "content": [{"type": "text", "text": json.dumps(outcome)}],
            "isError": not outcome.get("ok", False)
        })


def create_app(*, verifier, resource: str, authorization_server: str, repositories):
    """Create an unmounted WSGI app; caller provides the real OAuth verifier."""
    return OAuthDiscovery(
        OAuthMockMCP(verifier=verifier, resource=resource, repositories=repositories),
        resource=resource, authorization_server=authorization_server
    )
