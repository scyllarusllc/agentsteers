"""Private Frappe OAuth MCP configuration: interactive setup, preflight, and launch.

No secrets are stored in Git or printed. Never configures Caddy or starts Codex.
"""
from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path
import stat
import sys

from scripts.check_frappe_mcp_auth import REQUIRED, RESOURCE, validate

CONFIG = Path.home() / ".config" / "agentsteers" / "frappe-oauth.env"
KEYS = ("AGENTSTEERS_FRAPPE_CLIENT_ID", "AGENTSTEERS_FRAPPE_CLIENT_SECRET",
        "AGENTSTEERS_FRAPPE_SUBJECTS", "AGENTSTEERS_FRAPPE_REPOS")
DEFAULTS = {
    "AGENTSTEERS_FRAPPE_OAUTH_ENABLED": "1",
    "AGENTSTEERS_FRAPPE_ISSUER": "https://agentsteers.com",
    "AGENTSTEERS_FRAPPE_MCP_RESOURCE": RESOURCE,
    "AGENTSTEERS_FRAPPE_REPOS": "scyllarusllc/agentsteers",
}


def read_private_config():
    if not CONFIG.exists():
        return {}
    metadata = CONFIG.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid() or metadata.st_mode & 0o077:
        raise ValueError(f"Private config must be a regular file owned by this user with mode 600: {CONFIG}")
    out = {}
    with CONFIG.open(encoding="utf-8") as fh:
        for num, line in enumerate(fh, 1):
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                raise ValueError(f"Invalid private config line {num}")
            key, val = line.split("=", 1)
            if key not in (*KEYS, "AGENTSTEERS_FRAPPE_ISSUER", "AGENTSTEERS_FRAPPE_MCP_RESOURCE"):
                raise ValueError(f"Unexpected config key on line {num}")
            if any(c in val for c in "\r\x00"):
                raise ValueError(f"Invalid private config value on line {num}")
            out[key] = val
    return out


def environment():
    values = dict(DEFAULTS)
    values.update(read_private_config())
    values.update({k: v for k, v in os.environ.items() if k.startswith("AGENTSTEERS_FRAPPE_")})
    values["AGENTSTEERS_FRAPPE_OAUTH_ENABLED"] = "1"
    return values


def preflight(env):
    missing = [key for key in REQUIRED if not env.get(key, "").strip()]
    if missing:
        raise ValueError("Missing required Frappe OAuth settings:\n  " + "\n  ".join(missing)
                         + "\nRun 'make mcp-auth-setup' to configure them privately.")
    validate(env)


def setup():
    previous = read_private_config()
    config = dict(previous)
    print("Configure Frappe OAuth MCP credentials locally. No values are sent to GitHub.")
    print("First register an OAuth Client in Frappe; use its real Client ID and Client Secret.")
    print("Press Enter to keep an existing value. Client Secret will not be displayed.")
    for key in ("AGENTSTEERS_FRAPPE_ISSUER", *KEYS):
        default = previous.get(key, DEFAULTS.get(key, ""))
        label = key + (" [configured]" if key == "AGENTSTEERS_FRAPPE_CLIENT_SECRET" and default else
                       " [" + default + "]" if default and key != "AGENTSTEERS_FRAPPE_CLIENT_SECRET" else "")
        value = (getpass.getpass(label + ": ") if key == "AGENTSTEERS_FRAPPE_CLIENT_SECRET"
                 else input(label + ": ")).strip()
        if value:
            if any(c in value for c in "\r\n\x00"):
                raise ValueError(f"Invalid {key}")
            config[key] = value
        elif default:
            config[key] = default
    config["AGENTSTEERS_FRAPPE_MCP_RESOURCE"] = RESOURCE
    candidate = dict(DEFAULTS)
    candidate.update(config)
    candidate["AGENTSTEERS_FRAPPE_OAUTH_ENABLED"] = "1"
    preflight(candidate)
    CONFIG.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if CONFIG.is_symlink():
        raise ValueError("Refusing symlinked private config")
    temp = CONFIG.with_name(CONFIG.name + ".tmp-" + str(os.getpid()))
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            for key in ("AGENTSTEERS_FRAPPE_ISSUER", *KEYS, "AGENTSTEERS_FRAPPE_MCP_RESOURCE"):
                out.write(key + "=" + config[key] + "\n")
        os.replace(temp, CONFIG)
    finally:
        if temp.exists():
            temp.unlink()
    print(f"Private OAuth settings saved to {CONFIG} (mode 600).")
    print("This only validates configuration structure; real OAuth login is not yet verified.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("setup", "check", "start"))
    action = parser.parse_args().action
    try:
        if action == "setup":
            setup()
            return 0
        env = environment()
        preflight(env)
        if action == "check":
            print("Frappe OAuth MCP configuration: structural checks passed.")
            print("No live Frappe token introspection, ChatGPT login, or public routing verified.")
            return 0
        print("Starting Frappe OAuth Mock MCP on localhost:8767 only; no Caddy changes or Codex.", flush=True)
        os.execvpe(".venv/bin/python", [".venv/bin/python", "-m", "gunicorn",
                    "--bind", "127.0.0.1:8767", "--workers", "1",
                    "agentsteers.frappe_oauth_wsgi:application"],
                   {**os.environ, **env, "PYTHONPATH": "src"})
    except (ValueError, OSError, EOFError, KeyboardInterrupt) as exc:
        print(f"Frappe OAuth MCP configuration failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
