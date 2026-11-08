#!/usr/bin/env python3
"""Install/update the AgentSteers Frappe app in an explicitly selected dev Bench.

Never creates a site, changes proxy/DNS, or guesses an existing site's name.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
APP_SRC = ROOT / "frappe_app"
APP_NAME = "agentsteers_frappe"


def fail(message: str) -> None:
    raise RuntimeError(message)


def checked(*argv: str, cwd: Path) -> None:
    print("+ " + " ".join(argv), flush=True)
    subprocess.run(argv, cwd=cwd, check=True)


def main() -> int:
    bench_var = os.environ.get("AGENTSTEERS_BENCH_DIR", "").strip()
    site = os.environ.get("AGENTSTEERS_FRAPPE_SITE", "").strip()
    if not bench_var and not site:
        print("No Frappe development Bench configured; skipping Frappe installation.")
        return 0
    if not bench_var or not site:
        fail("Set both AGENTSTEERS_BENCH_DIR and AGENTSTEERS_FRAPPE_SITE.")
    if os.environ.get("AGENTSTEERS_FRAPPE_DEV_CONFIRM") != site:
        fail("Refusing site modification: set AGENTSTEERS_FRAPPE_DEV_CONFIRM to the exact dedicated development site name.")

    bench = Path(bench_var).expanduser().resolve(strict=True)
    if not site or site in {".", "..", "all"} or "/" in site or "\\" in site:
        fail("Invalid site name")
    site_config = bench / "sites" / site / "site_config.json"
    python = bench / "env" / "bin" / "python"
    bench_cli = bench / "env" / "bin" / "bench"
    if not (site_config.is_file() and python.is_file() and (bench / "apps" / "frappe").is_dir()):
        fail("Existing dedicated Frappe Bench/site not found. Refusing to initialize or modify a different site.")
    app_link = bench / "apps" / APP_NAME
    if app_link.is_symlink():
        if app_link.resolve() != APP_SRC.resolve():
            fail("Bench app symlink points elsewhere; refusing to replace it.")
    elif app_link.exists():
        if app_link.resolve() != APP_SRC.resolve():
            fail("Bench app directory already exists; refusing to overwrite it.")
    else:
        app_link.symlink_to(APP_SRC, target_is_directory=True)
        print(f"Linked {app_link} -> {APP_SRC}", flush=True)

    checked(str(python), "-m", "pip", "install", "-e", str(app_link), cwd=bench)
    bench_command = str(bench_cli) if bench_cli.is_file() else "bench"
    listing = subprocess.run([bench_command, "--site", site, "list-apps"], cwd=bench,
                             check=True, text=True, capture_output=True)
    installed = {line.strip().split()[0] for line in listing.stdout.splitlines() if line.strip()}
    if APP_NAME not in installed:
        checked(bench_command, "--site", site, "install-app", APP_NAME, cwd=bench)
    else:
        print(f"{APP_NAME} already installed on {site}; updating assets and schema.", flush=True)
    checked(bench_command, "--site", site, "migrate", cwd=bench)
    checked(bench_command, "build", "--app", APP_NAME, cwd=bench)
    checked(bench_command, "--site", site, "clear-website-cache", cwd=bench)
    print(f"Frappe app installed/updated on dedicated site {site}; deployment not performed.", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Frappe development setup failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
