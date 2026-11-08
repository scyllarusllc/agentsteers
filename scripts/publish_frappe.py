#!/usr/bin/env python3
"""Publish AgentSteers Frappe website to a preconfigured, dedicated production Bench.

This is intentionally NOT a production installer, DNS/proxy editor, or MCP deployer.
"""
from __future__ import annotations

import os
import json
import datetime
import re
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error

from yarn_environment import ensure_yarn
from mariadb_environment import ensure_mariadb
from frappe_database_auth import repair_missing_site_account, _root_sql, _literal

ROOT = Path(__file__).resolve().parent.parent
APP_SRC = ROOT / "frappe_app"
APP = "agentsteers_frappe"
DOMAIN = "agentsteers.com"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def diagnose_site_database_config(bench: Path, site: str) -> None:
    """Read-only database connection metadata; never print credentials."""
    path = bench / "sites" / site / "site_config.json"
    try:
        import json
        config = json.loads(path.read_text(encoding="utf-8"))
        db_name = config.get("db_name")
        db_user = config.get("db_user") or db_name
        db_host = config.get("db_host") or "localhost"
        print("Frappe site database configuration (password hidden):", file=sys.stderr)
        print(f"  db_name: {db_name or '(missing)'}", file=sys.stderr)
        print(f"  db_user: {db_user or '(missing)'}" +
              (" (defaults to db_name)" if not config.get("db_user") else ""),
              file=sys.stderr)
        print(f"  db_host: {db_host}", file=sys.stderr)
        print(f"  db_password: {'configured' if config.get('db_password') else 'missing'}",
              file=sys.stderr, flush=True)
    except (OSError, ValueError, TypeError) as exc:
        print(f"Could not inspect site database configuration: {type(exc).__name__}",
              file=sys.stderr, flush=True)


def diagnose_mariadb_root_access() -> None:
    """Read-only MariaDB administrator diagnostic after authentication failure."""
    if not shutil.which("sudo") or not shutil.which("mariadb"):
        print("Skipping MariaDB root diagnostic: sudo or mariadb client unavailable.",
              file=sys.stderr, flush=True)
        return
    print("Checking local MariaDB administrator access without prompting for a password...",
          file=sys.stderr, flush=True)
    result = subprocess.run(
        ["sudo", "-n", "mariadb", "-e", "SELECT CURRENT_USER(), VERSION();"],
        text=True, capture_output=True, check=False,
    )
    if result.returncode == 0:
        print("MariaDB administrator connection succeeded; Frappe credentials still "
              "require separate verification.", file=sys.stderr, flush=True)
    else:
        print('MariaDB admin diagnostic unavailable or failed. Manually run: '
              'sudo mariadb -e "SELECT CURRENT_USER(), VERSION();" ',
              file=sys.stderr, flush=True)


def diagnose_database_accounts() -> None:
    """Optional read-only MariaDB account list after Frappe error 1045."""
    if not sys.stdin.isatty() or not shutil.which("su"):
        print("Account check requires an interactive root session (su).",
              file=sys.stderr, flush=True)
        return
    print("MariaDB account inspection is available. It will run 'SELECT User, Host "
          "FROM mysql.user' under root, without changing database users.",
          file=sys.stderr, flush=True)
    answer = input("Type CHECK DB USERS to inspect database accounts, or press Enter to skip: ").strip()
    if answer != "CHECK DB USERS":
        print("Skipped MariaDB account inspection.", file=sys.stderr, flush=True)
        return
    # su asks for the root password through the terminal. Never read or store it.
    # Fixed command: no shell input from the site configuration or error message.
    query = "mariadb --batch -e 'SELECT User, Host FROM mysql.user;'"
    result = subprocess.run(["su", "-c", query], check=False)
    if result.returncode:
        print("Could not inspect MariaDB accounts. Root password login may be "
              "disabled or the MariaDB administrator account may require different "
              "authentication.", file=sys.stderr, flush=True)
    else:
        print("MariaDB account list completed. This does not verify the Frappe "
              "password or grants.", file=sys.stderr, flush=True)


