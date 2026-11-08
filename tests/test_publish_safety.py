"""Regression tests: publishing must never recover or rebuild a failed site."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('publish_frappe', SCRIPTS / 'publish_frappe.py')
publish = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publish)


class PublishSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bench = self.root / 'frappe-bench'
        for name in ['apps/frappe', 'sites/agentsteers.com', 'env/bin']:
            (self.bench / name).mkdir(parents=True)
        for name in ['env/bin/python', 'env/bin/bench', 'sites/common_site_config.json',
                     'sites/agentsteers.com/site_config.json']:
            (self.bench / name).touch()
        self.calls = []
        for name, value in [('ROOT', self.root), ('APP_SRC', self.root / 'frappe_app')]:
            p = patch.object(publish, name, value); p.start(); self.addCleanup(p.stop)
        for name in ['verify_git_release', 'resolve_bench', 'ensure_apps_manifest',
                     'ensure_mariadb', 'diagnose_site_database_config', 'confirm_release',
                     'ensure_yarn', 'run', 'health_check']:
            p = patch.object(publish, name); mock = p.start(); self.addCleanup(p.stop)
            setattr(self, name, mock)
        self.resolve_bench.return_value = self.bench
        self.verify_git_release.return_value = 'test-commit'
        self.run.side_effect = lambda args, **kwargs: self.calls.append(args) or 'frappe\n'
        p = patch.object(publish.os, 'geteuid', return_value=1000)
        p.start(); self.addCleanup(p.stop)
        p = patch.object(publish.os, 'access', return_value=True)
        p.start(); self.addCleanup(p.stop)

    def test_auth_failure_has_no_setup_recovery_or_deployment(self):
        self.run.side_effect = RuntimeError('MariaDB authentication failed')
        with patch.object(sys, 'argv', ['publish']), self.assertRaises(RuntimeError):
            publish.main()
        self.confirm_release.assert_not_called()
        self.ensure_yarn.assert_not_called()
        self.health_check.assert_not_called()
        self.assertEqual(self.run.call_count, 1)
        self.ensure_mariadb.assert_called_once_with(self.bench, 'agentsteers.com', check_only=True)
        self.ensure_apps_manifest.assert_called_once_with(self.bench, check_only=True)

    def test_missing_bench_does_not_run_setup(self):
        self.resolve_bench.side_effect = RuntimeError('No Bench; use make setup')
        with patch.object(sys, 'argv', ['publish']), self.assertRaises(RuntimeError):
            publish.main()
        self.run.assert_not_called()
        self.ensure_yarn.assert_not_called()

    def test_check_runs_only_list_apps(self):
        with patch.object(sys, 'argv', ['publish', '--check']):
            self.assertEqual(publish.main(), 0)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][-1], 'list-apps')
        self.confirm_release.assert_not_called()
        self.ensure_yarn.assert_not_called()

    def test_backup_failure_prevents_install_migration_restart(self):
        def run(args, **kwargs):
            self.calls.append(args)
            if 'backup' in args:
                raise RuntimeError('backup failed')
            return 'frappe\n'
        self.run.side_effect = run
        with patch.object(sys, 'argv', ['publish']), self.assertRaisesRegex(RuntimeError, 'backup failed'):
            publish.main()
        self.confirm_release.assert_called_once()
        self.ensure_yarn.assert_not_called()
        self.assertEqual([c[-1] for c in self.calls], ['list-apps', '--with-files'])
        self.assertFalse((self.bench / 'apps/agentsteers_frappe').exists())

    def test_1698_is_reported_as_auth_failure(self):
        # Exercise the real command wrapper rather than the mocked deployment runner.
        spec2 = importlib.util.spec_from_file_location('publish_error_test', SCRIPTS / 'publish_frappe.py')
        mod = importlib.util.module_from_spec(spec2); spec2.loader.exec_module(mod)
        result = __import__('subprocess').CompletedProcess([], 1, '', "(1698, Access denied for user 'root'@'localhost')")
        with patch.object(mod.subprocess, 'run', return_value=result):
            with self.assertRaisesRegex(RuntimeError, 'MariaDB authentication failed'):
                mod.run(['bench', 'list-apps'], cwd=self.bench, capture=True)


class PublishGitTests(unittest.TestCase):
    def test_clean_matching_main_does_not_push(self):
        answers = [str(publish.ROOT.resolve()), 'main', '', '', 'abc', 'abc',
                   'abc refs/heads/main', 'abc', '']
        with patch.object(publish, 'git_output', side_effect=answers) as git:
            with patch.object(sys, 'argv', ['publish']):
                self.assertEqual(publish.verify_git_release(), 'abc')
        self.assertFalse(any(c.args[0] in {'add', 'commit', 'push', 'merge'}
                             for c in git.call_args_list))

    def test_divergence_never_resets_merges_or_pushes(self):
        answers = [str(publish.ROOT.resolve()), 'main', '', '', 'local', 'remote', '1 1']
        with patch.object(publish, 'git_output', side_effect=answers) as git:
            with patch.object(sys, 'argv', ['publish']):
                with self.assertRaisesRegex(RuntimeError, 'diverged'):
                    publish.verify_git_release()
        self.assertFalse(any(c.args[0] in {'reset', 'push', 'merge', 'stash'}
                             for c in git.call_args_list))

    def test_dirty_noninteractive_does_not_stage(self):
        answers = [str(publish.ROOT.resolve()), 'main', ' M Makefile', 'Makefile | 1 +']
        with patch.object(publish, 'git_output', side_effect=answers) as git:
            with patch.object(sys, 'argv', ['publish']), patch.object(publish.sys.stdin, 'isatty', return_value=False):
                with self.assertRaisesRegex(RuntimeError, 'interactive terminal'):
                    publish.verify_git_release()
        self.assertFalse(any(c.args[0] in {'add', 'commit', 'push'} for c in git.call_args_list))

    def test_ahead_push_requires_confirmation(self):
        answers = [str(publish.ROOT.resolve()), 'main', '', '', 'local', 'remote', '0 1',
                   '', 'local refs/heads/main', 'local', '']
        with patch.object(publish, 'git_output', side_effect=answers) as git:
            with patch.object(publish, 'confirm_git_action') as confirm, patch.object(sys, 'argv', ['publish']):
                self.assertEqual(publish.verify_git_release(), 'local')
        self.assertEqual(confirm.call_args.args[1], 'PUSH MAIN')
        self.assertIn(__import__('unittest.mock').mock.call('push', 'origin', 'HEAD:refs/heads/main'), git.call_args_list)

    def test_check_does_not_modify_dirty_checkout(self):
        answers = [str(publish.ROOT.resolve()), 'main', ' M Makefile']
        with patch.object(publish, 'git_output', side_effect=answers) as git:
            with patch.object(sys, 'argv', ['publish', '--check']):
                with self.assertRaisesRegex(RuntimeError, 'read-only'):
                    publish.verify_git_release()
        self.assertEqual(git.call_count, 3)


if __name__ == '__main__':
    unittest.main()
