"""Production Frappe WSGI application with public assets (never private files)."""
from pathlib import Path
from werkzeug.middleware.shared_data import SharedDataMiddleware
from frappe.app import application as frappe_application

application = SharedDataMiddleware(
    frappe_application, {'/assets': str(Path.cwd() / 'assets')}, cache=False
)