def run(args: list[str], *, cwd: Path, capture: bool = False) -> str:
    print("+ " + " ".join(args), flush=True)
    if capture:
        result = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
        if result.returncode:
            # Show the real Frappe traceback without hiding it behind exit status 1.
            details = (result.stderr or result.stdout or "").strip()
            if re.search(r"Access denied for user .*using password:", details, re.I):
                print("MariaDB rejected the Frappe site's database credentials (error 1045).", file=sys.stderr, flush=True)
                diagnose_mariadb_root_access()
                print("Frappe reads the database username from its site configuration; "
                      "you do NOT need to type or share it.", file=sys.stderr, flush=True)
                print("This can mean a missing database account, mismatched password, "
                      "or incorrect user@host grants. The existing site configuration "
                      "and credentials have NOT been changed.", file=sys.stderr, flush=True)
                print("A database administrator must reconcile the account and site configuration "
                      "before publishing; do not reset the MariaDB root password or delete the site.",
                      file=sys.stderr, flush=True)
            elif details:
                print(details, file=sys.stderr, flush=True)
            marker = " [MariaDB authentication 1045]" if re.search(
                r"Access denied for user .*using password:", details, re.I
            ) else ""
            raise RuntimeError(
                f"Bench command failed (exit {result.returncode}): "
                + " ".join(args)
                + marker + ". See Frappe error output above."
            )
        return result.stdout
    subprocess.run(args, cwd=cwd, text=True, check=True)
    return ""


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


def _looks_like_bench(candidate: Path, site: str) -> bool:
    return ((candidate / "apps" / "frappe").is_dir()
            and (candidate / "sites" / site / "site_config.json").is_file()
            and (candidate / "env" / "bin" / "python").is_file())


