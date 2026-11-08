#!/usr/bin/env python3
"""Initialise an isolated, project-managed Frappe Bench for a brand-new site.

Interactive database and Administrator secrets are handled by Frappe Bench itself.
Never imports existing site data, runs as root, or touches other Benches.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / "frappe-bench"
SOURCE = ROOT / "frappe_app"
SITE = "agentsteers.com"
APP = "agentsteers_frappe"


def abort(message: str) -> None:
    raise RuntimeError(message)


def run(*args: str, cwd: Path = ROOT) -> None:
    print("+ " + " ".join(args), flush=True)
    subprocess.run(args, cwd=cwd, check=True)


def main() -> None:
    if not sys.stdin.isatty():
        abort("Interactive terminal required for safe database and Administrator password prompts.")
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        abort("Use a dedicated non-root Bench owner, not root.")
    python = shutil.which("python3.11")
    if not python:
        abort("Python 3.11 is required for this setup preset.")
    # Use a repository-local virtual environment instead of modifying the
    # system Python or requiring sudo. The environment is ignored by Git.
    # Always prefer the project-local CLI, independent of system PATH.
    managed_cli = ROOT / ".bench-cli-venv" / "bin" / "bench"
    venv_dir = ROOT / ".bench-cli-venv"
    if venv_dir.is_symlink():
        abort("Refusing symlinked local Bench CLI environment.")
    if not managed_cli.is_file():
        if not (venv_dir / "bin" / "python").is_file():
            print("Bootstrapping project-local Frappe Bench CLI environment...", flush=True)
            run(python, "-m", "venv", str(venv_dir))
        print("Installing Bench CLI in project-local environment...", flush=True)
        run(str(venv_dir / "bin" / "python"), "-m", "pip", "install",
            "frappe-bench>=5,<6")
    cli = str(managed_cli)
    if not Path(cli).is_file():
        abort("Bench CLI installation was not successful.")
    if BENCH.is_symlink():
        abort("Refusing symlink for the project-managed Bench.")

    if not BENCH.exists():
        branch = os.environ.get("AGENTSTEERS_FRAPPE_BRANCH", "version-15")
        if not branch.startswith("version-") or not branch[8:].isdigit():
            abort("AGENTSTEERS_FRAPPE_BRANCH must be version-N, e.g. version-15.")
        print(f"Creating a new Bench in {BENCH} (Frappe {branch}).", flush=True)
        run(cli, "init", "--frappe-branch", branch,
            "--python", python, str(BENCH))
    if not ((BENCH / "apps" / "frappe").is_dir()
            and (BENCH / "env" / "bin" / "python").is_file()
            and (BENCH / "sites" / "common_site_config.json").is_file()):
        abort("Existing frappe-bench/ is incomplete; refusing to overwrite or repair it automatically.")

    sites = [p.name for p in (BENCH / "sites").iterdir()
             if p.is_dir() and (p / "site_config.json").is_file()]
    if any(name != SITE for name in sites):
        abort("Project Bench contains another site; refusing to change a shared environment.")

    link = BENCH / "apps" / APP
    if link.is_symlink() and not link.exists():
        abort("Broken app link; repair manually.")
    if link.exists() and link.resolve() != SOURCE.resolve():
        abort("Conflicting AgentSteers app path; refusing to replace it.")
    if not link.exists():
        link.symlink_to(SOURCE, target_is_directory=True)

    run(str(BENCH / "env" / "bin" / "python"), "-m", "pip", "install", "-e", str(SOURCE), cwd=BENCH)

    apps_txt = BENCH / "sites" / "apps.txt"
    if not apps_txt.is_file():
        abort("Missing Frappe sites/apps.txt")
    apps = apps_txt.read_text().splitlines()
    if APP not in apps:
        with apps_txt.open("a") as stream:
            stream.write(APP + "\n")

    if SITE not in sites:
        print(f"Creating {SITE}. Frappe will securely prompt for database and Administrator passwords.", flush=True)
        run(cli, "new-site", SITE, cwd=BENCH)

    listed = subprocess.run([cli, "--site", SITE, "list-apps"], cwd=BENCH,
                            text=True, check=True, capture_output=True).stdout
    installed = {row.split()[0] for row in listed.splitlines() if row.strip()}
    if APP not in installed:
        run(cli, "--site", SITE, "install-app", APP, cwd=BENCH)
    run(cli, "build", "--app", APP, cwd=BENCH)
    print("Project-managed Bench and site initialised.", flush=True)
    print("Development: cd frappe-bench && bench start", flush=True)
    print("Production setup (services, reverse proxy, TLS, DNS) is NOT configured by this command.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f"Setup stopped: {exc}", file=sys.stderr)
        raise SystemExit(1)
