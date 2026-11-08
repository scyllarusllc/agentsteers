#!/usr/bin/env python3
"""Publish AgentSteers Frappe website to a preconfigured, dedicated production Bench.

This is intentionally NOT a production installer, DNS/proxy editor, or MCP deployer.
"""
from __future__ import annotations

import os
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error

from yarn_environment import ensure_yarn
from website_service import restart_website_service
from bench_redis import ensure_bench_redis
from initialize_fresh_site import initialize_fresh_site
from mariadb_environment import ensure_mariadb

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


def run(args: list[str], *, cwd: Path, capture: bool = False) -> str:
    print("+ " + " ".join(args), flush=True)
    if capture:
        result = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
        if result.returncode:
            # Show the real Frappe traceback without hiding it behind exit status 1.
            details = (result.stderr or result.stdout or "").strip()
            if re.search(r"Access denied for user", details, re.I):
                print("MariaDB authentication failed (1045/1698).", file=sys.stderr, flush=True)
                print("Frappe reads the database username from its site configuration; "
                      "you do NOT need to type or share it.", file=sys.stderr, flush=True)
                print("This can mean a missing database account, mismatched password, "
                      "or incorrect user@host grants. The existing site configuration "
                      "and credentials have NOT been changed.", file=sys.stderr, flush=True)
                print("A database administrator must reconcile the account and site configuration "
                      "before publishing; do not reset the MariaDB root password or delete the site. "
                      "For error 1698, verify whether the administrator account requires Unix socket "
                      "authentication as Linux root. Fresh initialization is offered only after verifying that both database and account are absent.",
                      file=sys.stderr, flush=True)
            elif details:
                print(details, file=sys.stderr, flush=True)
            marker = " [MariaDB authentication failed]" if re.search(
                r"Access denied for user", details, re.I
            ) else ""
            raise RuntimeError(
                f"Bench command failed (exit {result.returncode}): "
                + " ".join(args)
                + marker + ". See Frappe error output above."
            )
        return result.stdout
    subprocess.run(args, cwd=cwd, text=True, check=True)
    return ""


def git_output(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True)
    require(result.returncode == 0,
            "Git command failed: git " + " ".join(args)
            + ". Check repository ownership, origin access and Git credentials. "
            "No automatic reset or stash was attempted.")
    return result.stdout.strip()


def confirm_git_action(prompt: str, expected: str) -> None:
    require(sys.stdin.isatty(), prompt + " Run make publish in an interactive terminal.")
    require(input(prompt + " Type " + expected + " to continue: ").strip() == expected,
            "Git action cancelled; local work preserved.")


