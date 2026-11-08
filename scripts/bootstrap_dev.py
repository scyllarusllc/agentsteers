#!/usr/bin/env python3
"""Prepare AgentSteers' local virtual environment without sudo or system edits."""
from __future__ import annotations

import datetime
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / ".venv"


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(args, check=check, cwd=ROOT)


def backup_existing() -> None:
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = ROOT / f".venv.backup.{stamp}.{os.getpid()}"
    VENV.rename(destination)
    print(f"Existing virtual environment moved to {destination.name}", flush=True)


def healthy_environment() -> bool:
    interpreter = VENV / "bin" / "python"
    if not interpreter.is_file():
        return False
    probe = subprocess.run(
        [str(interpreter), "-c",
         "import sys, pip; assert sys.version_info >= (3, 11); "
         "assert sys.prefix != sys.base_prefix"],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        check=False,
    )
    return probe.returncode == 0


def main() -> int:
    if sys.version_info < (3, 11):
        print(
            "AgentSteers development requires Python 3.11+. "
            "On CentOS Stream 9: sudo dnf install python3.11 python3.11-pip; "
            "then run make PYTHON=python3.11 dev.",
            file=sys.stderr,
        )
        return 2
    if healthy_environment():
        print("Existing .venv uses Python 3.11+ and has pip.", flush=True)
        return 0

    if VENV.exists():
        interpreter = VENV / "bin" / "python"
        # Try repairing the existing 3.11+ virtual environment first.
        if interpreter.is_file():
            version = subprocess.run(
                [str(interpreter), "-c", "import sys; assert sys.version_info >= (3, 11)"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
            )
            if version.returncode == 0:
                run(str(interpreter), "-m", "ensurepip", "--upgrade", check=False)
                if healthy_environment():
                    print("Repaired pip in existing .venv.", flush=True)
                    return 0
        backup_existing()

    print("Creating isolated Python 3.11+ virtual environment...", flush=True)
    if run(sys.executable, "-m", "venv", str(VENV), check=False).returncode != 0:
        print(
            "Could not create a Python environment. On CentOS Stream 9 "
            "install: sudo dnf install python3.11 python3.11-pip",
            file=sys.stderr,
        )
        return 2

    if not healthy_environment():
        interpreter = VENV / "bin" / "python"
        if interpreter.is_file():
            run(str(interpreter), "-m", "ensurepip", "--upgrade", check=False)
    if not healthy_environment():
        print(
            "The virtual environment is missing pip. On CentOS Stream 9 "
            "run: sudo dnf install python3.11-pip; then make dev. "
            "No system Python was modified.",
            file=sys.stderr,
        )
        return 2
    print("Python 3.11+ virtual environment and pip are ready.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
