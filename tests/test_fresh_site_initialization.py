"""Fresh-site provisioning must never overwrite existing database objects."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('initialize_fresh_site', SCRIPTS / 'initialize_fresh_site.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class FreshSiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.bench = self.root / 'frappe-bench'
        self.folder = self.bench / 'sites' / mod.SITE
        self.folder.mkdir(parents=True)
        self.config = self.folder / 'site_config.json'
        self.config.write_text(json.dumps({'db_name': '_fresh_example', 'db_password': 'x' * 32}))
        (self.bench / 'sites/common_site_config.json').write_text('{}')
        for name, kwargs in [('sys.stdin.isatty', {'return_value': True}),
                             ('_root_sql', {}), ('subprocess.run', {})]:
            if name.startswith('sys.'):
                p = patch.object(mod.sys.stdin, 'isatty', **kwargs)
            elif name.startswith('subprocess.'):
                p = patch.object(mod.subprocess, 'run', **kwargs)
            else:
                p = patch.object(mod, name, **kwargs)
            mock = p.start(); self.addCleanup(p.stop)
            if name == '_root_sql': self.sql = mock
            if name == 'subprocess.run': self.run = mock

    def test_existing_database_or_account_never_changes_files(self):
        for result in ['1\n0', '0\n1', '1\n1', 'unexpected']:
            self.sql.return_value = result
            with self.assertRaisesRegex(RuntimeError, 'already exists'):
                mod.initialize_fresh_site(self.bench, self.root)
            self.assertTrue(self.config.exists())
        self.run.assert_not_called()
        self.assertTrue(all(c.kwargs.get('read_only') for c in self.sql.call_args_list))

    def test_socket_auth_failure_does_not_move_site(self):
        self.sql.side_effect = RuntimeError('socket access denied')
        with self.assertRaisesRegex(RuntimeError, 'socket access denied'):
            mod.initialize_fresh_site(self.bench, self.root)
        self.assertTrue(self.config.exists())
        self.run.assert_not_called()

    def test_declining_initialization_does_not_provision(self):
        self.sql.return_value = '0\n0'
        with patch('builtins.input', return_value=''), self.assertRaisesRegex(RuntimeError, 'cancelled'):
            mod.initialize_fresh_site(self.bench, self.root)
        self.assertEqual(self.sql.call_count, 1)
        self.assertTrue(self.config.exists())

    def test_provisioning_failure_keeps_original_site_in_place(self):
        self.sql.side_effect = ['0\n0', RuntimeError('provision failed')]
        with patch('builtins.input', return_value='INITIALIZE FRESH SITE'):
            with self.assertRaisesRegex(RuntimeError, 'provision failed'):
                mod.initialize_fresh_site(self.bench, self.root)
        self.assertTrue(self.config.exists())
        self.run.assert_not_called()

    def test_success_archives_files_and_never_passes_password_in_arguments(self):
        self.sql.side_effect = ['0\n0', '']
        with patch('builtins.input', return_value='INITIALIZE FRESH SITE'):
            mod.initialize_fresh_site(self.bench, self.root)
        archives = list((self.bench / 'sites').glob('.agentsteers-incomplete-*'))
        self.assertEqual(len(archives), 1)
        self.assertTrue((archives[0] / 'site_config.json').exists())
        self.assertNotIn('x' * 32, str(self.run.call_args))
        statement = self.sql.call_args_list[1].args[0]
        self.assertNotIn('DROP ', statement)
        self.assertNotIn('ALTER USER', statement)
        self.assertIn('CREATE DATABASE', statement)

    def test_bootstrap_failure_restores_original_if_no_partial_directory(self):
        self.sql.side_effect = ['0\n0', '']
        self.run.side_effect = RuntimeError('bootstrap failed')
        with patch('builtins.input', return_value='INITIALIZE FRESH SITE'):
            with self.assertRaisesRegex(RuntimeError, 'no automatic retry'):
                mod.initialize_fresh_site(self.bench, self.root)
        self.assertTrue(self.config.exists())

    def test_remote_database_refused_before_root_query(self):
        (self.bench / 'sites/common_site_config.json').write_text('{"db_host":"remote.example"}')
        with self.assertRaisesRegex(RuntimeError, 'local default'):
            mod.initialize_fresh_site(self.bench, self.root)
        self.sql.assert_not_called()


if __name__ == '__main__':
    unittest.main()
