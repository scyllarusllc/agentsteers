#!/usr/bin/env python3
"""Find and update a *dedicated* local AgentSteers Frappe development site.

Default discovery is the current working directory, then ./frappe-bench.
Never create a Bench/site or modify an ambiguous or production site.
"""
from __future__ import annotations
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

APP_NAME = "agentsteers_frappe"
ROOT = Path(__file__).resolve().parent.parent
APP_SRC = ROOT / "frappe_app"
SITE_PATTERN = re.compile(r"^agentsteers[-_]dev(?:[.-][a-zA-Z0-9.-]+)?$")


def die(message: str) -> None:
    raise RuntimeError(message)


def valid_bench(path: Path) -> bool:
    return ((path / "apps" / "frappe").is_dir()
            and (path / "sites").is_dir()
            and (path / "env" / "bin" / "python").is_file())


def find_bench() -> Path | None:
    configured = os.environ.get("AGENTSTEERS_BENCH_DIR", "").strip()
    if configured:
        bench = Path(configured).expanduser().resolve()
        if not valid_bench(bench):
            die(f"Configured path is not a working Frappe Bench: {bench}")
        return bench
    # Make uses the repository root as working directory; allow a nested Bench.
    for candidate in (Path.cwd(), ROOT, ROOT / "frappe-bench"):
        bench = candidate.resolve()
        if valid_bench(bench):
            return bench
    return None


def select_site(bench: Path) -> str:
    configured = os.environ.get("AGENTSTEERS_FRAPPE_SITE", "").strip()
    if configured:
        if not SITE_PATTERN.fullmatch(configured):
            die("Site must have a dedicated agentsteers-dev name; production sites are refused.")
        if os.environ.get("AGENTSTEERS_FRAPPE_DEV_CONFIRM") != configured:
            die("Set AGENTSTEERS_FRAPPE_DEV_CONFIRM to the exact development site name.")
        name = configured
    else:
        candidates = sorted(
            child.name for child in (bench / "sites").iterdir()
            if child.is_dir() and SITE_PATTERN.fullmatch(child.name)
            and (child / "site_config.json").is_file()
        )
        if len(candidates) != 1:
            die("Expected exactly one agentsteers-dev site in this Bench. "
                "Create a dedicated development site or explicitly configure site and confirmation.")
        name = candidates[0]
    if not (bench / "sites" / name / "site_config.json").is_file():
        die(f"Frappe development site does not exist: {name}")
    return name


def run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(args), flush=True)
    return subprocess.run(args, cwd=cwd, check=True, text=True, capture_output=False)


def main() -> int:
    bench = find_bench()
    if bench is None:
        if "--required" in sys.argv:
            die("No Frappe Bench found in current directory or ./frappe-bench. "
                "A Git repository is not itself a Bench; first create a dedicated Frappe Bench and agentsteers-dev site.")
        print("Frappe: no local Bench in current directory or ./frappe-bench; "
              "skipping App installation (MCP mock can still start).", flush=True)
        return 0
    site = select_site(bench)
    link = bench / "apps" / APP_NAME
    if link.is_symlink():
        if link.resolve() != APP_SRC.resolve():
            die("Conflicting Frappe app symlink; refusing to overwrite.")
    elif link.exists():
        if link.resolve() != APP_SRC.resolve():
            die("Conflicting Frappe app directory; refusing to overwrite.")
    else:
        link.symlink_to(APP_SRC, target_is_directory=True)
        print(f"Linked AgentSteers Frappe app: {link}", flush=True)

    python = str(bench / "env" / "bin" / "python")
    bench_cmd = str(bench / "env" / "bin" / "bench")
    if not Path(bench_cmd).is_file():
        bench_cmd = shutil.which("bench") or ""
    if not bench_cmd:
        die("bench CLI unavailable; install Bench CLI for this environment.")
    run(python, "-m", "pip", "install", "-e", str(link), cwd=bench)
    apps = subprocess.run([bench_cmd, "--site", site, "list-apps"],
                          cwd=bench, check=True, capture_output=True, text=True).stdout
    installed = {line.split()[0] for line in apps.splitlines() if line.strip()}
    if APP_NAME not in installed:
        run(bench_cmd, "--site", site, "install-app", APP_NAME, cwd=bench)
    run(bench_cmd, "--site", site, "migrate", cwd=bench)
    run(bench_cmd, "build", "--app", APP_NAME, cwd=bench)
    run(bench_cmd, "--site", site, "clear-website-cache", cwd=bench)
    print(f"AgentSteers Frappe app updated on development site {site}; no public deploy.", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Frappe setup stopped: {exc}", file=sys.stderr)
        raise SystemExit(1)