def resolve_bench(site: str) -> Path:
    """Auto-discover a nearby dedicated Bench; never guess among alternatives."""
    configured = os.environ.get("AGENTSTEERS_PROD_BENCH_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve(strict=True)
    # Project-managed Bench is the default. Its generated contents stay out of Git.
    managed = ROOT / "frappe-bench"
    if _looks_like_bench(managed, site):
        print(f"Using project-managed Frappe Bench: {managed}", flush=True)
        return managed.resolve()
    cwd = Path.cwd().resolve()
    if _looks_like_bench(cwd, site):
        return cwd

    # Search only local, conventional locations; no system-wide recursive scan.
    roots = (ROOT.parent, Path.home())
    names = ("frappe-bench", "agentsteers-bench", "bench", "frappe")
    candidates: set[Path] = set()
    for root in roots:
        for name in names:
            candidate = root / name
            if _looks_like_bench(candidate, site):
                candidates.add(candidate.resolve())
        # Also find a custom-named Bench directly beside the Git checkout.
        if root == ROOT.parent:
            for candidate in root.iterdir():
                if candidate.is_dir() and not candidate.is_symlink() and _looks_like_bench(candidate, site):
                    candidates.add(candidate.resolve())
    if len(candidates) == 1:
        selected = next(iter(candidates))
        print(f"Automatically detected Frappe Bench: {selected}", flush=True)
        return selected
    if not candidates:
        raise RuntimeError(
            "Could not auto-detect an existing Frappe Bench for " + site
            + ". Initialise the project-managed frappe-bench/ using the installation guide, "
            "or set AGENTSTEERS_PROD_BENCH_DIR to an existing dedicated Bench."
        )
    raise RuntimeError(
        "Multiple Frappe Benches detected; choose explicitly with "
        "AGENTSTEERS_PROD_BENCH_DIR: " + ", ".join(str(p) for p in sorted(candidates))
    )


def ensure_apps_manifest(bench: Path, *, check_only: bool = False) -> None:
    """Repair only the app manifest of an otherwise validated, dedicated Bench."""
    manifest = bench / "sites" / "apps.txt"
    require(not manifest.is_symlink(), "Refusing symlinked sites/apps.txt.")
    require(not manifest.exists() or manifest.is_file(),
            "sites/apps.txt is not a regular file.")
    names = ["frappe"]
    if (bench / "apps" / APP).is_dir():
        names.append(APP)
    if not manifest.exists():
        require(not check_only,
                "Missing sites/apps.txt; run make publish to repair it.")
        manifest.write_text("\n".join(names) + "\n")
        print("Created missing Frappe sites/apps.txt.", flush=True)
        return
    original = manifest.read_text()
    present = original.splitlines()
    missing = [name for name in names if name not in present]
    if missing:
        require(not check_only,
                "Missing entries in sites/apps.txt; run make publish to repair them.")
        with manifest.open("a") as stream:
            if original and not original.endswith("\n"):
                stream.write("\n")
            stream.write("\n".join(missing) + "\n")
        print("Added missing Frappe app entries: " + ", ".join(missing), flush=True)


def offer_fresh_site_recovery(bench: Path, site: str, bench_cli: str) -> bool:
    """Explicitly rebuild a verified missing-database site, preserving old files."""
    if not sys.stdin.isatty() or bench != (ROOT / "frappe-bench").resolve():
        return False
    site_dir = bench / "sites" / site
    config_path = site_dir / "site_config.json"
    if site_dir.is_symlink() or config_path.is_symlink():
        raise RuntimeError("Symlinked site configuration; recovery refused.")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    db_name = config.get("db_name")
    if not isinstance(db_name, str) or not re.fullmatch(r"[A-Za-z0-9_]+", db_name):
        raise RuntimeError("Invalid configured database name; recovery refused.")
    print("Checking whether the configured site database is actually missing. "
          "Linux root authentication may be requested.", flush=True)
    result = _root_sql(
        "SELECT COUNT(*) FROM information_schema.SCHEMATA "
        f"WHERE SCHEMA_NAME={_literal(db_name)};\n", read_only=True
    ).strip()
    if result not in ("0", "1"):
        raise RuntimeError("Database existence query returned an unexpected result; recovery refused.")
    if result == "1":
        print("Recovery refused: configured database exists; no initialization attempted.",
              flush=True)
        return False
    print("The configured database is absent. This may be an incomplete first-time "
          "installation. Existing site files will be preserved in a separate directory.",
          flush=True)
    answer = input("Type REINITIALIZE EMPTY SITE to create a fresh Frappe site: ").strip()
    if answer != "REINITIALIZE EMPTY SITE":
        print("Fresh-site initialization skipped.", flush=True)
        return False
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = bench / "sites" / (".agentsteers-incomplete-" + stamp)
    if archive.exists():
        raise RuntimeError("Recovery archive already exists; refusing to overwrite.")
    site_dir.rename(archive)
    print(f"Preserved previous site directory at {archive}", flush=True)
    try:
        # Bench securely prompts for database administrator and Frappe
        # Administrator passwords; never supply secrets on the command line.
        run([bench_cli, "new-site", site], cwd=bench)
    except BaseException:
        if not site_dir.exists():
            archive.rename(site_dir)
            print("Restored original site directory after failed initialization.",
                  file=sys.stderr, flush=True)
        else:
            print("Initialization failed and created partial files. Preserved both "
                  "directories for manual inspection; no automatic deletion.",
                  file=sys.stderr, flush=True)
        raise
    print("Fresh Frappe site initialized; previous site files remain archived.",
          flush=True)
    return True


def main() -> int:
    # Use the standard-library venv/pip path by default throughout publish.
    os.environ.setdefault("BENCH_DISABLE_UV", "1")
    site = os.environ.get("AGENTSTEERS_PROD_SITE", DOMAIN).strip()
    require(site == DOMAIN, "Only dedicated production site agentsteers.com is supported.")
    require(os.geteuid() != 0, "Run as the dedicated Bench owner, not root.")
    commit = verify_git_release()
    if "--check" not in sys.argv:
        ensure_yarn()
    try:
        bench = resolve_bench(site)
    except RuntimeError as exc:
        # New, single-purpose AgentSteers installation: initialise the managed
        # Bench on the first publish only. Never use auto-setup for ambiguous
        # existing Benches, explicit paths, or the read-only preflight mode.
        if ("Could not auto-detect an existing Frappe Bench" not in str(exc)
                or "--check" in sys.argv):
            raise
        print("No existing Frappe Bench found. Running first-time make setup automatically...", flush=True)
        run([sys.executable, str(ROOT / "scripts" / "setup_managed_bench.py")], cwd=ROOT)
        bench = resolve_bench(site)
    print(f"Production Bench candidate: {bench}", flush=True)
    require(bench != ROOT and (ROOT not in bench.parents or bench == ROOT / "frappe-bench"),
            "Only the project-managed frappe-bench/ subdirectory may serve as a Bench inside the repository.")
    require((bench / "apps" / "frappe").is_dir()
            and (bench / "sites" / site / "site_config.json").is_file()
            and (bench / "env" / "bin" / "python").is_file(),
            "Existing Frappe production Bench/site is required; refusing to create it.")
    require((bench / "sites" / "common_site_config.json").is_file(),
            "Bench configuration missing.")
    # Avoid restarts / schema changes to other applications in a shared Bench.
    sites_dir = bench / "sites"
    archived_site_pattern = re.compile(r"^\.agentsteers-incomplete-\d{8}T\d{6}Z$")
    sites = []
    archived_sites = []
    for p in sites_dir.iterdir():
        if not p.is_dir() or not (p / "site_config.json").is_file():
            continue
        if (bench == ROOT / "frappe-bench"
                and not p.is_symlink()
                and archived_site_pattern.fullmatch(p.name)):
            archived_sites.append(p.name)
            continue
        sites.append(p.name)
    if archived_sites:
        print("Preserved incomplete-site archives (not active sites): "
              + ", ".join(sorted(archived_sites)), flush=True)
    if sites != [DOMAIN]:
        sites_dir = bench / "sites"
        print("Single-site Bench diagnostic (read-only):", flush=True)
        print(f"Directory: {sites_dir}", flush=True)
        print("Equivalent command: ls -la frappe-bench/sites/ "
              "(for the project-managed Bench)", flush=True)
        for entry in sorted(sites_dir.iterdir(), key=lambda p: p.name):
            try:
                stat = entry.lstat()
                kind = ("symlink" if entry.is_symlink() else
                        "directory" if entry.is_dir() else "file")
                print(f"  {entry.name} [{kind}, mode={stat.st_mode & 0o777:03o}]",
                      flush=True)
            except OSError as exc:
                print(f"  {entry.name} [unable to inspect: {exc}]", flush=True)
        print(f"Detected configured site directories: {sorted(sites)!r}", flush=True)
        raise RuntimeError(
            "Publish requires a dedicated single-site Bench, not a shared Bench. "
            "Directory inspection above is read-only; no files were changed."
        )
    require(os.access(bench, os.W_OK), "Production Bench is not writable by current user.")

    link = bench / "apps" / APP
    require(not link.exists() or link.resolve() == APP_SRC.resolve(),
            "Conflicting app directory; refusing to replace existing installation.")
    # A first-time publish may have installed Bench CLI in the repository's
    # isolated virtual environment; keep using it after setup completes.
    bench_candidates = (
        bench / "env" / "bin" / "bench",
        ROOT / ".bench-cli-venv" / "bin" / "bench",
    )
    bench_cli = next((str(p) for p in bench_candidates if p.is_file()), None)
    if not bench_cli:
        bench_cli = shutil.which("bench")
    require(bool(bench_cli), "Bench CLI not found.")

    ensure_apps_manifest(bench, check_only="--check" in sys.argv)

    ensure_mariadb(bench, site, check_only="--check" in sys.argv)

    diagnose_site_database_config(bench, site)

    # Verify site and database are accessible BEFORE normal deployment changes.
    # Only after error 1045, allow explicit creation of a *missing* local
    # account. Never change a pre-existing account or password.
    list_args = [bench_cli, "--site", site, "list-apps"]
    try:
        run(list_args, cwd=bench, capture=True)
    except RuntimeError as exc:
        if "--check" in sys.argv and "[MariaDB authentication 1045]" in str(exc):
            if sys.stdin.isatty():
                print("Optional read-only account inspection requires Linux root "
                      "authentication via su. No database changes will be made.", flush=True)
                answer = input("Type INSPECT DB ACCOUNT to proceed, or Enter to skip: ").strip()
                if answer == "INSPECT DB ACCOUNT":
                    try:
                        repair_missing_site_account(bench, site, inspect_only=True)
                    except RuntimeError as diagnostic_error:
                        print(f"Read-only account inspection unavailable: {diagnostic_error}",
                              file=sys.stderr, flush=True)
            raise
        if "--check" in sys.argv or "[MariaDB authentication 1045]" not in str(exc):
            raise
        try:
            repaired = repair_missing_site_account(bench, site)
        except RuntimeError as diagnostic_error:
            if "site database does not exist" not in str(diagnostic_error):
                raise
            print("The configured Frappe database is missing.", flush=True)
            repaired = offer_fresh_site_recovery(bench, site, bench_cli)
        if not repaired:
            raise
        run(list_args, cwd=bench, capture=True)

    if "--check" in sys.argv:
        print(f"Publish preflight passed for {DOMAIN} at {commit}. No backups, migrations, or restarts executed.", flush=True)
        return 0

    confirm_release(commit)
    print("Production target validated. Taking site backup before any changes...", flush=True)
    run([bench_cli, "--site", site, "backup", "--with-files"], cwd=bench)

    if not link.exists():
        link.symlink_to(APP_SRC, target_is_directory=True)
    ensure_apps_manifest(bench)

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
