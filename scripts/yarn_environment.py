"""Project-local Yarn Classic for Frappe asset builds.

Never chmod a system executable, run sudo or modify global npm packages.
Use a working Yarn Classic from PATH, or install a private copy via npm.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent.parent
PREFIX = ROOT / ".node-tools"
LOCAL_BIN = PREFIX / "node_modules" / ".bin"
YARN = LOCAL_BIN / "yarn"


def _version(command: str) -> str | None:
    try:
        proc = subprocess.run([command, "--version"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    value = proc.stdout.strip()
    return value if value.startswith("1.") else None


def ensure_yarn() -> str:
    """Make executable Yarn v1 available to child Bench processes."""
    node = shutil.which("node")
    if not node or not _node_runs(node):
        raise RuntimeError("Node.js is unavailable or not executable; fix Node installation first.")
    if PREFIX.is_symlink():
        raise RuntimeError("Refusing symlinked project-local Yarn directory.")
    if _version(str(YARN)):
        selected = str(YARN)
    else:
        system_yarn = shutil.which("yarn")
        if system_yarn and _version(system_yarn):
            selected = system_yarn
        else:
            npm = shutil.which("npm")
            if not npm:
                raise RuntimeError("Yarn unusable and npm not found; install working Node.js/npm.")
            PREFIX.mkdir(parents=True, exist_ok=True)
            print("Installing Yarn Classic into project-local .node-tools (no sudo)...", flush=True)
            subprocess.run([npm, "install", "--prefix", str(PREFIX),
                            "--no-audit", "--no-fund", "--no-save", "yarn@1.22.22"],
                           check=True)
            if not _version(str(YARN)):
                raise RuntimeError("Project-local Yarn could not run after installation.")
            selected = str(YARN)
    # Frappe/Bench launches yarn as a subprocess by name.
    # For a working system Yarn, prepending LOCAL_BIN is harmless.
    if selected == str(YARN):
        os.environ["PATH"] = str(LOCAL_BIN) + os.pathsep + os.environ.get("PATH", "")
    print("Verified executable Yarn Classic:", selected, flush=True)
    return selected


def _node_runs(path: str) -> bool:
    try:
        result = subprocess.run([path, "--version"], capture_output=True, timeout=15)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False
