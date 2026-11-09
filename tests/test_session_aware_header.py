"""Static regressions for session-aware navigation on Frappe website pages."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / "frappe_app" / "agentsteers_frappe" / "www"


class SessionHeaderTests(unittest.TestCase):
    def test_header_uses_frappe_session_not_local_storage(self):
        header = (ROOT / "includes" / "site_header.html").read_text()
        self.assertIn('frappe.session.user != "Guest"', header)
        self.assertIn("{% if agentsteers_signed_in %}", header)
        self.assertIn('frappe.get_fullname(frappe.session.user)', header)
        self.assertIn('{{ agentsteers_display_name | e }}', header)
        self.assertIn('href="/user/account" aria-label="Your account"', header)
        self.assertIn('href="/?cmd=web_logout">Sign out</a>', header)
        self.assertIn('href="/user/login?redirect-to=%2Fuser%2Faccount">Sign in</a>', header)

    def test_mcp_navigation_and_page_are_informational(self):
        header = (ROOT / "includes" / "site_header.html").read_text()
        page = (ROOT / "mcp-connection.html").read_text()
        self.assertIn('href="/mcp-connection">MCP Connection</a>', header)
        self.assertIn("Connection status:", page)
        self.assertIn("Not verified", page)
        self.assertIn("No production commands are executed", page)

    def test_every_session_aware_page_disables_cache(self):
        for name in ("index", "privacy", "terms", "account", "user/login", "mcp-connection"):
            with self.subTest(name=name):
                self.assertIn("no_cache = True", (ROOT / (name + ".py")).read_text())
                self.assertIn('includes/site_header.html', (ROOT / (name + ".html")).read_text())


if __name__ == "__main__":
    unittest.main()
