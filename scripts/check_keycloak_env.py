"""Check Keycloak test environment before an operator starts Docker Compose.

This script intentionally never prints secret values and never starts services.
"""
from __future__ import annotations
import os
from pathlib import Path
import re
import stat
import sys

VARS = ("KC_DB_PASSWORD", "KC_BOOTSTRAP_ADMIN_USERNAME", "KC_BOOTSTRAP_ADMIN_PASSWORD")
BAD = ("REPLACE_", "CHANGE_ME", "YOUR_", "EXAMPLE", "PASSWORD")


def validate_env_file(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError("environment path must be a regular file, not a symlink")
    mode = path.stat().st_mode
    if stat.S_IMODE(mode) & 0o077:
        raise ValueError("environment file permissions must be 0600 (or stricter)")
    if hasattr(os, "geteuid") and path.stat().st_uid != os.geteuid():
        raise ValueError("environment file must be owned by current user")
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, sep, val = stripped.partition("=")
        if not sep or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key.strip()):
            raise ValueError("invalid environment line")
        key = key.strip()
        if key in values:
            raise ValueError("duplicate environment key")
        values[key] = val.strip()
    for name in VARS:
        value = values.get(name, "")
        if (not value or any(flag in value.upper() for flag in BAD)
                or any(c in value for c in ("\r", "\n", "\x00"))):
            raise ValueError(f"{name} must have a private non-placeholder value")
        if name.endswith("PASSWORD") and len(value) < 24:
            raise ValueError(f"{name} must have at least 24 characters")


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("env_file", type=Path)
    args = parser.parse_args()
    try:
        validate_env_file(args.env_file)
    except (ValueError, OSError, UnicodeError) as exc:
        print(f"Keycloak environment preflight failed: {exc}", file=sys.stderr)
        return 1
    print("Keycloak environment preflight passed (values not shown).")
    print("This does not validate Docker, DNS, proxy, realm or OAuth login.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
