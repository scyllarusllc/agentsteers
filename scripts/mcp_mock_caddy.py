"""Preview or enable the standalone mock MCP hostname in an existing Caddyfile.

No website routes are replaced. Only an exact, standalone mcp.agentsteers.com
block that still has the project's 503 prelaunch response can be changed.
Uses a separate already-running mock-only WSGI backend. Does not start Codex.
"""
from __future__ import annotations

import argparse
import datetime
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "deploy" / "Caddyfile.mock-mcp"
SITE = re.compile(r"(?m)^mcp\.agentsteers\.com\s*\{")
PRELAUNCH = 'respond "AgentSteers MCP endpoint not yet enabled" 503'
BACKEND = "127.0.0.1:8766"


def replace_site(config: str, replacement: str) -> str:
    matches = list(SITE.finditer(config))
    if len(matches) != 1:
        raise ValueError("Expected exactly one top-level mcp.agentsteers.com block in Caddyfile")
    start = matches[0].start()
    # Count block braces. Reject unusual constructions rather than guessing.
    pos = matches[0].end() - 1
    depth = 0
    end = None
    for index in range(pos, len(config)):
        if config[index] == "{":
            depth += 1
        elif config[index] == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    if end is None:
        raise ValueError("MCP site block has unbalanced braces")
    existing = config[start:end]
    if PRELAUNCH not in existing and f"reverse_proxy {BACKEND}" not in existing:
        raise ValueError("Refusing to replace an unknown MCP site configuration")
    if "import " in existing or "{" in existing.replace("{", "", 1).replace(
        "header {", "").replace("handle /mcp {", ""):
        # Avoid attempting to rewrite an unexpectedly complex site.
        raise ValueError("MCP site configuration is nonstandard; review it manually")
    return config[:start] + replacement.rstrip() + config[end:]


def run_caddy(*args):
    binary = shutil.which("caddy")
    if binary is None:
        raise RuntimeError("Caddy is not installed or not on PATH")
    subprocess.run([binary, *args], check=True)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="/tpdata/caddy/config.json" if Path("/tpdata/caddy/config.json").is_file() else "/etc/caddy/Caddyfile", help="Active Caddy JSON or Caddyfile")
    p.add_argument("--apply", action="store_true", help="Apply after validation and explicit confirmation")
    args = p.parse_args(argv)
    path = Path(args.config).resolve()
    if path.suffix.lower() == '.json':
        if args.apply:
            raise RuntimeError('Docker JSON changes use the supervised temporary session: run make mcp. '
                               'It handles root authentication, validation, backup and route restoration.')
        print('Docker JSON adapter: temporary mcp.agentsteers.com/mcp -> 127.0.0.1:8766.')
        print('Preserves Host=mcp.agentsteers.com and sets X-Forwarded-Proto=https for the guarded mock.')
        print('Other host routes are preserved. Run make mcp to validate/activate after confirmation.')
        print('This installation requires restarting Caddy alone for activation and restoration.')
        return 0
    original = path.read_text()
    replacement = TEMPLATE.read_text()
    candidate = replace_site(original, replacement)
    if candidate == original:
        print("MCP host already matches the mock proxy template; no changes.")
        return 0
    if not args.apply:
        print("PREVIEW ONLY. This command will replace the MCP host's 503 block:")
        print(replacement)
        print("Existing non-MCP website blocks will remain unchanged.")
        print("Run 'make mcp-mock-proxy-apply' to validate and apply.")
        return 0

    with socket.create_connection(("127.0.0.1", 8766), timeout=2):
        pass
    reply = input("Type ENABLE MOCK MCP to activate public MCP proxy: ").strip()
    if reply != "ENABLE MOCK MCP":
        print("Cancelled. Caddy remains unchanged.")
        return 1

    # Temporary candidate lives beside the original for relative imports.
    with tempfile.NamedTemporaryFile(
        mode="w", prefix=".agentsteers-mcp-", suffix=".caddy",
        dir=path.parent, delete=False
    ) as staging:
        staging.write(candidate)
        staged = Path(staging.name)
    try:
        run_caddy("validate", "--config", str(staged), "--adapter", "caddyfile")
        now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = path.with_name(path.name + ".agentsteers-mcp-backup-" + now)
        shutil.copy2(path, backup)
        try:
            # Preserve Caddyfile ownership and permissions (staging file is 0600).
            shutil.copyfile(staged, path)
            run_caddy("reload", "--config", str(path), "--adapter", "caddyfile")
        except Exception:
            shutil.copy2(backup, path)
            try:
                run_caddy("reload", "--config", str(path), "--adapter", "caddyfile")
            except Exception:
                print("Rollback reload failed. Inspect Caddy immediately.", file=sys.stderr)
            raise
        print(f"Mock MCP HTTPS proxy enabled. Original Caddyfile backup: {backup}")
        print("Verify HTTPS 401 without token and MCP initialize with a valid token.")
        return 0
    finally:
        staged.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"MCP proxy not enabled: {exc}", file=sys.stderr)
        raise SystemExit(1)
