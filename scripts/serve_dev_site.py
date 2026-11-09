"""Serve only the isolated development site, without a public debugger."""
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--site', required=True, choices=['agentsteers-dev.localhost'])
    parser.add_argument('--port', required=True, type=int)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Port must be between 1024 and 65535')
    expected = Path(__file__).resolve().parents[1] / 'frappe-dev-bench/sites'
    if Path.cwd().resolve() != expected.resolve():
        parser.error('Refusing to serve outside the dedicated development Bench')
    import frappe.app
    from werkzeug.serving import run_simple
    frappe.app._site = args.site
    frappe.app._sites_path = str(expected)
    application = frappe.app.application_with_statics()
    run_simple('127.0.0.1', args.port, application, use_reloader=False,
               use_debugger=False, use_evalex=False, threaded=True)


if __name__ == '__main__':
    main()
