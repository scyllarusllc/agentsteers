"""Production Frappe WSGI application with public assets (never private files).

The embedded /mcp adapter is disabled by default and remains blocked by Caddy.
It shares the existing Gunicorn process; no additional service is started.
"""
from pathlib import Path
from werkzeug.middleware.shared_data import SharedDataMiddleware
from frappe.app import application as frappe_application
from embedded_mcp_wsgi import application as embedded_mcp_application

website_application = SharedDataMiddleware(
    frappe_application, {'/assets': str(Path.cwd() / 'assets')}, cache=False
)


def application(environ, start_response):
    if environ.get("PATH_INFO") == "/mcp":
        return embedded_mcp_application(environ, start_response)
    return website_application(environ, start_response)
