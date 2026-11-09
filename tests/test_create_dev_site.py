"""Development provisioning creates only new credentials and preserves partial work."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('create_dev_site', SCRIPTS / 'create_dev_site.py')
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)


class CreateDevSiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.bench = self.root / 'frappe-dev-bench'
        for name in ['config', 'sites']:
            (self.bench / name).mkdir(parents=True)
        (self.bench / 'sites/common_site_config.json').write_text('{}')
        p = patch.object(mod.os, 'geteuid', return_value=1002); p.start(); self.addCleanup(p.stop)
        p = patch.object(mod.sys.stdin, 'isatty', return_value=True); p.start(); self.addCleanup(p.stop)
        self.production = {'db_name': 'production_db', 'db_user': 'production_user'}

    def test_creates_only_separate_db_without_password_in_argv(self):
        with patch.object(mod, '_root_sql', side_effect=['0\n0', '']) as sql, \
             patch.object(mod.subprocess, 'run') as run:
            mod.create_dev_site(self.bench, self.root, self.production)
        statement = sql.call_args_list[1].args[0]
        self.assertIn('CREATE DATABASE `_agentsteers_dev_', statement)
        self.assertNotIn('production_', statement)
        self.assertNotIn('DROP ', statement)
        self.assertEqual(len(run.call_args.args[0]), 4)
        self.assertFalse((self.bench / 'config/agentsteers-dev-provisioning.json').exists())

    def test_partial_provisioning_is_never_retried(self):
        p = self.bench / 'config/agentsteers-dev-provisioning.json'; p.write_text('preserved')
        with patch.object(mod, '_root_sql') as sql:
            with self.assertRaisesRegex(RuntimeError, 'Partial dev provisioning'):
                mod.create_dev_site(self.bench, self.root, self.production)
        self.assertEqual(p.read_text(), 'preserved'); sql.assert_not_called()

    def test_bootstrap_failure_preserves_private_credentials(self):
        with patch.object(mod, '_root_sql', side_effect=['0\n0', '']), \
             patch.object(mod.subprocess, 'run', side_effect=RuntimeError('bootstrap failure')):
            with self.assertRaises(RuntimeError):
                mod.create_dev_site(self.bench, self.root, self.production)
        p = self.bench / 'config/agentsteers-dev-provisioning.json'
        self.assertEqual(p.stat().st_mode & 0o777, 0o600)
        self.assertNotEqual(json.loads(p.read_text())['db_name'], 'production_db')

    def test_existing_database_refused_without_mutation(self):
        with patch.object(mod, '_root_sql', return_value='1\n0') as sql, patch.object(mod.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'already exists'):
                mod.create_dev_site(self.bench, self.root, self.production)
        self.assertEqual(sql.call_count, 1); run.assert_not_called()
