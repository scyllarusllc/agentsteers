import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('website_service', Path(__file__).resolve().parents[1] / 'scripts/website_service.py')
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)


class WebsiteServiceTests(unittest.TestCase):
    def test_other_bench_unit_is_never_restarted(self):
        result = subprocess.CompletedProcess([], 0, '/other/bench/sites\n', '')
        with patch.object(mod.Path, 'is_file', return_value=True), patch.object(mod.subprocess, 'run', return_value=result) as run:
            with self.assertRaisesRegex(RuntimeError, 'another Bench'):
                mod.restart_website_service(Path('/dedicated/bench'))
        self.assertEqual(run.call_count, 1)

    def test_missing_unit_fails_instead_of_noop_restart(self):
        with patch.object(mod.Path, 'is_file', return_value=False), patch.object(mod.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'not installed'):
                mod.restart_website_service(Path('/dedicated/bench'))
        run.assert_not_called()

    def test_only_dedicated_unit_restarted_and_checked(self):
        result = subprocess.CompletedProcess([], 0, '/dedicated/bench/sites\n', '')
        with patch.object(mod.Path, 'is_file', return_value=True), patch.object(mod.os, 'geteuid', return_value=0), \
             patch.object(mod.subprocess, 'run', return_value=result) as run:
            mod.restart_website_service(Path('/dedicated/bench'))
        self.assertEqual(run.call_args_list[1].args[0], ['systemctl', 'restart', mod.UNIT])
        self.assertEqual(run.call_args_list[2].args[0], ['systemctl', 'is-active', '--quiet', mod.UNIT])


class WebsiteReloadTests(unittest.TestCase):
    def test_graceful_reload_signals_only_dedicated_master(self):
        result = subprocess.CompletedProcess([], 0, '/dedicated/bench/sites\n', '')
        with patch.object(mod.Path, 'is_file', return_value=True), patch.object(mod.os, 'geteuid', return_value=0), \
             patch.object(mod.subprocess, 'run', return_value=result) as run:
            mod.reload_website_service(Path('/dedicated/bench'))
        self.assertEqual(run.call_args_list[1].args[0],
                         ['systemctl', 'kill', '--kill-whom=main', '--signal=HUP', mod.UNIT])
        self.assertFalse(any('restart' in c.args[0] for c in run.call_args_list))
