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


def main() -> int:
    path = os.environ.get("AGENTSTEERS_PROD_BENCH_DIR", "").strip()
    site = os.environ.get("AGENTSTEERS_PROD_SITE", "").strip()
    require(bool(path and site), "Set AGENTSTEERS_PROD_BENCH_DIR and AGENTSTEERS_PROD_SITE.")
    require(site == DOMAIN, "Only dedicated production site agentsteers.com is supported.")
    require(os.environ.get("AGENTSTEERS_PUBLISH_CONFIRM") == "PUBLISH agentsteers.com",
            "Set AGENTSTEERS_PUBLISH_CONFIRM='PUBLISH agentsteers.com' to allow production changes.")
    require(os.geteuid() != 0, "Run as the dedicated Bench owner, not root.")
    bench = Path(path).expanduser().resolve(strict=True)
    require(bench != ROOT and ROOT not in bench.parents,
            "The production Bench must be separate from this Git checkout.")
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
    print("Frappe production site updated. Verify live HTTPS routes /, /privacy, /terms.", flush=True)
    print("No Caddy/DNS changes, MCP publication or Codex execution was performed.", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Publish aborted: {exc}", file=sys.stderr)
        raise SystemExit(1)
