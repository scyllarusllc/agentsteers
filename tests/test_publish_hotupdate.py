"""Fast website refresh must not install dependencies or migrate the database."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('publish_hotupdate', SCRIPTS / 'publish_hotupdate.py')
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)


class HotUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name)
        (self.source / mod.APP / 'public').mkdir(parents=True)
        for name, value in [('APP_SRC', self.source)]:
            p = patch.object(mod, name, value); p.start(); self.addCleanup(p.stop)
        for name in ['preflight', 'ensure_yarn', 'run', 'reload_website_service', 'health_check']:
            p = patch.object(mod, name); mock = p.start(); self.addCleanup(p.stop)
            setattr(self, name, mock)
        self.preflight.return_value = (Path('/dedicated/bench'), '/managed/bench')
        p = patch.object(mod.sys.stdin, 'isatty', return_value=True); p.start(); self.addCleanup(p.stop)

    def test_plain_website_skips_build_install_and_migration(self):
        with patch('builtins.input', return_value='HOTUPDATE agentsteers.com'):
            self.assertEqual(mod.main(), 0)
        self.ensure_yarn.assert_not_called()
        commands = [c.args[0] for c in self.run.call_args_list]
        self.assertEqual([c[-1] for c in commands], ['clear-cache', 'clear-website-cache'])
        self.reload_website_service.assert_called_once_with(Path('/dedicated/bench'))
        self.health_check.assert_called_once_with('hotupdate')

    def test_custom_bundles_build_only_custom_app(self):
        (self.source / mod.APP / 'public/custom.bundle.js').write_text('console.log(1)')
        with patch('builtins.input', return_value='HOTUPDATE agentsteers.com'):
            mod.main()
        self.ensure_yarn.assert_called_once()
        self.assertEqual(self.run.call_args_list[0].args[0], ['/managed/bench', 'build', '--apps', mod.APP])
        self.assertFalse(any('migrate' in c.args[0] or 'install-app' in c.args[0]
                             for c in self.run.call_args_list))

    def test_cancellation_never_reloads(self):
        with patch('builtins.input', return_value='no'), self.assertRaisesRegex(RuntimeError, 'cancelled'):
            mod.main()
        self.run.assert_not_called(); self.reload_website_service.assert_not_called()

    def test_cache_failure_never_reloads(self):
        self.run.side_effect = RuntimeError('cache failed')
        with patch('builtins.input', return_value='HOTUPDATE agentsteers.com'), self.assertRaises(RuntimeError):
            mod.main()
        self.reload_website_service.assert_not_called(); self.health_check.assert_not_called()
