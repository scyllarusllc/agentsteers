#!/usr/bin/env python3
"""Publish AgentSteers Frappe website to a preconfigured, dedicated production Bench.

This is intentionally NOT a production installer, DNS/proxy editor, or MCP deployer.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parent.parent
APP_SRC = ROOT / "frappe_app"
APP = "agentsteers_frappe"
DOMAIN = "agentsteers.com"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def run(args: list[str], *, cwd: Path, capture: bool = False) -> str:
    print("+ " + " ".join(args), flush=True)
    result = subprocess.run(args, cwd=cwd, text=True, check=True,
                            capture_output=capture)
    return result.stdout if capture else ""


def verify_git_release() -> str:
    """Require a clean, exact upstream main checkout; never reset or pull."""
    def output(*cmd: str) -> str:
        return subprocess.run(cmd, cwd=ROOT, check=True, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.strip()

    require(output("git", "rev-parse", "--show-toplevel") == str(ROOT.resolve()),
            "Run from the AgentSteers repository checkout.")
    require(output("git", "symbolic-ref", "--quiet", "--short", "HEAD") == "main",
            "Publish is allowed only from the main branch.")
    require(not output("git", "status", "--porcelain", "--untracked-files=normal"),
            "Working tree contains local changes. Commit or stash before publishing.")
    print("Checking remote main without modifying the local working tree...", flush=True)
    remote = output("git", "ls-remote", "--exit-code", "origin", "refs/heads/main").split()[0]
    head = output("git", "rev-parse", "HEAD")
    require(head == remote, "Local main differs from origin/main; run make pull and review before publish.")
    print(f"Verified clean Git main at {head}", flush=True)
    return head


def confirm_release(commit: str) -> None:
    require(sys.stdin.isatty(), "Interactive production confirmation required.")
    print(f"About to publish commit {commit} to {DOMAIN}. "
          "A full site backup is taken first. Database changes may require manual restore.",
          flush=True)
    value = input("Type PUBLISH agentsteers.com to proceed: ").strip()
    require(value == "PUBLISH agentsteers.com", "Publish cancelled: confirmation did not match.")


def health_check(commit: str) -> None:
    """Verify HTTPS actually serves the new Frappe page, not the old static site."""
    expected = {
        "/": b'content="agentsteers-frappe-website"',
        "/privacy": b"AgentSteers Frappe website route",
        "/terms": b"AgentSteers Frappe website route",
        "/assets/agentsteers_frappe/css/styles.css": b"--lime",
    }
    base = "https://agentsteers.com"
    errors: list[str] = []
    for attempt in range(6):
        errors = []
        for path, signature in expected.items():
            try:
                req = urllib.request.Request(base + path, headers={
                    "User-Agent": "AgentSteers-Publish-Healthcheck/1.0",
                    "Cache-Control": "no-cache",
                })
                with urllib.request.urlopen(req, timeout=10) as resp:
                    body = resp.read(1_000_000)
                    if resp.status != 200 or signature not in body:
                        errors.append(f"{path}: wrong response or missing Frappe marker")
            except (OSError, urllib.error.URLError, ValueError) as exc:
                errors.append(f"{path}: {type(exc).__name__}")
        if not errors:
            print(f"HTTPS Frappe website health checks passed for {commit}.", flush=True)
            return
        if attempt < 5:
            time.sleep(3)
    raise RuntimeError("Production site verification failed: " + "; ".join(errors)
                       + ". Site may still be served by static Caddy or a stale cache; "
                       "investigate routing and restore from backup if necessary.")


def main() -> int:
    path = os.environ.get("AGENTSTEERS_PROD_BENCH_DIR", "").strip() or str(Path.cwd())
    site = os.environ.get("AGENTSTEERS_PROD_SITE", DOMAIN).strip()
    require(site == DOMAIN, "Only dedicated production site agentsteers.com is supported.")
    require(os.geteuid() != 0, "Run as the dedicated Bench owner, not root.")
    commit = verify_git_release()
    bench = Path(path).expanduser().resolve(strict=True)
    print(f"Production Bench candidate: {bench}", flush=True)
    require(bench != ROOT and ROOT not in bench.parents,
            "Current directory is the AgentSteers Git checkout, not a production Bench. "
            "Run from a dedicated Frappe Bench directory or set AGENTSTEERS_PROD_BENCH_DIR.")
    require((bench / "apps" / "frappe").is_dir()
            and (bench / "sites" / site / "site_config.json").is_file()
            and (bench / "env" / "bin" / "python").is_file(),
            "Existing Frappe production Bench/site is required; refusing to create it.")
    require((bench / "sites" / "common_site_config.json").is_file(),
            "Bench configuration missing.")
    # Avoid restarts / schema changes to other applications in a shared Bench.
    sites = [
        p.name for p in (bench / "sites").iterdir()
        if p.is_dir() and (p / "site_config.json").is_file()
    ]
    require(sites == [DOMAIN], "Publish requires a dedicated single-site Bench, not a shared Bench.")
    require(os.access(bench, os.W_OK), "Production Bench is not writable by current user.")

    link = bench / "apps" / APP
    require(not link.exists() or link.resolve() == APP_SRC.resolve(),
            "Conflicting app directory; refusing to replace existing installation.")
    bench_cli = str(bench / "env" / "bin" / "bench")
    if not Path(bench_cli).is_file():
        bench_cli = shutil.which("bench") or ""
    require(bool(bench_cli), "Bench CLI not found.")

    # Verify site and database are accessible BEFORE attempting changes.
    run([bench_cli, "--site", site, "list-apps"], cwd=bench, capture=True)

    if "--check" in sys.argv:
        print(f"Publish preflight passed for {DOMAIN} at {commit}. No backups, migrations, or restarts executed.", flush=True)
        return 0

    confirm_release(commit)
    print("Production target validated. Taking site backup before any changes...", flush=True)
    run([bench_cli, "--site", site, "backup", "--with-files"], cwd=bench)

    if not link.exists():
        link.symlink_to(APP_SRC, target_is_directory=True)

    python = str(bench / "env" / "bin" / "python")
    run([python, "-m", "pip", "install", "-e", str(link)], cwd=bench)
    apps = run([bench_cli, "--site", site, "list-apps"], cwd=bench, capture=True)
    installed = {row.split()[0] for row in apps.splitlines() if row.strip()}
    if APP not in installed:
        run([bench_cli, "--site", site, "install-app", APP], cwd=bench)
    run([bench_cli, "--site", site, "migrate"], cwd=bench)
    run([bench_cli, "build", "--app", APP], cwd=bench)
    run([bench_cli, "--site", site, "clear-website-cache"], cwd=bench)
    run([bench_cli, "restart"], cwd=bench)
    health_check(commit)
    print("Frappe production site updated and HTTPS routes verified.", flush=True)
    print("No Caddy/DNS changes, MCP publication or Codex execution was performed.", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Publish aborted: {exc}", file=sys.stderr)
        raise SystemExit(1)
