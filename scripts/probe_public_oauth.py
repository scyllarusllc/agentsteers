"""Read-only public OAuth discovery probe for AgentSteers.

Only performs two unauthenticated HTTPS GET requests: the path-scoped MCP
protected-resource metadata and the Frappe authorization-server metadata.
No client credentials, access tokens, tasks, Caddy edits or Codex commands.
A passing probe does NOT establish a successful OAuth login.
"""
from __future__ import annotations

import argparse
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from scripts.check_frappe_oauth_metadata import validate_frappe_metadata

RESOURCE = "https://mcp.agentsteers.com/mcp"
MAX_BYTES = 65536
TIMEOUT_SECONDS = 5
EXPECTED_SCOPES = frozenset({
    "agentsteers:read", "agentsteers:submit", "agentsteers:cancel",
})


class PublicOAuthProbeError(ValueError):
    """Public discovery could not safely verify the expected metadata."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _valid_https_url(url: str) -> bool:
    if not isinstance(url, str) or not url or url != url.strip():
        return False
    try:
        parts = urlsplit(url)
        return bool(
            parts.scheme == "https" and parts.hostname and
            not parts.username and not parts.password and
            not parts.query and not parts.fragment and
            not parts.path.endswith("/") and
            not any(ch in url for ch in ("\\r", "\\n", "\\x00"))
        )
    except ValueError:
        return False


def _fetch_json(url: str, *, opener):
    if not _valid_https_url(url):
        raise PublicOAuthProbeError("Invalid HTTPS discovery URL")
    request = Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "AgentSteers-Public-OAuth-Probe/1.0",
    }, method="GET")
    try:
        with opener(request, timeout=TIMEOUT_SECONDS) as response:
            if getattr(response, "status", 200) != 200:
                raise PublicOAuthProbeError("Discovery endpoint did not return HTTP 200")
            content_type = response.headers.get("Content-Type", "")
            if not content_type.lower().split(";", 1)[0].strip() == "application/json":
                raise PublicOAuthProbeError("Discovery endpoint returned a non-JSON content type")
            body = response.read(MAX_BYTES + 1)
    except (HTTPError, URLError, OSError, TimeoutError, ValueError) as exc:
        if isinstance(exc, PublicOAuthProbeError):
            raise
        # Deliberately omit upstream URLs, headers and response bodies.
        raise PublicOAuthProbeError("HTTPS discovery request failed") from exc
    if len(body) > MAX_BYTES:
        raise PublicOAuthProbeError("Discovery document too large")
    try:
        document = json.loads(body)
    except (UnicodeError, ValueError) as exc:
        raise PublicOAuthProbeError("Invalid JSON discovery document") from exc
    if not isinstance(document, dict):
        raise PublicOAuthProbeError("Discovery document must be a JSON object")
    return document


def validate_resource_metadata(metadata: dict, *, issuer: str) -> None:
    if not isinstance(metadata, dict):
        raise PublicOAuthProbeError("Invalid protected-resource metadata")
    if metadata.get("resource") != RESOURCE:
        raise PublicOAuthProbeError("MCP resource mismatch")
    if metadata.get("authorization_servers") != [issuer]:
        raise PublicOAuthProbeError("Expected Frappe authorization server not advertised")
    scopes = metadata.get("scopes_supported")
    if not isinstance(scopes, list) or not all(isinstance(s, str) for s in scopes):
        raise PublicOAuthProbeError("MCP scopes missing or malformed")
    if not EXPECTED_SCOPES.issubset(set(scopes)):
        raise PublicOAuthProbeError("Missing required AgentSteers MCP scopes")
    bearer = metadata.get("bearer_methods_supported")
    if not isinstance(bearer, list) or "header" not in bearer:
        raise PublicOAuthProbeError("Bearer header authentication not advertised")


def probe(*, issuer: str, opener=None, registration: str = "provided") -> None:
    if not _valid_https_url(issuer):
        raise PublicOAuthProbeError("Issuer must be a valid HTTPS URL")
    if registration not in ("provided", "dcr"):
        raise PublicOAuthProbeError("Unknown OAuth client registration mode")
    if opener is None:
        opener = build_opener(_NoRedirect()).open

    resource_metadata = _fetch_json(
        "https://mcp.agentsteers.com/.well-known/oauth-protected-resource/mcp",
        opener=opener,
    )
    validate_resource_metadata(resource_metadata, issuer=issuer)
    authorization_metadata = _fetch_json(
        issuer + "/.well-known/oauth-authorization-server",
        opener=opener,
    )
    validate_frappe_metadata(
        authorization_metadata, expected_issuer=issuer, registration=registration,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issuer", required=True,
                        help="Exact HTTPS Frappe OAuth issuer, never a client secret")
    parser.add_argument("--registration", choices=("provided", "dcr"),
                        default="provided")
    args = parser.parse_args(argv)
    try:
        probe(issuer=args.issuer, registration=args.registration)
    except (PublicOAuthProbeError, ValueError) as exc:
        print("Public OAuth discovery: FAILED (" + str(exc) + ")")
        return 1
    print("Public OAuth discovery: PASS (MCP and Frappe metadata verified).")
    print("Real login, token exchange, authorization and Codex execution NOT verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
