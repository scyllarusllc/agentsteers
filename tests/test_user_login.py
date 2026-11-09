"""Custom login delegates authentication and fixes the return path locally."""
import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys
import unittest
from unittest.mock import Mock, patch

PAGE = Path(__file__).resolve().parents[1] / 'frappe_app/agentsteers_frappe/www/user/login.py'


class UserLoginTests(unittest.TestCase):
    def load(self, user='Guest', target=None):
        frappe = ModuleType('frappe')
        frappe.session = SimpleNamespace(user=user)
        frappe.local = SimpleNamespace(flags=SimpleNamespace(),
                                       request=SimpleNamespace(args={'redirect-to': target}))
        frappe.Redirect = type('Redirect', (Exception,), {})
        login = ModuleType('frappe.www.login'); login.get_context = Mock(return_value={'login': True})
        modules = {'frappe': frappe, 'frappe.www': ModuleType('frappe.www'), 'frappe.www.login': login}
        p = patch.dict(sys.modules, modules); p.start(); self.addCleanup(p.stop)
        spec = importlib.util.spec_from_file_location('user_login_test', PAGE)
        page = importlib.util.module_from_spec(spec); spec.loader.exec_module(page)
        return page, frappe, login

    def test_guest_uses_existing_frappe_authentication(self):
        page, frappe, login = self.load(target='/user/account')
        self.assertEqual(page.get_context({}), {'login': True})
        login.get_context.assert_called_once_with({})
        self.assertTrue(page.no_cache)

    def test_missing_or_external_return_url_is_canonicalized(self):
        for target in [None, 'https://evil.example', '//evil.example', '/app']:
            with self.subTest(target=target):
                page, frappe, login = self.load(target=target)
                with self.assertRaises(frappe.Redirect): page.get_context({})
                self.assertEqual(frappe.local.flags.redirect_location,
                                 '/user/login?redirect-to=%2Fuser%2Faccount')
                login.get_context.assert_not_called()

    def test_signed_in_session_goes_to_account(self):
        page, frappe, login = self.load(user='owner@example.com')
        with self.assertRaises(frappe.Redirect): page.get_context({})
        self.assertEqual(frappe.local.flags.redirect_location, '/user/account')
        login.get_context.assert_not_called()
