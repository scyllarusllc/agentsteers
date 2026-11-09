"""Register development apps before install-app and resume partial installation."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import dev_environment as dev


class DevAppSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.bench = self.root / 'dev'; self.source = self.root / 'app'
        self.source.mkdir()
        (self.bench / 'apps/frappe').mkdir(parents=True)
        (self.bench / 'sites').mkdir()
        (self.bench / 'sites/apps.txt').write_text('frappe')
        for name, value in [('DEV_BENCH', self.bench), ('APP_SRC', self.source)]:
            p = patch.object(dev, name, value); p.start(); self.addCleanup(p.stop)
        for name in ['validate', 'ensure_bench_redis', 'isolate_site', 'ensure_yarn']:
            p = patch.object(dev, name); p.start(); self.addCleanup(p.stop)
        p = patch.object(dev, 'bench_cli', return_value='/managed/bench'); p.start(); self.addCleanup(p.stop)

    def test_manifest_registered_before_install_and_build(self):
        calls = []
        def run(args, cwd):
            calls.append(args)
            if 'install-app' in args:
                self.assertEqual((self.bench / 'sites/apps.txt').read_text().splitlines(),
                                 ['frappe', 'agentsteers_frappe'])
        result = subprocess.CompletedProcess([], 0, 'frappe 15.0.0\n', '')
        with patch.object(dev.subprocess, 'run', return_value=result), patch.object(dev, 'run', side_effect=run):
            dev.prepare_dev_app()
        self.assertTrue((self.bench / 'apps/agentsteers_frappe').is_symlink())
        self.assertEqual(sum('install-app' in c for c in calls), 1)
        self.assertEqual(sum('build' in c for c in calls), 1)

    def test_complete_site_is_not_reinstalled_or_rebuilt(self):
        p = self.bench / 'sites/assets/assets.json'; p.parent.mkdir()
        p.write_text(json.dumps({x: '/assets/generated' for x in
                                ['website.bundle.css', 'login.bundle.css', 'frappe-web.bundle.js']}))
        result = subprocess.CompletedProcess([], 0, 'frappe 15\nagentsteers_frappe 0.1\n', '')
        with patch.object(dev.subprocess, 'run', return_value=result), patch.object(dev, 'run') as run:
            dev.prepare_dev_app(); dev.prepare_dev_app()
        run.assert_not_called()
        self.assertEqual((self.bench / 'sites/apps.txt').read_text().count('agentsteers_frappe'), 1)

    def test_symlinked_manifest_is_not_changed(self):
        p = self.bench / 'sites/apps.txt'; p.unlink()
        target = self.root / 'production_apps'; target.write_text('preserved')
        p.symlink_to(target)
        with self.assertRaisesRegex(RuntimeError, 'symlinked'):
            dev.prepare_dev_app()
        self.assertEqual(target.read_text(), 'preserved')
