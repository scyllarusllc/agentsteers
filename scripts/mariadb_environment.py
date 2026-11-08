"""Non-destructive local MariaDB preflight for AgentSteers deployment.

Only offers an explicitly confirmed start of an existing MariaDB systemd unit.
Never installs packages, changes credentials, enables a service, or edits data.
"""
from __future__ import annotations

import json
import getpass
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time


def _database_endpoint(bench: Path | None, site: str) -> tuple[str, int]:
    config: dict = {}
    if bench is not None:
        for path in (bench / "sites" / "common_site_config.json",
                     bench / "sites" / site / "site_config.json"):
            if path.is_file():
                try:
                    data = json.loads(path.read_text())
                except (ValueError, OSError) as exc:
                    raise RuntimeError(f"Cannot read database configuration in {path}: {exc}") from exc
                if isinstance(data, dict):
                    config.update(data)
    return str(config.get("db_host") or "127.0.0.1"), int(config.get("db_port") or 3306)


def _connects(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False



def _show_start_failure_diagnostics() -> None:
    """Read-only diagnostics; never attempt another privileged action."""
    commands = [
        ["systemctl", "status", "mariadb", "--no-pager", "-l"],
        ["journalctl", "-u", "mariadb", "-n", "50", "--no-pager"],
    ]
    for command in commands:
        print("\n--- " + " ".join(command) + " ---", flush=True)
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=15)
            detail = (result.stdout + "\n" + result.stderr).strip()
            if detail:
                print(detail, flush=True)
            if result.returncode and command[0] == "journalctl":
                print("Journal access may require elevated privileges.", flush=True)
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"Could not read diagnostics: {exc}", flush=True)
    print("If journal entries are restricted, run: "
          "sudo journalctl -u mariadb -n 50 --no-pager", flush=True)



def _authorize_mariadb_start(systemctl: str) -> None:
    """One-time root-password authorization via su's native TTY prompt."""
    if getpass.getuser() != "frappe":
        raise RuntimeError("Automatic sudoers setup is restricted to the frappe account.")
    if systemctl not in ("/usr/bin/systemctl", "/bin/systemctl"):
        raise RuntimeError(f"Unexpected systemctl location: {systemctl}")
    if not shutil.which("su"):
        raise RuntimeError("su is unavailable; ask the server administrator to configure sudoers.")
    print("The frappe account cannot start MariaDB with sudo.", flush=True)
    print("One-time setup can add a sudoers rule allowing ONLY MariaDB service start.", flush=True)
    print("The system 'su' command will ask for the root password directly; "
          "the deployment script does not collect or store it.", flush=True)
    answer = input("Type AUTHORIZE FRAPPE to configure that rule: ").strip()
    if answer != "AUTHORIZE FRAPPE":
        raise RuntimeError("Root authorization was not approved; deployment stopped.")
    # Run only a fixed, tightly scoped root command. No project script or
    # user-provided strings are executed as root, and visudo validates syntax.
    rule = f"frappe ALL=(root) NOPASSWD: {systemctl} start mariadb.service"
    command = (
        "set -eu; "
        "tmp=$(mktemp /etc/sudoers.d/.agentsteers-mariadb.XXXXXX); "
        'trap \'rm -f "$tmp"\' EXIT; '
        f'printf "%s\\n" "{rule}" > "$tmp"; '
        'chmod 0440 "$tmp"; '
        'visudo -cf "$tmp"; '
        'mv -f "$tmp" /etc/sudoers.d/agentsteers-mariadb'
    )
    result = subprocess.run(["su", "-c", command], check=False)
    if result.returncode:
        raise RuntimeError("Root authentication or sudoers validation failed; "
                           "no MariaDB privileges were granted.")
    print("Installed restricted sudoers entry for frappe.", flush=True)



def ensure_mariadb(bench: Path | None = None, site: str = "agentsteers.com",
                   *, check_only: bool = False) -> None:
    """Check TCP MariaDB reachability; offer local service start with consent."""
    host, port = _database_endpoint(bench, site)
    if host not in ("localhost", "127.0.0.1", "::1"):
        print(f"External database configured ({host}:{port}); skipping local MariaDB service handling.", flush=True)
        return
    if _connects(host, port):
        print(f"Database TCP endpoint reachable at {host}:{port}.", flush=True)
        return

    failure = (f"Cannot connect to MariaDB/MySQL at {host}:{port}. "
               "Check the configured database host, port, and service logs.")
    if check_only:
        raise RuntimeError(failure + " Read-only check: no repair attempted.")
    if not shutil.which("systemctl"):
        raise RuntimeError(failure + " systemctl unavailable; start the configured database manually.")

    unit = subprocess.run(["systemctl", "show", "mariadb.service",
                           "--property=LoadState", "--value"],
                          capture_output=True, text=True)
    if unit.returncode or unit.stdout.strip() != "loaded":
        raise RuntimeError(failure + " mariadb.service not installed/loaded. "
                           "No packages were installed automatically.")

    active = subprocess.run(["systemctl", "is-active", "--quiet", "mariadb.service"])
    if active.returncode == 0:
        raise RuntimeError(failure + " MariaDB service is already active; "
                           "check bind-address, port, and site configuration.")

    if not sys.stdin.isatty():
        raise RuntimeError(failure + " Interactive terminal required before starting a system service.")
    systemctl = shutil.which("systemctl")
    if not systemctl or not shutil.which("sudo"):
        raise RuntimeError("systemctl or sudo unavailable; ask your server administrator.")
    answer = input("Type START MARIADB to attempt service start: ").strip()
    if answer != "START MARIADB":
        raise RuntimeError("MariaDB start was not authorized; deployment stopped.")

    permission = subprocess.run(
        ["sudo", "-n", "-l", systemctl, "start", "mariadb.service"],
        capture_output=True, text=True)
    if permission.returncode:
        _authorize_mariadb_start(systemctl)
    try:
        subprocess.run(["sudo", "-n", systemctl, "start", "mariadb.service"], check=True)
    except subprocess.CalledProcessError as exc:
        print("MariaDB start failed; collecting read-only service diagnostics.", flush=True)
        _show_start_failure_diagnostics()
        raise RuntimeError(
            "MariaDB service failed to start; see systemctl status and journal logs above."
        ) from exc
    for _ in range(10):
        if _connects(host, port):
            print(f"MariaDB service started; {host}:{port} is reachable.", flush=True)
            return
        time.sleep(1)
    raise RuntimeError(failure + " Service start was attempted but TCP is still unavailable.")
