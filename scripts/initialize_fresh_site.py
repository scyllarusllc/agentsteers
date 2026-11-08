"""Initialize only a confirmed absent database in the dedicated managed Bench.

Uses Linux root's socket access solely for provisioning, never for running Frappe.
No root password is copied, changed, or passed to Bench.
"""
from pathlib import Path
import datetime
import json
import os
import subprocess
import sys
from frappe_database_auth import _root_sql, _literal, _identifier

SITE = 'agentsteers.com'


def initialize_fresh_site(bench: Path, root: Path) -> None:
    if not sys.stdin.isatty():
        raise RuntimeError('Fresh initialization requires an interactive terminal; no changes made.')
    if bench.resolve() != (root / 'frappe-bench').resolve() or bench.is_symlink():
        raise RuntimeError('Fresh initialization is restricted to the project-managed Bench.')
    folder = bench / 'sites' / SITE
    config_path = folder / 'site_config.json'
    if folder.is_symlink() or config_path.is_symlink():
        raise RuntimeError('Symlinked site configuration; initialization refused.')
    config = json.loads(config_path.read_text())
    common = json.loads((bench / 'sites/common_site_config.json').read_text())
    merged = {**common, **config}
    db = config.get('db_name')
    user = config.get('db_user') or db
    password = config.get('db_password')
    _identifier(db)
    if user != db or not isinstance(password, str) or len(password) < 16:
        raise RuntimeError('Expected a generated Frappe database name/user and password; refusing initialization.')
    if (merged.get('db_host') not in (None, 'localhost', '127.0.0.1')
            or int(merged.get('db_port') or 3306) != 3306
            or merged.get('db_type', 'mariadb') != 'mariadb'
            or merged.get('db_socket')):
        raise RuntimeError('Fresh initialization supports only the local default MariaDB instance.')
    print('Checking database and account absence using Linux root socket access. '
          'su prompts for the Linux root password, not a MariaDB root password.', flush=True)
    query = ("SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=" + _literal(db) + ";\n"
             "SELECT COUNT(*) FROM mysql.user WHERE User=" + _literal(user) + ";\n")
    if _root_sql(query, read_only=True).splitlines() != ['0', '0']:
        raise RuntimeError('Database or account already exists. Initialization refused; no reset or overwrite.')
    answer = input('Confirmed missing database and account. Type INITIALIZE FRESH SITE to create them: ').strip()
    if answer != 'INITIALIZE FRESH SITE':
        raise RuntimeError('Fresh initialization cancelled; no changes made.')
    # No IF EXISTS, DROP, or ALTER USER: a concurrent creation makes this fail.
    # Database comes first so an existing database cannot be paired with a new user.
    sql = (f'CREATE DATABASE {_identifier(db)} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n'
           f'CREATE USER {_literal(user)}@\'localhost\' IDENTIFIED BY {_literal(password)};\n'
           f'GRANT ALL PRIVILEGES ON {_identifier(db)}.* TO {_literal(user)}@\'localhost\';\n')
    _root_sql(sql)
    # Provisioning succeeded before moving any files. Preserve the original config.
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    archive = bench / 'sites' / ('.agentsteers-incomplete-' + stamp)
    if archive.exists():
        raise RuntimeError('Archive collision; site files unchanged, inspect provisioned database manually.')
    folder.rename(archive)
    print(f'Preserved original site files: {archive}', flush=True)
    try:
        subprocess.run([str(bench / 'env/bin/python'), str(Path(__file__).resolve()),
                        '--bootstrap', str(archive / 'site_config.json')], cwd=bench / 'sites', check=True)
    except BaseException:
        if not folder.exists():
            archive.rename(folder)
        raise RuntimeError('Fresh initialization failed. Database/account and site files were preserved; '
                           'no automatic retry or deletion. Inspect before recovery.') from None
    print('Fresh Frappe site initialized as the non-root Bench owner.', flush=True)


if __name__ == '__main__':
    # Internal child process: credentials are read from the private archived config,
    # never placed in process arguments or environment variables.
    if len(sys.argv) != 3 or sys.argv[1] != '--bootstrap' or os.geteuid() == 0:
        raise SystemExit('Internal bootstrap must run as the non-root Bench owner.')
    config = json.loads(Path(sys.argv[2]).read_text())
    import frappe
    from frappe.installer import _new_site
    frappe.init(site=SITE, new_site=True)
    _new_site(config['db_name'], SITE, db_password=config['db_password'],
              db_type='mariadb', db_host='localhost', setup_db=False, install_apps=[])
