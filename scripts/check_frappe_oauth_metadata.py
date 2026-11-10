"""Validate public Frappe OAuth authorization-server metadata offline.

Unlike a JWT/JWKS preflight, this checks Frappe's opaque access-token flow:
Authorization Code + PKCE S256 and a confidential introspection endpoint.
No HTTP calls, tokens, secrets, or service changes are made by this script.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit


class FrappeDiscoveryError(ValueError):
    """The metadata cannot safely support the requested AgentSteers flow."""


EXPECTED_ENDPOINTS = {
    "authorization_endpoint": "/api/method/frappe.integrations.oauth2.authorize",
    "token_endpoint": "/api/method/frappe.integrations.oauth2.get_token",
    "introspection_endpoint": "/api/method/frappe.integrations.oauth2.introspect_token",
}


def _issuer(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parts = urlsplit(value)
        return bool(
            parts.scheme == "https" and parts.hostname and
            not parts.username and not parts.password and
            not parts.query and not parts.fragment and
            not parts.path.endswith("/")
        )
    except ValueError:
        return False


def _contains(document: dict, name: str, value: str) -> bool:
    items = document.get(name)
    return isinstance(items, list) and value in items


def validate_frappe_metadata(document: dict, *, expected_issuer: str,
                             registration: str = "provided") -> None:
    """Check expected Frappe OAuth endpoints and capabilities; fail closed.

    A pass is ONLY structural metadata verification, not successful login,
    access-token issuance or resource-server authorization.
    """
    if registration not in ("provided", "dcr"):
        raise FrappeDiscoveryError("Unsupported OAuth client registration mode")
    if not _issuer(expected_issuer) or not isinstance(document, dict):
        raise FrappeDiscoveryError("HTTPS issuer and JSON object required")
    if document.get("issuer") != expected_issuer:
        raise FrappeDiscoveryError("Issuer mismatch")
    for name, suffix in EXPECTED_ENDPOINTS.items():
        if document.get(name) != expected_issuer + suffix:
            raise FrappeDiscoveryError("Unexpected or missing " + name)
    if not _contains(document, "response_types_supported", "code"):
        raise FrappeDiscoveryError("Authorization Code response not advertised")
    if not _contains(document, "grant_types_supported", "authorization_code"):
        raise FrappeDiscoveryError("Authorization Code grant not advertised")
    if not _contains(document, "code_challenge_methods_supported", "S256"):
        raise FrappeDiscoveryError("PKCE S256 not advertised")
    if not _contains(document, "token_endpoint_auth_methods_supported",
                     "client_secret_basic"):
        raise FrappeDiscoveryError("Confidential client authentication not advertised")
    # In Frappe native introspection mode the same confidential client
    # authenticates to introspect its own opaque access tokens.
    introspection_auth = document.get("introspection_endpoint_auth_methods_supported")
    if introspection_auth is not None and (
        not isinstance(introspection_auth, list)
        or "client_secret_basic" not in introspection_auth
    ):
        raise FrappeDiscoveryError("Introspection client authentication mismatch")
    if registration == "dcr":
        expected = (expected_issuer +
                    "/api/method/frappe.integrations.oauth2.register_client")
        if document.get("registration_endpoint") != expected:
            raise FrappeDiscoveryError("Frappe dynamic client registration unavailable")
    elif "registration_endpoint" in document:
        # An advertised registration endpoint is not required if the
        # operator already has a dedicated Frappe OAuth Client.
        if document["registration_endpoint"] != (
            expected_issuer + "/api/method/frappe.integrations.oauth2.register_client"
        ):
            raise FrappeDiscoveryError("Untrusted registration endpoint")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("metadata_json", type=Path,
                        help="Public /.well-known/oauth-authorization-server JSON")
    parser.add_argument("--issuer", required=True,
                        help="Exact HTTPS Frappe issuer base URL")
    parser.add_argument("--registration", choices=("provided", "dcr"),
                        default="provided")
    args = parser.parse_args()
    try:
        document = json.loads(args.metadata_json.read_text(encoding="utf-8"))
        validate_frappe_metadata(
            document, expected_issuer=args.issuer, registration=args.registration
        )
    except (FrappeDiscoveryError, ValueError, OSError) as exc:
        print("Frappe OAuth metadata: FAILED (" + str(exc) + ")", file=sys.stderr)
        return 1
    print("Frappe OAuth metadata: structural checks passed.")
    print("ChatGPT login, consent, token issuance and real MCP calls NOT verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
