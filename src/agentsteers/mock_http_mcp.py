"""Opt-in, mock-only WSGI MCP endpoint. Never runs Codex or shell.

Deploy only behind trusted HTTPS termination and loopback-bound WSGI. This
separate app is NOT connected to production website_wsgi.py or Caddy.
"""
from __future__ import annotations

import hmac
import json
import os
from urllib.parse import urlsplit

from agentsteers.actor_jobs import ActorScopedMockJobs, Principal

PROTOCOL = "2025-06-18"
MAX_BODY = 16384
JOBS = ActorScopedMockJobs(max_jobs=100)
METHODS = {
    "submit_task": {
        "description": "Create a mock-only development task. Never executes code.",
        "inputSchema": {
            "type": "object",
            "properties": {"repository": {"type": "string"}, "instruction": {"type": "string"}},
            "required": ["repository", "instruction"], "additionalProperties": False,
        },
    },
    "get_task_status": {"description": "Read a mock task status.", "inputSchema": {
        "type": "object", "properties": {"task_id": {"type": "string"}},
        "required": ["task_id"], "additionalProperties": False}},
    "get_task_result": {"description": "Read a simulated result only.", "inputSchema": {
        "type": "object", "properties": {"task_id": {"type": "string"}},
        "required": ["task_id"], "additionalProperties": False}},
    "cancel_task": {"description": "Cancel a queued mock task.", "inputSchema": {
        "type": "object", "properties": {"task_id": {"type": "string"}},
        "required": ["task_id"], "additionalProperties": False}},
}


def _response(start_response, status, body=b"", extra=()):
    start_response(status, [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Cache-Control", "no-store"),
        ("X-Content-Type-Options", "nosniff"),
        ("Content-Length", str(len(body))), *extra,
    ])
    return [body]


def _json(start_response, id_, *, result=None, error=None):
    payload = {"jsonrpc": "2.0", "id": id_}
    if error is None:
        payload["result"] = result
    else:
        payload["error"] = {"code": error[0], "message": error[1]}
    return _response(start_response, "200 OK", json.dumps(payload).encode("utf-8"))


def application(environ, start_response):
    # Fail closed; nothing is exposed by importing this module.
    if os.environ.get("AGENTSTEERS_MCP_MOCK_ENABLED") != "1":
        return _response(start_response, "404 Not Found", b'{"error":"not_found"}')
    token = os.environ.get("AGENTSTEERS_MCP_MOCK_TOKEN", "")
    host = os.environ.get("AGENTSTEERS_MCP_MOCK_HOST", "").lower()
    repositories = frozenset(s.strip() for s in os.environ.get(
        "AGENTSTEERS_MCP_MOCK_REPOS", "").split(",") if s.strip())
    if (len(token) < 32 or any(c in token for c in "\r\n") or
            not host or "/" in host or not repositories):
        return _response(start_response, "503 Service Unavailable", b'{"error":"not_configured"}')
    if environ.get("PATH_INFO") != "/mcp":
        return _response(start_response, "404 Not Found", b'{"error":"not_found"}')
    if (environ.get("wsgi.url_scheme") != "https" or
            environ.get("HTTP_HOST", "").lower() != host):
        return _response(start_response, "403 Forbidden", b'{"error":"untrusted_transport"}')
    origin = environ.get("HTTP_ORIGIN")
    if origin:
        parsed = urlsplit(origin)
        if (parsed.scheme != "https" or parsed.netloc.lower() != host or
                parsed.path not in ("", "/") or parsed.query or parsed.fragment):
            return _response(start_response, "403 Forbidden", b'{"error":"untrusted_origin"}')
    auth = environ.get("HTTP_AUTHORIZATION", "")
    if not isinstance(auth, str) or not hmac.compare_digest(auth, "Bearer " + token):
        return _response(start_response, "401 Unauthorized", b'{"error":"unauthorized"}',
                         (("WWW-Authenticate", "Bearer"),))
    if environ.get("REQUEST_METHOD") != "POST":
        return _response(start_response, "405 Method Not Allowed", b'{"error":"method_not_allowed"}',
                         (("Allow", "POST"),))
    accept = environ.get("HTTP_ACCEPT", "")
    if "application/json" not in accept or "text/event-stream" not in accept:
        return _response(start_response, "406 Not Acceptable", b'{"error":"bad_accept"}')
    try:
        length = int(environ.get("CONTENT_LENGTH", "0"))
        if length < 1 or length > MAX_BODY:
            raise ValueError("bad length")
        raw = environ["wsgi.input"].read(length)
        if len(raw) != length:
            raise ValueError("incomplete")
        req = json.loads(raw)
        if not isinstance(req, dict) or req.get("jsonrpc") != "2.0":
            raise ValueError("json-rpc required")
    except (ValueError, KeyError, TypeError, UnicodeDecodeError):
        return _json(start_response, None, error=(-32700, "Invalid JSON-RPC request"))
    method, id_ = req.get("method"), req.get("id")
    if id_ is None and method == "notifications/initialized":
        return _response(start_response, "202 Accepted", b"")
    if not isinstance(id_, (str, int)) or isinstance(id_, bool):
        return _json(start_response, None, error=(-32600, "Invalid request id"))
    if method == "initialize":
        return _json(start_response, id_, result={
            "protocolVersion": PROTOCOL, "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "AgentSteers Mock MCP", "version": "0.1.0"},
            "instructions": "Mock only. No Codex, shell, Git or deployment execution.",
        })
    if method == "ping":
        return _json(start_response, id_, result={})
    if method == "tools/list":
        return _json(start_response, id_, result={"tools": [
            {"name": name, **data} for name, data in METHODS.items()
        ]})
    if method != "tools/call":
        return _json(start_response, id_, error=(-32601, "Method not found"))
    params = req.get("params")
    if not isinstance(params, dict):
        return _json(start_response, id_, error=(-32602, "Invalid parameters"))
    name, arguments = params.get("name"), params.get("arguments", {})
    if name not in METHODS or not isinstance(arguments, dict):
        return _json(start_response, id_, error=(-32602, "Unknown tool or arguments"))
    schema = METHODS[name]["inputSchema"]
    if set(arguments) != set(schema["required"]) or any(
        not isinstance(value, str) for value in arguments.values()
    ):
        return _json(start_response, id_, error=(-32602, "Invalid tool arguments"))
    principal = Principal(
        subject="mock-token-owner", repositories=repositories,
        can_submit=True, can_cancel=True,
    )
    if name == "submit_task":
        outcome = JOBS.submit(principal, arguments["repository"], arguments["instruction"])
    elif name == "get_task_status":
        outcome = JOBS.status(principal, arguments["task_id"])
    elif name == "get_task_result":
        outcome = JOBS.result(principal, arguments["task_id"])
    else:
        outcome = JOBS.cancel(principal, arguments["task_id"])
    return _json(start_response, id_, result={
        "content": [{"type": "text", "text": json.dumps(outcome)}],
        "isError": not outcome.get("ok", False),
    })
