#!/usr/bin/env python3
"""Restart only a verified, same-user AgentSteers localhost development listener.

Linux (/proc) only. Never terminate a process based solely on its port number.
"""
from __future__ import annotations

import os
from pathlib import Path
import signal
import socket
import sys
import time

PORT = 8765
ROOT = Path(__file__).resolve().parent.parent


def listeners(port: int = PORT) -> set[str]:
    """Linux socket inode(s) in TCP LISTEN state for the development port."""
    result: set[str] = set()
    for name in ("tcp", "tcp6"):
        try:
            lines = Path("/proc/net", name).read_text().splitlines()[1:]
        except OSError as exc:
            raise RuntimeError(f"Cannot inspect /proc/net/{name}: {exc}") from exc
        for line in lines:
            fields = line.split()
            if len(fields) > 9 and fields[3] == "0A":
                try:
                    listener_port = int(fields[1].rsplit(":", 1)[1], 16)
                except ValueError:
                    continue
                if listener_port == port:
                    result.add(fields[9])
    return result


def matching_pids(inodes: set[str]) -> dict[str, set[int]]:
    owners = {inode: set() for inode in inodes}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            for fd in (entry / "fd").iterdir():
                try:
                    target = os.readlink(fd)
                except (OSError, PermissionError):
                    continue
                if target.startswith("socket:[") and target.endswith("]"):
                    inode = target[8:-1]
                    if inode in owners:
                        owners[inode].add(int(entry.name))
        except (OSError, PermissionError):
            continue
    return owners


def is_our_dev_process(pid: int) -> bool:
    proc = Path("/proc", str(pid))
    try:
        if proc.stat().st_uid != os.getuid():
            return False
        if (proc / "cwd").resolve(strict=True) != ROOT.resolve(strict=True):
            return False
        argv = (proc / "cmdline").read_bytes().split(b"\0")
        return any(
            argv[i] == b"-m" and argv[i + 1] == b"agentsteers.http_server"
            for i in range(len(argv) - 1)
        )
    except (OSError, PermissionError):
        return False


def main() -> int:
    try:
        inodes = listeners()
        if not inodes:
            return 0
        mapping = matching_pids(inodes)
        pids = set().union(*mapping.values())
        if not pids or any(not mapping[inode] for inode in inodes) or len(pids) != 1:
            raise RuntimeError("Port has an unknown or ambiguous listener; refusing to kill it.")
        pid = next(iter(pids))
        if not is_our_dev_process(pid):
            raise RuntimeError(
                f"Port {PORT} belongs to PID {pid}, not this project's own dev server. "
                "Stop the service manually or choose a different port."
            )
        # Reconfirm the bound listener just before terminating it.
        if not inodes.issubset(listeners()) or not is_our_dev_process(pid):
            raise RuntimeError("Listener changed during inspection; refusing to stop it.")
        print(f"Stopping previous AgentSteers dev server (PID {pid})...", flush=True)
        os.kill(pid, signal.SIGTERM)
        for _ in range(50):
            if not listeners().intersection(inodes):
                print("Previous development server released the port.", flush=True)
                return 0
            time.sleep(0.1)
        raise RuntimeError("Previous dev server did not stop; refusing to force-kill it.")
    except (OSError, RuntimeError) as exc:
        print(f"Cannot safely free port {PORT}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
