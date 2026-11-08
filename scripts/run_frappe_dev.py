#!/usr/bin/env python3
"""Run a dedicated Frappe development website, never the production site."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from install_frappe_dev import find_bench, select_site

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    bench = find_bench()
    if bench is None:
        raise RuntimeError("No development Bench found. Set AGENTSTEERS_BENCH_DIR to a dedicated development Bench.")
    site = select_site(bench)
    if site == "agentsteers.com":
        raise RuntimeError("Refusing to serve production site.")
    # Only use a dedicated development Bench. Do not reuse the managed
    # production Bench created by make setup or the public site.
    if bench == (ROOT / "frappe-bench").resolve():
        raise RuntimeError("Project-managed frappe-bench is used for production; provide a separate development Bench.")
    cli = bench / "env" / "bin" / "bench"
    if not cli.is_file():
        raise RuntimeError("Development Bench CLI not found at env/bin/bench.")
    port = os.environ.get("AGENTSTEERS_DEV_PORT", "8001")
    if not port.isdigit() or not 1024 <= int(port) <= 65535:
        raise RuntimeError("AGENTSTEERS_DEV_PORT must be a number from 1024 to 65535.")
    print(f"Starting Frappe development site {site} at http://127.0.0.1:{port}", flush=True)
    print("Localhost only. Press Ctrl+C to stop. This does not deploy or restart production.", flush=True)
    subprocess.run([str(cli), "--site", site, "serve", "--host", "127.0.0.1",
                    "--port", port, "--noreload"], cwd=bench, check=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f"Frappe development server stopped: {exc}", file=sys.stderr)
        raise SystemExit(1)
