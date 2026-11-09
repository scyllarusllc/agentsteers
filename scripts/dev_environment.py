#!/usr/bin/env python3
"""Isolated local development Bench bootstrap and guarded production-data refresh.

Never writes to production Bench or database. Requires an existing dev site for sync.
Production data is sensitive: local-only, restricted to the Bench owner.
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from install_frappe_dev import APP_SRC, APP_NAME, ROOT
from publish_frappe import resolve_bench, ensure_apps_manifest
from yarn_environment import ensure_yarn
from bench_redis import ensure_bench_redis

PROD_SITE = "agentsteers.com"
DEV_SITE = "agentsteers-dev.localhost"
DEV_BENCH = ROOT / "frappe-dev-bench"
PROD_BENCH = (ROOT / "frappe-bench").resolve()



def diagnose_permissions() -> None:
    """Read-only, sanitized diagnostics for common noexec / permission failures."""
    print("Development execution diagnostics (read-only):", file=sys.stderr, flush=True)
    print(f"  cwd: {Path.cwd()}", file=sys.stderr)
    print(f"  uid: {os.geteuid()}", file=sys.stderr)
    candidates = (
        ROOT / ".bench-cli-venv/bin/bench",
        PROD_BENCH / "env/bin/bench",
        DEV_BENCH / "env/bin/bench",
    )
    system = shutil.which("bench")
    if system:
        candidates += (Path(system),)
    for path in candidates:
        try:
            info = path.stat()
            mode = stat.S_IMODE(info.st_mode)
            print(f"  {path}: mode={mode:04o}, owner_uid={info.st_uid}, "
                  f"executable={os.access(path, os.X_OK)}", file=sys.stderr)
        except OSError as exc:
            print(f"  {path}: {type(exc).__name__}", file=sys.stderr)
    findmnt = shutil.which("findmnt")
    if findmnt:
        try:
            for path in (ROOT, DEV_BENCH):
                result = subprocess.run(
                    [findmnt, "-n", "-T", str(path), "-o", "TARGET,OPTIONS"],
                    capture_output=True, text=True, timeout=5, check=False)
                if result.returncode == 0:
                    # Mount options do not include passwords or project credentials.
                    print(f"  mount for {path}: {result.stdout.strip()}", file=sys.stderr)
        except (OSError, subprocess.TimeoutExpired):
            print("  mount diagnostics unavailable", file=sys.stderr)
    print("  Do not sudo, chmod -R, delete Bench directories, or change production permissions.",
          file=sys.stderr, flush=True)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def config(bench: Path, site: str) -> dict:
    path = bench / "sites" / site / "site_config.json"
    check(path.is_file() and not path.is_symlink(), f"Missing regular site config: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate() -> tuple[Path, dict, dict]:
    check(os.geteuid() != 0, "Run as the non-root Bench owner.")
    check(not DEV_BENCH.is_symlink(), "Refusing symlinked development Bench.")
    check(DEV_BENCH.is_dir(), "Run make dev-setup first.")
    prod = resolve_bench(PROD_SITE).resolve()
    check(prod != DEV_BENCH and DEV_BENCH != PROD_BENCH, "Production and development Bench must differ.")
    check((DEV_BENCH / "apps" / "frappe").is_dir(), "Development Bench is incomplete.")
    check((DEV_BENCH / "sites" / DEV_SITE).is_dir(), "Development site missing; run make dev-setup.")
    check(not (DEV_BENCH / "sites" / DEV_SITE).is_symlink(), "Refusing symlinked dev site.")
    dev_sites = [p.name for p in (DEV_BENCH / "sites").iterdir()
                 if p.is_dir() and (p / "site_config.json").exists()]
    check(dev_sites == [DEV_SITE], "Development Bench must contain only the dedicated development site.")
    p, d = config(prod, PROD_SITE), config(DEV_BENCH, DEV_SITE)
    for key in ("db_name", "db_password"):
        check(p.get(key) and d.get(key), f"Both sites need {key}.")
    check(p["db_name"] != d["db_name"], "Refusing same production/development database.")
    check((p.get("db_user") or p["db_name"]) != (d.get("db_user") or d["db_name"]),
          "Refusing shared production/development database user.")
    for cfg in (p, d):
        check(cfg.get("db_host", "localhost") in ("localhost", "127.0.0.1", ""),
              "Only local MariaDB is supported.")
        check(not cfg.get("db_port") or str(cfg["db_port"]) == "3306",
              "Nondefault MariaDB port requires manual review.")
    check(d.get("host_name", "").startswith("http://127.0.0.1:") or
          d.get("host_name", "").startswith("http://localhost:") or
          not d.get("host_name"), "Development host_name must be loopback-only.")
    return prod, p, d


def run(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True)


def bench_cli(bench: Path) -> str:
    # Match publish's managed Bench CLI discovery order; reject unusable
    # executables rather than trying to chmod system or production files.
    for path in (ROOT / ".bench-cli-venv/bin/bench", bench / "env/bin/bench"):
        if path.is_file():
            check(os.access(path, os.X_OK),
                  f"Bench CLI exists but is not executable: {path}")
            return str(path)
    found = shutil.which("bench")
    check(bool(found), "Bench CLI unavailable.")
    check(os.access(found, os.X_OK), f"Bench CLI not executable: {found}")
    return str(found)


def isolate_site() -> None:
    cli = bench_cli(DEV_BENCH)
    # Settings must be applied before starting any development web or worker process.
    for key, value in (("disable_scheduler", "1"), ("mute_emails", "1"),
                       ("developer_mode", "1"), ("host_name", "http://127.0.0.1:8001")):
        run([cli, "--site", DEV_SITE, "set-config", key, value], DEV_BENCH)
    # Do not allow this dev site to inherit OAuth/social login credentials from production.
    # Existing encrypted integrations and personal data still require operator care.


def setup() -> None:
    # Match make publish: use stdlib venv + pip, not uv (may be noexec).
    os.environ["BENCH_DISABLE_UV"] = "1"
    check(os.geteuid() != 0, "Do not initialize Bench as root.")
    check(sys.stdin.isatty(), "Interactive terminal required for initial setup.")
    check(not DEV_BENCH.is_symlink(), "Refusing symlinked dev Bench.")
    prod = resolve_bench(PROD_SITE).resolve()
    check(DEV_BENCH != prod and DEV_BENCH != PROD_BENCH, "Refusing production Bench.")
    existing = DEV_BENCH.exists()
    if existing:
        check(DEV_BENCH.is_dir() and (DEV_BENCH / "apps/frappe").is_dir()
              and (DEV_BENCH / "env/bin/python").is_file()
              and (DEV_BENCH / "sites/common_site_config.json").is_file(),
              "Existing development Bench is incomplete; refusing to overwrite it.")
        sites = [p for p in (DEV_BENCH / "sites").iterdir()
                 if p.is_dir() and (p / "site_config.json").exists()]
        check(not sites, "Existing configured sites must be validated, never recreated.")
        check(not (DEV_BENCH / "sites" / DEV_SITE).exists(),
              "Partial development site exists; preserve it and inspect before retrying.")
    # Match make publish: validate working Yarn Classic (and prepend project-local
    # executable to PATH if necessary) before Bench creates any dev directories.
    ensure_yarn()
    cli = bench_cli(prod)
    branch = os.environ.get("AGENTSTEERS_FRAPPE_BRANCH", "version-15")
    check(branch.startswith("version-") and branch[8:].isdigit(), "Invalid Frappe branch.")
    print("Creating separate development Bench. Frappe will ask for new database credentials.", flush=True)
    if not existing:
        run([cli, "init", "--frappe-branch", branch, "--python", "python3.11", str(DEV_BENCH)], ROOT)
    dev_cli = bench_cli(DEV_BENCH)
    ensure_bench_redis(DEV_BENCH, start=True)
    from create_dev_site import create_dev_site
    create_dev_site(DEV_BENCH, ROOT, config(prod, PROD_SITE))
    validate()
    prepare_dev_app()
    print("Development site initialized with a fresh database. Production data sync is disabled.", flush=True)


def prepare_dev_app() -> None:
    """Resume app registration/installation without recreating a development site."""
    validate()
    cli = bench_cli(DEV_BENCH)
    link = DEV_BENCH / "apps" / APP_NAME
    check(not (link.exists() or link.is_symlink()) or link.resolve() == APP_SRC.resolve(),
          "Conflicting development app path; refusing overwrite.")
    if not link.exists():
        link.symlink_to(APP_SRC, target_is_directory=True)
    # Frappe checks this registry before install-app, independently of pip.
    ensure_apps_manifest(DEV_BENCH)
    ensure_bench_redis(DEV_BENCH, start=True)
    isolate_site()
    result = subprocess.run([cli, "--site", DEV_SITE, "list-apps"], cwd=DEV_BENCH,
                            text=True, capture_output=True, check=True)
    installed = {line.split()[0] for line in result.stdout.splitlines() if line.strip()}
    newly_installed = APP_NAME not in installed
    if newly_installed:
        run([str(DEV_BENCH / "env/bin/python"), "-m", "pip", "install", "-e", str(APP_SRC)], DEV_BENCH)
        run([cli, "--site", DEV_SITE, "install-app", APP_NAME], DEV_BENCH)
    manifest = DEV_BENCH / "sites/assets/assets.json"
    assets = json.loads(manifest.read_text()) if manifest.is_file() else {}
    if newly_installed or not all(name in assets for name in
                                 ("website.bundle.css", "login.bundle.css", "frappe-web.bundle.js")):
        ensure_yarn()
        run([cli, "build", "--apps", "frappe," + APP_NAME], DEV_BENCH)


def ensure() -> None:
    """Create a fresh dev Bench only when absent; never repair or overwrite one."""
    # Apply before any child Bench command, including first-time init.
    os.environ["BENCH_DISABLE_UV"] = "1"
    check(os.geteuid() != 0, "Run as the non-root Bench owner.")
    check(not DEV_BENCH.is_symlink(), "Refusing symlinked development Bench.")
    if not DEV_BENCH.exists():
        print("Isolated development Bench missing; starting one-time setup.", flush=True)
        setup()
    else:
        check(DEV_BENCH.is_dir(),
              "Existing development Bench path is not a directory; refusing to modify it.")
        if not (DEV_BENCH / "sites" / DEV_SITE).exists():
            print("Development Bench exists without a site; resuming isolated setup.", flush=True)
            setup()
        else:
            print("Using existing isolated development Bench.", flush=True)
    # Fail closed for incomplete or cross-wired development sites.
    validate()
    prepare_dev_app()
    print("Isolated development Bench verified. Starting loopback server.", flush=True)


def sync() -> None:
    """Fail closed: production records/credentials must never be cloned into dev."""
    raise RuntimeError("Production database sync is disabled. Use a fresh isolated development site and synthetic test data.")


if __name__ == "__main__":
    try:
        command = sys.argv[1] if len(sys.argv) == 2 else ""
        if command == "setup":
            setup()
        elif command == "sync":
            sync()
        elif command == "ensure":
            ensure()
        else:
            raise RuntimeError("Usage: dev_environment.py [setup|sync|ensure]")
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f"Development environment: {exc}", file=sys.stderr)
        diagnose_permissions()
        raise SystemExit(1)
