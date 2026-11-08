#!/usr/bin/env python3
"""Manage only the existing, dedicated AgentSteers production web systemd unit."""
from __future__ import annotations
import os
from pathlib import Path
import shutil
import subprocess
import sys
from publish_frappe import DOMAIN, resolve_bench, _looks_like_bench

UNIT = "agentsteers-web.service"
UNIT_PATH = Path("/etc/systemd/system") / UNIT


def output(*args: str) -> str:
    return subprocess.run(args, text=True, capture_output=True, check=True).stdout.strip()


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in {"list", "start", "stop", "restart"}:
        raise RuntimeError("Usage: manage_website.py {list|start|stop|restart}")
    action = sys.argv[1]
    if not UNIT_PATH.is_file() or UNIT_PATH.is_symlink():
        raise RuntimeError(f"Dedicated systemd unit missing or invalid: {UNIT_PATH}")
    bench = resolve_bench(DOMAIN)
    if not _looks_like_bench(bench, DOMAIN):
        raise RuntimeError("Dedicated production Bench/site could not be verified.")
    working = output("systemctl", "show", UNIT, "--property=WorkingDirectory", "--value")
    expected = str(bench.resolve() / "sites")
    if working != expected:
        raise RuntimeError(f"Service WorkingDirectory mismatch; expected {expected}, got {working!r}. No changes made.")
    print(f"Production site: {DOMAIN}; unit: {UNIT}; Bench: {bench}", flush=True)
    if action == "list":
        for key in ("LoadState", "ActiveState", "SubState", "UnitFileState"):
            print(f"{key}: {output('systemctl', 'show', UNIT, '--property=' + key, '--value')}")
        return
    if action == "stop":
        if not sys.stdin.isatty():
            raise RuntimeError("Stopping production requires an interactive terminal.")
        answer = input(f"Stopping {DOMAIN} will take the website offline. Type STOP {DOMAIN} to continue: ")
        if answer.strip() != f"STOP {DOMAIN}":
            raise RuntimeError("Stop cancelled.")
    command = ["systemctl", action, UNIT]
    if os.geteuid() != 0:
        if not sys.stdin.isatty() or not shutil.which("su"):
            raise RuntimeError("Interactive Linux root authentication required.")
        command = ["su", "-c", " ".join(command)]
    subprocess.run(command, check=True)
    state = output("systemctl", "show", UNIT, "--property=ActiveState", "--value")
    expected_state = "inactive" if action == "stop" else "active"
    if state != expected_state:
        raise RuntimeError(f"Service operation returned but state is {state}, expected {expected_state}.")
    print(f"{UNIT}: {state}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f"Website service management failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
