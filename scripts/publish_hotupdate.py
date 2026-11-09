#!/usr/bin/env python3
"""Refresh the existing production app without installing or migrating anything.

The production Bench links this checkout directly. This command does not copy
or commit code. Use full publish for dependency, schema, hook or patch changes.
"""
from pathlib import Path
import ast
import json
import os
import subprocess
import sys

from publish_frappe import ROOT, APP_SRC, APP, DOMAIN, require, run, health_check
from website_service import reload_website_service
from bench_redis import ensure_bench_redis
from yarn_environment import ensure_yarn


def preflight():
    require(os.geteuid() != 0, 'Run as the non-root production Bench owner.')
    bench = ROOT / 'frappe-bench'
    require(not bench.is_symlink(), 'Refusing a symlinked production Bench.')
    require((bench / 'env/bin/python').is_file(), 'Production Bench missing; use make publish first.')
    site = bench / 'sites' / DOMAIN
    require(site.is_dir() and not site.is_symlink(), 'Production site missing or symlinked.')
    config = json.loads((site / 'site_config.json').read_text())
    require(not config.get('developer_mode'), 'Production developer_mode must be disabled.')
    require((bench / 'apps' / APP).resolve() == APP_SRC.resolve(),
            'Production app is not linked to this source checkout; use make publish.')
    for folder in (APP_SRC / APP / 'www', APP_SRC / APP / 'templates'):
        if folder.exists():
            require(not folder.is_symlink(), 'Refusing symlinked template directories.')
    # Catch syntax errors before replacing working web workers; never executes app code.
    for path in (APP_SRC / APP).rglob('*.py'):
        ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    ensure_bench_redis(bench)  # Health checks only; never start/replace Redis here.
    manifest = bench / 'sites/assets/assets.json'
    assets = json.loads(manifest.read_text()) if manifest.is_file() else {}
    require(all(k in assets for k in ('website.bundle.css', 'login.bundle.css', 'frappe-web.bundle.js')),
            'Core frontend assets missing; run make publish.')
    cli = ROOT / '.bench-cli-venv/bin/bench'
    require(cli.is_file() and os.access(cli, os.X_OK), 'Managed Bench CLI unavailable.')
    apps = run([str(cli), '--site', DOMAIN, 'list-apps'], cwd=bench, capture=True)
    require(APP in {line.split()[0] for line in apps.splitlines() if line.strip()},
            'Production app is not installed; run make publish.')
    return bench, str(cli)


def main():
    bench, cli = preflight()
    require(sys.stdin.isatty(), 'Interactive confirmation required for the live website refresh.')
    print('Target: https://agentsteers.com/ using the current source checkout.', flush=True)
    print('No commits, dependency installation, database migration or site backup. '
          'Use make publish for dependencies, DocTypes, hooks or database patches.', flush=True)
    require(input('Type HOTUPDATE agentsteers.com to refresh the live website: ').strip()
            == 'HOTUPDATE agentsteers.com', 'Hot update cancelled.')
    # Ordinary public CSS/JS files are served directly and do not require esbuild.
    public = APP_SRC / APP / 'public'
    if any(public.rglob('*.bundle.*')):
        ensure_yarn()
        run([cli, 'build', '--apps', APP], cwd=bench)
    else:
        print('No custom frontend bundles; skipping asset build.', flush=True)
    run([cli, '--site', DOMAIN, 'clear-cache'], cwd=bench)
    run([cli, '--site', DOMAIN, 'clear-website-cache'], cwd=bench)
    reload_website_service(bench)
    health_check('hotupdate')
    print('Live website refreshed. Gunicorn master, Caddy and other services were not restarted.', flush=True)
    print('Cloudflare may retain cached files at unchanged asset URLs; version CSS/JS URLs when changing them.', flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, SyntaxError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f'Hot update aborted: {exc}', file=sys.stderr)
        raise SystemExit(1)
