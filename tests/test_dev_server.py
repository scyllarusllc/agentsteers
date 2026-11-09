"""Development server must bind only loopback and never enable a remote debugger."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('serve_dev_site', ROOT / 'scripts/serve_dev_site.py')
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)


class DevServerTests(unittest.TestCase):
    def test_explicit_loopback_no_debugger(self):
        frappe = ModuleType('frappe'); app = ModuleType('frappe.app'); frappe.app = app
        app.application_with_statics = Mock(return_value=object())
        werkzeug = ModuleType('werkzeug'); serving = ModuleType('werkzeug.serving')
        serving.run_simple = Mock()
        with patch.dict(sys.modules, {'frappe': frappe, 'frappe.app': app, 'werkzeug': werkzeug, 'werkzeug.serving': serving}), \
             patch.object(Path, 'cwd', return_value=ROOT / 'frappe-dev-bench/sites'), \
             patch.object(sys, 'argv', ['serve', '--site', 'agentsteers-dev.localhost', '--port', '8001']):
            mod.main()
        call = serving.run_simple.call_args
        self.assertEqual(call.args[:2], ('127.0.0.1', 8001))
        self.assertFalse(call.kwargs['use_debugger'])
        self.assertFalse(call.kwargs['use_evalex'])
        self.assertEqual(app._site, 'agentsteers-dev.localhost')

    def test_production_cwd_refused(self):
        with patch.object(Path, 'cwd', return_value=ROOT / 'frappe-bench/sites'), \
             patch.object(sys, 'argv', ['serve', '--site', 'agentsteers-dev.localhost', '--port', '8001']):
            with self.assertRaises(SystemExit):
                mod.main()
