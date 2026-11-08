"""Non-destructive local MariaDB preflight for AgentSteers deployment.

Only offers an explicitly confirmed start of an existing MariaDB systemd unit.
Never installs packages, changes credentials, enables a service, or edits data.
"""
from __future__ import annotations

import json
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
    print("Existing MariaDB service appears stopped. This may require your sudo password.", flush=True)
    answer = input("Type START MARIADB to run 'sudo systemctl start mariadb': ").strip()
    if answer != "START MARIADB":
        raise RuntimeError("MariaDB start was not authorized; deployment stopped.")

    if not shutil.which("sudo"):
        raise RuntimeError("sudo unavailable; start mariadb.service through your administrator.")
    subprocess.run(["sudo", "systemctl", "start", "mariadb"], check=True)
    for _ in range(10):
        if _connects(host, port):
            print(f"MariaDB service started; {host}:{port} is reachable.", flush=True)
            return
        time.sleep(1)
    raise RuntimeError(failure + " Service start was attempted but TCP is still unavailable.")
