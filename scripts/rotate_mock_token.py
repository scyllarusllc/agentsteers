"""Rotate the local mock-only MCP bearer token without exposing it.

Run as the non-root service owner with the temporary MCP session stopped.
This updates only ~/.config/agentsteers/mock-mcp.token, never Caddy or a process.
"""
from __future__ import annotations

import os
from pathlib import Path
import secrets
import socket
import stat
import sys
import tempfile


def assert_stopped(host="127.0.0.1", port=8766):
    # A running listener would retain the old credential in its environment.
    try:
        with socket.create_connection((host, port), timeout=0.25):
            raise RuntimeError(
                "Mock MCP port 8766 is active. Stop the make mcp session or "
                "supervised mock service before rotating; restart it afterwards."
            )
    except (ConnectionRefusedError, TimeoutError):
        return
    except OSError as exc:
        # Unknown network errors are NOT evidence that the old service stopped.
        raise RuntimeError("Cannot verify Mock MCP is stopped; refusing rotation") from exc


def rotate_token(secret_file: Path, *, require_stopped=True) -> None:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        raise RuntimeError("Run as the non-root owner, not sudo/root")
    if require_stopped:
        assert_stopped()
    directory = secret_file.parent
    # Do not follow symlinks in any of the private path components.
    if secret_file.is_symlink() or directory.is_symlink():
        raise RuntimeError("Refusing token path symlink")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
        raise RuntimeError("Private token directory must be owned by current user")
    if stat.S_IMODE(info.st_mode) != 0o700:
        raise RuntimeError("Private token directory must be mode 0700")
    if secret_file.exists():
        info = secret_file.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600):
            raise RuntimeError("Existing token must be a regular user-owned 0600 file")
    token = secrets.token_urlsafe(48)
    fd, temporary = tempfile.mkstemp(prefix=".mock-mcp.rotate-", dir=str(directory))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(token + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, secret_file)
        # Make replacement durable before announcing a successful rotation.
        dirfd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> int:
    try:
        rotate_token(Path.home() / ".config" / "agentsteers" / "mock-mcp.token")
    except (RuntimeError, OSError) as exc:
        print(f"Token rotation refused: {exc}", file=sys.stderr)
        return 1
    print("Mock MCP token rotated in private file (secret not displayed).")
    print("Restart make mcp to load it; update any private client credential.")
    print("Standalone AGENTSTEERS_MCP_MOCK_TOKEN environments must be updated separately.")
    print("This does not rotate OAuth credentials or prove a live deployment.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
