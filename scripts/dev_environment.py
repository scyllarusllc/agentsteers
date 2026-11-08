#!/usr/bin/env python3
"""Isolated local development Bench bootstrap and guarded production-data refresh.

Never writes to production Bench or database. Requires an existing dev site for sync.
Production data is sensitive: local-only, restricted to the Bench owner.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from install_frappe_dev import APP_SRC, APP_NAME, ROOT
from publish_frappe import resolve_bench

PROD_SITE = "agentsteers.com"
DEV_SITE = "agentsteers-dev.localhost"
DEV_BENCH = (ROOT / "frappe-dev-bench").resolve()
PROD_BENCH = (ROOT / "frappe-bench").resolve()


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
    for path in (bench / "env/bin/bench", ROOT / ".bench-cli-venv/bin/bench"):
        if path.is_file():
            return str(path)
    found = shutil.which("bench")
    check(bool(found), "Bench CLI unavailable.")
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
    check(os.geteuid() != 0, "Do not initialize Bench as root.")
    check(sys.stdin.isatty(), "Interactive terminal required for initial setup.")
    check(not DEV_BENCH.is_symlink(), "Refusing symlinked dev Bench.")
    prod = resolve_bench(PROD_SITE).resolve()
    check(DEV_BENCH != prod and DEV_BENCH != PROD_BENCH, "Refusing production Bench.")
    check(not DEV_BENCH.exists(), "Development Bench already exists; refusing to replace it.")
    cli = bench_cli(prod)
    branch = os.environ.get("AGENTSTEERS_FRAPPE_BRANCH", "version-15")
    check(branch.startswith("version-") and branch[8:].isdigit(), "Invalid Frappe branch.")
    print("Creating separate development Bench. Frappe will ask for new database credentials.", flush=True)
    run([cli, "init", "--frappe-branch", branch, "--python", "python3.11", str(DEV_BENCH)], ROOT)
    dev_cli = bench_cli(DEV_BENCH)
    run([dev_cli, "new-site", DEV_SITE], DEV_BENCH)
    link = DEV_BENCH / "apps" / APP_NAME
    check(not link.exists() and not link.is_symlink(), "Unexpected app path.")
    link.symlink_to(APP_SRC, target_is_directory=True)
    run([str(DEV_BENCH / "env/bin/python"), "-m", "pip", "install", "-e", str(APP_SRC)], DEV_BENCH)
    run([dev_cli, "--site", DEV_SITE, "install-app", APP_NAME], DEV_BENCH)
    isolate_site()
    print("Development site initialized. Next: make dev-sync or make dev-fast.", flush=True)


def defaults_file(directory: Path, cfg: dict) -> Path:
    # MySQL reads credentials from a restricted file, never from argv or logs.
    path = directory / ("mysql-" + str(len(list(directory.iterdir()))) + ".cnf")
    user = cfg.get("db_user") or cfg["db_name"]
    def esc(v: str) -> str:
        return str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    path.write_text('[client]\nuser="' + esc(user) + '"\npassword="' +
                    esc(cfg["db_password"]) + '"\nhost="127.0.0.1"\n', encoding="utf-8")
    path.chmod(0o600)
    return path


def sync() -> None:
    prod, p, d = validate()
    check(shutil.which("mariadb-dump") or shutil.which("mysqldump"),
          "MariaDB dump utility missing.")
    check(shutil.which("mariadb") or shutil.which("mysql"), "MariaDB client missing.")
    check(os.environ.get("AGENTSTEERS_DEV_DATA_COPY_ACK") == "I_ACCEPT_LOCAL_PRODUCTION_DATA_COPY",
          "Production data includes personal information and integration credentials. "
          "Set AGENTSTEERS_DEV_DATA_COPY_ACK=I_ACCEPT_LOCAL_PRODUCTION_DATA_COPY "
          "only after approving restricted local development data handling.")
    check(not (DEV_BENCH / "sites" / "currentsite.txt").is_symlink(), "Refusing symlinked site selector.")
    # Do not run when Bench dev processes may be using the destination database.
    print("STOP any running development Bench processes before syncing.", flush=True)
    check(sys.stdin.isatty(), "Interactive terminal required to overwrite development data.")
    check(input(f"Type REPLACE {DEV_SITE} to overwrite its database: ").strip() ==
          f"REPLACE {DEV_SITE}", "Development database refresh cancelled.")
    isolate_site()
    dump = shutil.which("mariadb-dump") or shutil.which("mysqldump")
    mysql = shutil.which("mariadb") or shutil.which("mysql")
    with tempfile.TemporaryDirectory(prefix="agentsteers-dev-sync-") as tmp:
        os.chmod(tmp, 0o700)
        directory = Path(tmp)
        pc, dc = defaults_file(directory, p), defaults_file(directory, d)
        backup = directory / "production.sql"
        with backup.open("wb") as out:
            subprocess.run([dump, f"--defaults-extra-file={pc}", "--single-transaction",
                            "--quick", "--skip-lock-tables", "--no-tablespaces",
                            "--skip-triggers", p["db_name"]], stdout=out, check=True)
        # Import into the independently configured dev database only.
        with backup.open("rb") as source:
            subprocess.run([mysql, f"--defaults-extra-file={dc}", d["db_name"]],
                           stdin=source, check=True)
    isolate_site()
    print("Database copy imported into isolated development site.", flush=True)
    print("WARNING: Copied production data may contain personal information and "
          "integration secrets. Do not expose this site or enable background workers.", flush=True)


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2 or sys.argv[1] not in ("setup", "sync"):
            raise RuntimeError("Usage: dev_environment.py setup|sync")
        {"setup": setup, "sync": sync}[sys.argv[1]]()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Development environment stopped: {exc}", file=sys.stderr)
        raise SystemExit(1)
