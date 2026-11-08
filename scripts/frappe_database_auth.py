"""Opt-in repair for a *missing* local Frappe MariaDB account.

Only the dedicated AgentSteers Bench is eligible. Reads existing site
credentials without printing them; never changes existing DB users.
Root authentication is performed by the OS 'su' command.
"""
from __future__ import annotations

import json
import os
import shlex
import tempfile
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


def diagnose_mariadb_root_socket() -> bool:
    """Read-only MariaDB root socket test via interactive Linux su."""
    if not sys.stdin.isatty() or not shutil.which("su") or not shutil.which("mariadb"):
        print("Socket diagnostic requires an interactive terminal and su/mariadb.",
              file=sys.stderr, flush=True)
        return False
    print("Testing MariaDB root via local Unix socket. Linux su may prompt "
          "for its password. No database changes will be made.", flush=True)
    result = subprocess.run(
        ["su", "-c",
         "mariadb --protocol=socket -u root --batch --skip-column-names "
         "-e 'SELECT CURRENT_USER(), VERSION();'"],
        stdin=None, stdout=subprocess.PIPE, stderr=None, text=True, check=False,
    )
    if result.returncode == 0:
        print("MariaDB root socket authentication succeeded.", flush=True)
        return True
    print("MariaDB root socket authentication failed (or Linux su was denied). "
          "See the preceding terminal error. No credentials or privileges "
          "were changed.", file=sys.stderr, flush=True)
    return False


def _root_sql(sql: str, *, read_only: bool = False) -> str:
    """Authenticate su through the terminal; give MariaDB separate SQL input.

    A private temporary SQL file is removed after the single attempt. It is
    never printed, and neither SQL nor passwords appear in process arguments.
    """
    if not shutil.which("su") or not shutil.which("mariadb"):
        raise RuntimeError("su and mariadb client are required for account inspection.")
    if not sys.stdin.isatty():
        raise RuntimeError("Interactive terminal required for Linux root authentication.")
    print("su will ask for the Linux root password in the terminal. "
          "Password input is hidden; one attempt only.", flush=True)
    with tempfile.TemporaryDirectory(prefix="agentsteers-db-check-") as folder:
        sql_path = Path(folder) / "query.sql"
        fd = os.open(sql_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write("SET SESSION sql_mode='NO_BACKSLASH_ESCAPES';\n")
                stream.write(sql)
        except BaseException:
            raise
        command = ("mariadb --protocol=socket -u root --batch --skip-column-names --raw < "
                   + shlex.quote(str(sql_path)))
        result = subprocess.run(
            ["su", "-c", command],
            stdin=None, stdout=subprocess.PIPE, stderr=None,
            text=True, check=False,
        )
        if result.returncode != 0:
            if read_only:
                diagnose_mariadb_root_socket()
            raise RuntimeError("Linux root authentication or MariaDB administrator 
                               "query failed. See terminal output; no automatic retry.")
        return result.stdout.strip()


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
