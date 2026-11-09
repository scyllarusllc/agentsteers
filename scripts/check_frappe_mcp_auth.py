"""Preflight for the opt-in Frappe OAuth MCP localhost listener.

No network calls, Caddy edits, secrets printed or server process launches.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

RESOURCE = "https://mcp.agentsteers.com/mcp"
REQUIRED = ("AGENTSTEERS_FRAPPE_ISSUER", "AGENTSTEERS_FRAPPE_CLIENT_ID",
            "AGENTSTEERS_FRAPPE_CLIENT_SECRET", "AGENTSTEERS_FRAPPE_SUBJECTS",
            "AGENTSTEERS_FRAPPE_REPOS", "AGENTSTEERS_FRAPPE_MCP_RESOURCE")


def validate(env):
    if env.get("AGENTSTEERS_FRAPPE_OAUTH_ENABLED") != "1":
        raise ValueError("AGENTSTEERS_FRAPPE_OAUTH_ENABLED must equal 1")
    for key in REQUIRED:
        value = env.get(key, "")
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Missing {key}")
        if any(c in value for c in "\r\n\x00"):
            raise ValueError(f"Invalid {key}")
        if any(term in value.upper() for term in ("REPLACE_ME", "YOUR_", "EXAMPLE.COM")):
            raise ValueError(f"Unconfigured {key}")
    url = urlsplit(env["AGENTSTEERS_FRAPPE_ISSUER"])
    if (url.scheme != "https" or not url.hostname or url.username or url.password or
            url.query or url.fragment or url.path.endswith("/")):
        raise ValueError("Frappe issuer must be a trusted HTTPS URL without trailing slash")
    if env["AGENTSTEERS_FRAPPE_MCP_RESOURCE"] != RESOURCE:
        raise ValueError("MCP resource mismatch")
    for key in ("AGENTSTEERS_FRAPPE_SUBJECTS", "AGENTSTEERS_FRAPPE_REPOS"):
        if not all(part.strip() for part in env[key].split(",")):
            raise ValueError(f"Invalid {key}")
    # Frappe controls the issued credential length. Do not reject a real
    # non-empty OAuth client secret solely because it is shorter than 16 chars.
    # A missing, placeholder, or malformed secret is rejected above.
    return True


def main():
    try:
        validate(os.environ)
    except ValueError as exc:
        print(f"Frappe OAuth MCP config check FAILED: {exc}", file=sys.stderr)
        return 1
    print("Frappe OAuth MCP configuration: structural checks passed.")
    print("No live Frappe token introspection, ChatGPT OAuth login or public routing verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
