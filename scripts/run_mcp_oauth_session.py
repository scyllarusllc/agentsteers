"""Fail-closed entry point for future OAuth Bridge-backed MCP.

This command never falls back to shared bearer Mock MCP. A live listener may
be enabled only after Frappe login binding, durable grants, production token
verification and an authenticated MCP HTTP adapter are implemented and tested.
"""
from __future__ import annotations

import sys

from agentsteers.oauth_bridge_core import OAuthBridgeCore, OAuthClient, RESOURCE


def readiness() -> tuple[bool, tuple[str, ...]]:
    """Report missing integration gates; no network or process side effects."""
    missing = (
        "Frappe-authenticated user session and consent/CSRF adapter",
        "durable atomic authorization-code and access-token storage",
        "HTTP authorize/token endpoints with client authentication",
        "MCP resource-server validation for Bridge-issued tokens",
        "end-to-end ChatGPT OAuth and authorized tool-call tests",
    )
    return False, missing


def main() -> int:
    print("AgentSteers MCP (OAuth Bridge mode)")
    print("Resource: " + RESOURCE)
    print("The Bridge core exists, but the production OAuth service is not ready.")
    ready, missing = readiness()
    if not ready:
        print("Unavailable; refusing to launch a mock or an unauthenticated MCP listener.")
        for item in missing:
            print(" - " + item)
        print("For the existing temporary mock use: make mcp-mock")
        return 1
    # Do not add a startup branch without an audited implementation.
    print("No production launcher configured.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
