#!/usr/bin/env python3
"""Read-only local readiness report for the optional AgentSteers mock MCP host.

Does NOT start services, install dependencies, query secret values, write
files, read mail, contact network endpoints, or run the test suite.
Usage: python3 scripts/check_mock_mcp_host.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import pwd
import re
import shutil
import socket
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]
HOST_RE = re.compile(r"^[a-z0-9.-]+(?::[0-9]{1,5})?$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def finding(name, ok, detail):
    return {"check": name, "status": "ready" if ok else "needs_attention", "detail": detail}


def private_file(path):
    if not path.is_file() or path.is_symlink():
        return False
    return not bool(path.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO))


def inspect():
    items = []
    try:
        user = pwd.getpwuid(os.geteuid()).pw_name
    except KeyError:
        user = "unknown"
    items.append(finding("non_root_account", os.geteuid() != 0,
                         "Current account: " + user + " (no credentials shown)"))
    for filename in ("src/agentsteers/mock_http_mcp.py",
                     "src/agentsteers/persistent_mock_jobs.py",
                     "deploy/agentsteers-mock-mcp.service.example",
                     "deploy/Caddyfile.mock-mcp"):
        target = ROOT / filename
        items.append(finding("source_" + filename, target.is_file(),
                             "Found" if target.is_file() else "Missing"))
    gunicorn = ROOT / ".venv/bin/gunicorn"
    items.append(finding("local_gunicorn", gunicorn.is_file(),
                         "Python Gunicorn executable present in project venv" if gunicorn.is_file()
                         else "No project Gunicorn at .venv/bin/gunicorn"))
    items.append(finding("caddy_binary", bool(shutil.which("caddy")),
                         "Caddy binary found in PATH" if shutil.which("caddy")
                         else "No Caddy binary found in current PATH; proxy may be remote"))
    enabled = os.getenv("AGENTSTEERS_MCP_MOCK_ENABLED") == "1"
    items.append(finding("explicit_mock_enablement", enabled,
                         "Enabled in current process environment" if enabled
                         else "Disabled or not present in current process environment"))
    host = os.getenv("AGENTSTEERS_MCP_MOCK_HOST", "").lower()
    good_host = bool(host) and bool(HOST_RE.fullmatch(host)) and ".." not in host
    items.append(finding("exact_host", good_host,
                         "Host string syntax valid" if good_host
                         else "Set exact approved hostname in protected service environment"))
    allowed = [x.strip() for x in os.getenv("AGENTSTEERS_MCP_MOCK_REPOS", "").split(",") if x.strip()]
    items.append(finding("repository_allowlist", bool(allowed) and all(REPO_RE.fullmatch(x) for x in allowed),
                         "Repository allowlist syntax valid" if allowed and all(REPO_RE.fullmatch(x) for x in allowed)
                         else "Repository allowlist missing or malformed"))
    token = os.getenv("AGENTSTEERS_MCP_MOCK_TOKEN", "")
    items.append(finding("private_bearer_token", len(token) >= 32 and not any(c in token for c in "\r\n"),
                         "Token length and basic syntax acceptable; token never printed" if len(token) >= 32 and not any(c in token for c in "\r\n")
                         else "Token missing or malformed; token never printed"))
    db_value = os.getenv("AGENTSTEERS_MCP_MOCK_DB", "")
    db = Path(db_value) if db_value else None
    if not db or not db.is_absolute():
        items.append(finding("private_sqlite", False, "Persistent SQLite absolute path not configured"))
    else:
        parent = db.parent
        parent_ok = parent.is_dir() and not parent.is_symlink() and not bool(parent.stat().st_mode & (stat.S_IWGRP | stat.S_IWOTH))
        db_ok = not db.exists() or private_file(db)
        items.append(finding("private_sqlite", parent_ok and db_ok,
                             "Private state directory and database permissions acceptable"
                             if parent_ok and db_ok else
                             "Private SQLite parent is unavailable/unsafe or database permissions are too broad"))
    # Inspect the kernel's proc table only; do not connect, bind or stop anything.
    # The port must be free before provisioning, but later expected to be listening
    # once the service has been separately enabled.
    port_hex = f"{8766:04X}"
    listeners = []
    for table in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            lines = Path(table).read_text().splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            fields = line.split()
            if len(fields) >= 4 and fields[3] == "0A":
                port = fields[1].rsplit(":", 1)[-1]
                if port == port_hex:
                    listeners.append(fields[1])
    items.append({"check": "port_8766_listener", "status": "informational",
                  "detail": "TCP listener present; verify loopback-only ownership" if listeners
                  else "No TCP LISTEN entry observed on port 8766"})
    return {"scope": "local_read_only_preflight", "service_started": False,
            "tests_executed": False, "remote_connection_verified": False,
            "ready": all(x["status"] != "needs_attention" for x in items),
            "checks": items}


if __name__ == "__main__":
    print(json.dumps(inspect(), indent=2))
    sys.exit(0)  # Always informational: never abort or alter system state.
