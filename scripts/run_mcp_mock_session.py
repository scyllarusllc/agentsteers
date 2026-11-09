"""One-command interactive MCP mock test session.

Starts no Codex process. The session owns a single loopback Gunicorn process
and restores the original MCP proxy configuration when it exits normally.
Not a persistent system service; use dedicated deployment for 24/7 operation.
"""
from __future__ import annotations

import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time

from mcp_mock_caddy import replace_site, run_caddy, TEMPLATE

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "bin" / "python"
CADDY = Path(os.environ.get("CADDY_CONFIG", "/etc/caddy/Caddyfile"))
SECRET_FILE = Path.home() / ".config" / "agentsteers" / "mock-mcp.token"
HOST = "mcp.agentsteers.com"
PORT = 8766


def check_venv():
    if not PYTHON.is_file():
        print("Creating isolated Python virtual environment for Mock MCP...")
        subprocess.run([sys.executable, "-m", "venv", str(ROOT / ".venv")], check=True)
    try:
        subprocess.run([str(PYTHON), "-m", "gunicorn", "--version"], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        print("Installing mock HTTP server dependency into the existing venv...")
        subprocess.run([str(PYTHON), "-m", "pip", "install", "gunicorn>=21,<24"], check=True)


def test_suite():
    for filename in ("test_mock_http_mcp.py", "test_remote_mcp_guard.py",
                     "test_mcp_mock_caddy.py"):
        env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
        subprocess.run([str(PYTHON), "-m", "unittest", "discover",
                        "-s", "tests", "-p", filename, "-v"],
                       cwd=ROOT, env=env, check=True)


def token_from_private_file():
    SECRET_FILE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    SECRET_FILE.parent.chmod(0o700)
    if SECRET_FILE.exists():
        if SECRET_FILE.is_symlink() or SECRET_FILE.stat().st_mode & 0o077:
            raise RuntimeError("Token file must not be a symlink and must be private (0600)")
        token = SECRET_FILE.read_text().strip()
    else:
        token = secrets.token_urlsafe(48)
        descriptor = os.open(SECRET_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as out:
            out.write(token + "\n")
    if len(token) < 32 or any(c in token for c in "\r\n"):
        raise RuntimeError("Invalid private token")
    print(f"Bearer token is stored locally in {SECRET_FILE} (not printed).")
    return token


def ready(proc):
    for _ in range(40):
        if proc.poll() is not None:
            raise RuntimeError("Mock MCP process exited before startup")
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=0.2):
                return
        except OSError:
            time.sleep(0.15)
    raise RuntimeError("Mock MCP did not start listening on loopback")


def write_proxy(original, new_config):
    if CADDY.read_text() != original:
        raise RuntimeError("Caddyfile changed concurrently; refusing to overwrite")
    # Preserve original ownership/permissions and keep a recoverable backup.
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    backup = CADDY.with_name(CADDY.name + ".mcp-session-" + stamp)
    if backup.exists():
        raise RuntimeError("Caddy backup already exists")
    import shutil
    shutil.copy2(CADDY, backup)
    try:
        CADDY.write_text(new_config)
        run_caddy("reload", "--config", str(CADDY), "--adapter", "caddyfile")
    except BaseException:
        shutil.copy2(backup, CADDY)
        try:
            run_caddy("reload", "--config", str(CADDY), "--adapter", "caddyfile")
        except Exception:
            print("WARNING: rollback reload failed; inspect Caddy.", file=sys.stderr)
        raise
    return backup


def main():
    check_venv()
    test_suite()
    token = token_from_private_file()
    if not CADDY.is_file():
        raise RuntimeError(f"Missing real Caddyfile: {CADDY}")
    original = CADDY.read_text()
    candidate = replace_site(original, TEMPLATE.read_text())
    # We only promise temporary activation from the 503 prelaunch state.
    if candidate == original:
        raise RuntimeError("MCP proxy is already enabled; refusing to own an existing live route")
    if 'respond "AgentSteers MCP endpoint not yet enabled" 503' not in original:
        raise RuntimeError("Expected MCP 503 prelaunch state; refusing to replace live route")
    print(f"Mock server: 127.0.0.1:{PORT}; public route: https://{HOST}/mcp")
    print("This is a temporary test session; Ctrl+C will restore Caddy's original config.")
    answer = input("Type ENABLE MOCK MCP to start the session: ").strip()
    if answer != "ENABLE MOCK MCP":
        print("Cancelled without changing Caddy.")
        return 0

    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"),
               AGENTSTEERS_MCP_MOCK_ENABLED="1",
               AGENTSTEERS_MCP_MOCK_TOKEN=token,
               AGENTSTEERS_MCP_MOCK_HOST=HOST,
               AGENTSTEERS_MCP_MOCK_REPOS="scyllarusllc/agentsteers")
    proc = None
    backup = None
    try:
        proc = subprocess.Popen([str(PYTHON), "-m", "gunicorn",
                                 "--bind", f"127.0.0.1:{PORT}", "--workers", "1",
                                 "agentsteers.mock_http_mcp:application"],
                                cwd=ROOT, env=env)
        ready(proc)
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".caddy", dir=CADDY.parent) as staging:
            staging.write(candidate)
            staging.flush()
            run_caddy("validate", "--config", staging.name, "--adapter", "caddyfile")
        backup = write_proxy(original, candidate)
        print("Mock MCP test route is active. No Codex execution. Press Ctrl+C to shut down.")
        while proc.poll() is None:
            time.sleep(0.5)
        raise RuntimeError("Mock server exited unexpectedly")
    except KeyboardInterrupt:
        print("\nStopping mock MCP test session...")
    finally:
        if backup is not None:
            try:
                if CADDY.read_text() == candidate:
                    import shutil
                    shutil.copy2(backup, CADDY)
                    run_caddy("reload", "--config", str(CADDY), "--adapter", "caddyfile")
                    print("Original Caddy route restored.")
                else:
                    print("WARNING: Caddyfile changed during session; manual review required.",
                          file=sys.stderr)
            except Exception as exc:
                print(f"WARNING: Could not restore Caddy: {exc}", file=sys.stderr)
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"make mcp: {exc}", file=sys.stderr)
        raise SystemExit(1)
