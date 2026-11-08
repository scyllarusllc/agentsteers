#!/usr/bin/env python3
"""Inspect or safely correct the production Frappe public host_name for OAuth."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from publish_frappe import DOMAIN, ROOT, _looks_like_bench, resolve_bench

EXPECTED = "https://" + DOMAIN


def find_bench_cli(bench: Path) -> str:
    """Use the same CLI resolution order as make publish."""
    for candidate in (bench / "env" / "bin" / "bench",
                      ROOT / ".bench-cli-venv" / "bin" / "bench"):
        if candidate.is_file():
            return str(candidate)
    found = shutil.which("bench")
    if not found:
        raise RuntimeError("Bench CLI not found (checked Bench venv, project CLI venv, PATH).")
    return found


def configure(bench: Path, action: str, *, bench_cli: str | None = None) -> int:
    if action not in {"check", "fix"}:
        raise ValueError("Action must be check or fix.")
    if not _looks_like_bench(bench, DOMAIN):
        raise RuntimeError("Production Bench/site validation failed; no changes made.")
    config_path = bench / "sites" / DOMAIN / "site_config.json"
    if config_path.is_symlink() or not config_path.is_file():
        raise RuntimeError("Unsafe or missing site_config.json; no changes made.")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    current = config.get("host_name")
    print(f"Site: {DOMAIN}")
    print(f"Configured host_name: {current if isinstance(current, str) else '(not set)'}")
    print(f"Expected public host_name: {EXPECTED}")
    print("Note: OAuth redirect URI may also depend on Caddy forwarded headers and Frappe settings.")
    if action == "check":
        print("PASS: host_name matches." if current == EXPECTED else "CHECK NEEDED: host_name differs.")
        return 0 if current == EXPECTED else 1
    if current == EXPECTED:
        print("Already correct; no changes made.")
        return 0
    if not sys.stdin.isatty():
        raise RuntimeError("Interactive terminal required; no changes made.")
    answer = input(f"Type FIX {DOMAIN} to back up and update host_name: ").strip()
    if answer != f"FIX {DOMAIN}":
        print("Cancelled; no changes made.")
        return 1
    backup = config_path.with_name("site_config.json.before-google-login-" +
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".bak")
    if backup.exists():
        raise RuntimeError("Backup path already exists; no changes made.")
    # Resolve CLI before creating a backup or modifying anything.
    cli = bench_cli or find_bench_cli(bench)
    shutil.copy2(config_path, backup)
    backup.chmod(0o600)
    print(f"Backup created: {backup} (contains secrets; keep private)")
    subprocess.run([cli, "--site", DOMAIN, "set-config", "host_name", EXPECTED],
                   cwd=bench, check=True)
    updated = json.loads(config_path.read_text(encoding="utf-8"))
    if updated.get("host_name") != EXPECTED:
        raise RuntimeError("host_name verification failed; review site config and backup.")
    print("host_name updated and verified.")
    subprocess.run([cli, "--site", DOMAIN, "clear-cache"], cwd=bench, check=True)
    subprocess.run([cli, "--site", DOMAIN, "clear-website-cache"], cwd=bench, check=True)
    print("Caches cleared. Test Google login again; inspect actual redirect_uri if :8000 persists.")
    return 0


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"check", "fix"}:
        print("Usage: manage_google_login.py check|fix", file=sys.stderr)
        return 2
    return configure(resolve_bench(DOMAIN), sys.argv[1])


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Google login configuration check failed: {exc}", file=sys.stderr)
        sys.exit(1)
