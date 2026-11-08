"""Opt-in repair for a *missing* local Frappe MariaDB account.

Only the dedicated AgentSteers Bench is eligible. Reads existing site
credentials without printing them; never changes existing DB users.
Root authentication is performed by the OS 'su' command.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
import sys


def _literal(value: str) -> str:
    """SQL string literal with backslash escapes disabled in each session."""
    if not isinstance(value, str) or not value or "\x00" in value:
        raise RuntimeError("Invalid site database credential; account repair refused.")
    return "'" + value.replace("'", "''") + "'"


def _identifier(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_]+", value):
        raise RuntimeError("Unexpected site database name; automatic repair refused.")
    return "`" + value + "`"


def _root_sql(sql: str, *, read_only: bool = False) -> str:
    """Run local MariaDB as root; retry only failed su authentication for reads.

    SQL travels on stdin, not argv. Never replay potentially partial writes.
    """
    if not shutil.which("su") or not shutil.which("mariadb"):
        raise RuntimeError("su and mariadb client are required for account inspection.")
    command = "mariadb --batch --skip-column-names --raw"
    max_attempts = 3 if read_only else 1
    for attempt in range(1, max_attempts + 1):
        if read_only:
            print(f"Linux root authentication attempt {attempt}/{max_attempts}.",
                  flush=True)
        result = subprocess.run(
            ["su", "-c", command],
            input="SET SESSION sql_mode='NO_BACKSLASH_ESCAPES';\n" + sql,
            text=True, capture_output=True, check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        # Only retry if su itself rejected the login. SQL/permission errors,
        # even on a read-only query, must not be mistaken for password typos.
        authentication_failed = bool(re.search(
            r"(?:authentication failure|incorrect password|sorry, try again)",
            result.stderr or "", flags=re.IGNORECASE,
        ))
        if read_only and authentication_failed and attempt < max_attempts:
            print("Linux root authentication failed. You can retry the password.",
                  file=sys.stderr, flush=True)
            continue
        if authentication_failed:
            raise RuntimeError(
                "Linux root authentication failed. No site or database changes were made."
            )
        raise RuntimeError(
            "MariaDB administrator query failed; check local MariaDB root socket "
            "permissions. Query errors will not be retried automatically."
        )
    raise RuntimeError("Linux root authentication attempts exhausted.")


def repair_missing_site_account(bench: Path, site: str, *, inspect_only: bool = False) -> bool:
    """Return True only when a missing account was created and granted access."""
    if site != "agentsteers.com" or not sys.stdin.isatty():
        return False
    config_path = bench / "sites" / site / "site_config.json"
    if config_path.is_symlink() or not config_path.is_file():
        raise RuntimeError("Site configuration missing or symlinked; refusing repair.")
    config = json.loads(config_path.read_text())
    if not isinstance(config, dict):
        raise RuntimeError("Invalid Frappe site configuration.")
    db = config.get("db_name")
    user = config.get("db_user") or db
    password = config.get("db_password")
    if not all(isinstance(x, str) and x for x in (db, user, password)):
        raise RuntimeError("Site database name, user or password is missing; refusing repair.")
    _identifier(db)
    if len(user) > 80 or "\x00" in user:
        raise RuntimeError("Invalid site database username.")
    # The current deployment only supports a *local* MariaDB instance.
    common = bench / "sites" / "common_site_config.json"
    merged = json.loads(common.read_text()) if common.is_file() else {}
    if not isinstance(merged, dict):
        raise RuntimeError("Invalid shared Bench configuration.")
    merged.update(config)
    host = merged.get("db_host") or "127.0.0.1"
    if host not in ("127.0.0.1", "localhost", "::1"):
        print("External MariaDB: automatic local account repair is disabled.", file=sys.stderr)
        return False

    print("Checking Frappe's configured database against MariaDB as Linux root. "
          "No account names or passwords will be printed.", flush=True)
    check_sql = (
        "SELECT CONCAT('DATABASE:', COUNT(*)) FROM information_schema.SCHEMATA "
        f"WHERE SCHEMA_NAME={_literal(db)};\n"
        "SELECT CONCAT('ACCOUNT:', COUNT(*)) FROM mysql.user "
        f"WHERE User={_literal(user)};\n"
    )
    output = _root_sql(check_sql, read_only=True).splitlines()
    if len(output) != 2 or output[0] not in ("DATABASE:0", "DATABASE:1") or not re.fullmatch(r"ACCOUNT:\d+", output[1]):
        raise RuntimeError("Unexpected MariaDB inspection result; no repair attempted.")
    if output[0] == "DATABASE:0":
        raise RuntimeError("Frappe's site database does not exist; refusing to create an account "
                           "for a missing database. No data was changed.")
    if int(output[1].split(":")[1]) > 0:
        print("The configured Frappe database account already exists. "
              "It may have an incorrect password or host permissions; "
              "existing accounts will not be reset automatically.", file=sys.stderr, flush=True)
        return False

    print("The site's database exists but its configured MariaDB account is MISSING.", flush=True)
    if inspect_only:
        print("Read-only inspection complete; no account will be created.", flush=True)
        return False
    approval = input("Type CREATE MISSING DB USER to create only that user and grant "
                     "access to the existing site database: ").strip()
    if approval != "CREATE MISSING DB USER":
        print("Account creation skipped.", flush=True)
        return False
    # CREATE USER without IF NOT EXISTS is intentional: fail rather than
    # replace a user created concurrently. Do not expose the password in argv.
    sql = (f"CREATE USER {_literal(user)}@'localhost' IDENTIFIED BY {_literal(password)};\n"
           f"GRANT ALL PRIVILEGES ON {_identifier(db)}.* TO {_literal(user)}@'localhost';\n")
    _root_sql(sql)
    print("Created missing local Frappe account and granted access to its existing database. "
          "Retrying Frappe authentication once.", flush=True)
    return True
