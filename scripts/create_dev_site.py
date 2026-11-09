"""Provision a fresh, separate development database using root socket access."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from frappe_database_auth import _root_sql, _identifier, _literal

SITE = 'agentsteers-dev.localhost'


def create_dev_site(bench, root, production):
    bench, root = Path(bench), Path(root)
    if (os.geteuid() == 0 or not sys.stdin.isatty()
            or bench.is_symlink() or bench.resolve() != (root / 'frappe-dev-bench').resolve()):
        raise RuntimeError('Use the non-root owner interactively in the isolated development Bench.')
    folder = bench / 'sites' / SITE
    secret_file = bench / 'config/agentsteers-dev-provisioning.json'
    if folder.exists() or folder.is_symlink() or secret_file.exists() or secret_file.is_symlink():
        raise RuntimeError('Partial dev provisioning exists; preserve files and inspect before retrying.')
    common = json.loads((bench / 'sites/common_site_config.json').read_text())
    if common.get('db_host') not in (None, 'localhost', '127.0.0.1') or int(common.get('db_port') or 3306) != 3306 or common.get('db_socket'):
        raise RuntimeError('Only the default local MariaDB instance supports automatic development provisioning.')
    db = '_agentsteers_dev_' + secrets.token_hex(6)
    if db in (production.get('db_name'), production.get('db_user')):
        raise RuntimeError('Refusing shared production database or account.')
    password = secrets.token_urlsafe(36)
    query = (f'SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME={_literal(db)};\n'
             f'SELECT COUNT(*) FROM mysql.user WHERE User={_literal(db)};\n')
    if _root_sql(query, read_only=True).splitlines() != ['0', '0']:
        raise RuntimeError('Generated development database/account already exists; refusing overwrite.')
    # Save generated credentials before provisioning so a failed attempt is recoverable.
    fd = os.open(secret_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump({'db_name': db, 'db_password': password}, f)
    sql = (f'CREATE DATABASE {_identifier(db)} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n'
           f'CREATE USER {_literal(db)}@\'localhost\' IDENTIFIED BY {_literal(password)};\n'
           f'GRANT ALL PRIVILEGES ON {_identifier(db)}.* TO {_literal(db)}@\'localhost\';\n')
    _root_sql(sql)
    subprocess.run([str(bench / 'env/bin/python'), str(Path(__file__).resolve()),
                    '--bootstrap', str(secret_file)], cwd=bench / 'sites', check=True)
    secret_file.unlink()


if __name__ == '__main__':
    if len(sys.argv) != 3 or sys.argv[1] != '--bootstrap' or os.geteuid() == 0:
        raise SystemExit('Internal bootstrap requires the non-root Bench owner.')
    expected = Path(__file__).resolve().parents[1] / 'frappe-dev-bench/sites'
    if Path.cwd().resolve() != expected.resolve():
        raise SystemExit('Refusing bootstrap outside the isolated development Bench.')
    config = json.loads(Path(sys.argv[2]).read_text())
    import frappe
    from frappe.installer import _new_site
    frappe.init(site=SITE, new_site=True)
    _new_site(config['db_name'], SITE, db_password=config['db_password'],
              db_type='mariadb', db_host='localhost', setup_db=False, install_apps=[])