def verify_git_release() -> str:
    """Synchronize a reviewed main release only with explicit consent."""
    require(git_output("rev-parse", "--show-toplevel") == str(ROOT.resolve()),
            "Run from the AgentSteers repository checkout.")
    require(git_output("symbolic-ref", "--quiet", "--short", "HEAD") == "main",
            "Publish is allowed only from main; switch branches explicitly.")
    status = git_output("status", "--porcelain", "--untracked-files=normal")
    if status:
        require("--check" not in sys.argv, "Working tree contains local changes; read-only check stopped.")
        print("Local changes to review before publishing:\n" + status, flush=True)
        print(git_output("diff", "--stat"), flush=True)
        print("This will stage tracked changes and untracked non-ignored files. "
              "Review their contents and exclude secrets before agreeing.", flush=True)
        confirm_git_action("Commit and push these reviewed changes?", "COMMIT AND PUSH")
        message = input("Commit message: ").strip()
        require(bool(message), "Commit message required; no files staged.")
        require(git_output("status", "--porcelain", "--untracked-files=normal") == status,
                "File list changed during review; rerun make publish before staging.")
        git_output("add", "--all")
        git_output("commit", "-m", message)

    # Fetch only updates Git metadata, never the checked-out files.
    if "--check" in sys.argv:
        remote = git_output("ls-remote", "--exit-code", "origin", "refs/heads/main").split()[0]
        require(git_output("rev-parse", "HEAD") == remote, "Local main differs from origin/main.")
        return remote
    git_output("fetch", "origin", "main")
    head = git_output("rev-parse", "HEAD")
    remote = git_output("rev-parse", "FETCH_HEAD")
    if head != remote:
        behind, ahead = map(int, git_output(
            "rev-list", "--left-right", "--count", "FETCH_HEAD...HEAD").split())
        require(not (behind and ahead),
                "Local main and origin/main have diverged. Resolve the merge/rebase "
                "explicitly, then rerun make publish. Local commits preserved.")
        if behind:
            confirm_git_action(f"Local main is behind by {behind} commit(s). Fast-forward?", "UPDATE MAIN")
            git_output("merge", "--ff-only", remote)
            raise RuntimeError("Main updated safely. Review the incoming changes and rerun "
                               "make publish so the updated deployment script is loaded.")
        confirm_git_action(f"Push {ahead} local commit(s) to origin/main?", "PUSH MAIN")
        git_output("push", "origin", "HEAD:refs/heads/main")
    remote = git_output("ls-remote", "--exit-code", "origin", "refs/heads/main").split()[0]
    require(git_output("rev-parse", "HEAD") == remote,
            "Remote main changed during preparation; rerun make publish after review.")
    require(not git_output("status", "--porcelain", "--untracked-files=normal"),
            "Working tree changed during preparation; publication stopped.")
    print(f"Verified clean Git main at {remote}", flush=True)
    return remote


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
                req = urllib.request.Request(base + path + "?agentsteers-health=" + str(time.time_ns()), headers={
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
                "Missing sites/apps.txt; repair the Bench manifest before publishing.")
        manifest.write_text("\n".join(names) + "\n")
        print("Created missing Frappe sites/apps.txt.", flush=True)
        return
    original = manifest.read_text()
    present = original.splitlines()
    missing = [name for name in names if name not in present]
    if missing:
        require(not check_only,
                "Missing entries in sites/apps.txt; repair the Bench manifest before publishing.")
        with manifest.open("a") as stream:
            if original and not original.endswith("\n"):
                stream.write("\n")
            stream.write("\n".join(missing) + "\n")
        print("Added missing Frappe app entries: " + ", ".join(missing), flush=True)


def main() -> int:
    # Use the standard-library venv/pip path by default throughout publish.
    os.environ.setdefault("BENCH_DISABLE_UV", "1")
    site = os.environ.get("AGENTSTEERS_PROD_SITE", DOMAIN).strip()
    require(site == DOMAIN, "Only dedicated production site agentsteers.com is supported.")
    require(os.geteuid() != 0, "Run as the dedicated Bench owner, not root.")
    commit = verify_git_release()
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
    archived_site_pattern = re.compile(r"^\.agentsteers-incomplete-\d{8}T\d{6}(?:\d{6})?Z$")
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

    # Preflight never installs packages, starts services, or repairs accounts/sites.
    ensure_apps_manifest(bench, check_only=True)
    ensure_mariadb(bench, site, check_only=True)
    diagnose_site_database_config(bench, site)
    try:
        run([bench_cli, "--site", site, "list-apps"], cwd=bench, capture=True)
    except RuntimeError as exc:
        if "--check" in sys.argv or "[MariaDB authentication failed]" not in str(exc):
            raise
        initialize_fresh_site(bench, ROOT)
        run([bench_cli, "--site", site, "list-apps"], cwd=bench, capture=True)

    if "--check" in sys.argv:
        ensure_bench_redis(bench)
        print(f"Publish preflight passed for {DOMAIN} at {commit}. No backups, migrations, or restarts executed.", flush=True)
        return 0

    confirm_release(commit)
    print("Production target validated. Taking site backup before any changes...", flush=True)
    run([bench_cli, "--site", site, "backup", "--with-files"], cwd=bench)

    ensure_bench_redis(bench, start=True)
    ensure_yarn()
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
    run([bench_cli, "build", "--apps", "frappe," + APP], cwd=bench)
    run([bench_cli, "--site", site, "clear-website-cache"], cwd=bench)
    restart_website_service(bench)
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
