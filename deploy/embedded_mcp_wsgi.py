"""Opt-in MCP Streamable HTTP preflight inside the existing Frappe WSGI worker.

This is a read-only protocol compatibility slice, NOT a public MCP release.
It does not run Codex, read user tasks, or trust caller-supplied approval.
The Caddy public route must remain closed until OAuth and ownership checks exist.
"""
from __future__ import annotations

import hmac
import io
import json
import os

PROTOCOL = "2025-06-18"
MAX_BODY = 65536


def _respond(start_response, status, body=b"", extra=()):
    headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Cache-Control", "no-store"),
        ("X-Content-Type-Options", "nosniff"),
        ("Content-Length", str(len(body))),
        *extra,
    ]
    start_response(status, headers)
    return [body]


def _error(start_response, status, code, message, request_id=None):
    payload = {"jsonrpc": "2.0", "id": request_id,
               "error": {"code": code, "message": message}}
    return _respond(start_response, status, json.dumps(payload).encode())


def _authorized(environ):
    secret = os.environ.get("AGENTSTEERS_MCP_EMBEDDED_TOKEN", "")
    if len(secret) < 32 or any(c in secret for c in "\r\n"):
        return False
    auth = environ.get("HTTP_AUTHORIZATION", "")
    return hmac.compare_digest(auth, "Bearer " + secret)


def application(environ, start_response):
    """Stateless JSON-mode subset: initialize, ping, tools/list only.

    No tools are advertised until verified actor-scoped authorization and
    task ownership enforcement are implemented. No session persistence needed.
    """
    if os.environ.get("AGENTSTEERS_MCP_EMBEDDED") != "1":
        return _error(start_response, "404 Not Found", -32601, "Not found")
    if not _authorized(environ):
        return _respond(start_response, "401 Unauthorized", b'{"error":"unauthorized"}',
                        (("WWW-Authenticate", "Bearer"),))
    method = environ.get("REQUEST_METHOD", "")
    if method == "GET":
        return _respond(start_response, "405 Method Not Allowed", b'{"error":"sse_not_supported"}',
                        (("Allow", "POST, DELETE"),))
    if method == "DELETE":
        return _respond(start_response, "405 Method Not Allowed", b'{"error":"stateless_no_session"}',
                        (("Allow", "POST"),))
    if method != "POST":
        return _respond(start_response, "405 Method Not Allowed", b'{"error":"method_not_allowed"}',
                        (("Allow", "POST"),))
    accept = environ.get("HTTP_ACCEPT", "")
    if "application/json" not in accept or "text/event-stream" not in accept:
        return _error(start_response, "406 Not Acceptable", -32000,
                      "MCP requires Accept: application/json, text/event-stream")
    try:
        n = int(environ.get("CONTENT_LENGTH") or "0")
        if n <= 0 or n > MAX_BODY:
            raise ValueError
        raw = environ["wsgi.input"].read(n)
        if len(raw) != n:
            raise ValueError
        message = json.loads(raw)
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            raise ValueError
    except (ValueError, TypeError, UnicodeDecodeError, KeyError):
        return _error(start_response, "400 Bad Request", -32700, "Invalid JSON-RPC request")
    action = message.get("method")
    request_id = message.get("id")
    if request_id is None:
        # MCP notifications must be acknowledged without a JSON-RPC response.
        if action == "notifications/initialized":
            start_response("202 Accepted", [("Content-Length", "0"), ("Cache-Control", "no-store")])
            return [b""]
        return _error(start_response, "400 Bad Request", -32600, "Unsupported notification")
    if not isinstance(request_id, (str, int)) or isinstance(request_id, bool):
        return _error(start_response, "400 Bad Request", -32600, "Invalid request id")
    if action == "initialize":
        result = {"protocolVersion": PROTOCOL, "capabilities": {"tools": {"listChanged": False}},
                  "serverInfo": {"name": "AgentSteers Frappe MCP preflight", "version": "0.1.0"},
                  "instructions": "Preflight only; no task execution or remote Codex available."}
    elif action == "ping":
        result = {}
    elif action == "tools/list":
        result = {"tools": []}
    else:
        return _error(start_response, "200 OK", -32601, "Method not available", request_id)
    body = json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}).encode()
    return _respond(start_response, "200 OK", body)
