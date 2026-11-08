import importlib.util
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('bench_redis', Path(__file__).resolve().parents[1] / 'scripts/bench_redis.py')
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)


class BenchRedisTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.bench = Path(self.tmp.name)
        for name in ['sites', 'config', 'logs']:
            (self.bench / name).mkdir()
        (self.bench / 'sites/common_site_config.json').write_text(json.dumps({
            'redis_cache': 'redis://127.0.0.1:13000', 'redis_queue': 'redis://127.0.0.1:11000'}))
        for name, port in [('redis_cache', 13000), ('redis_queue', 11000)]:
            (self.bench / 'config' / (name + '.conf')).write_text(
                f'bind 127.0.0.1\nport {port}\ndir {self.bench}/config\n'
                f'pidfile {self.bench}/config/{name}.pid\naclfile {self.bench}/config/{name}.acl\n')

    def test_readonly_missing_does_not_start(self):
        with patch.object(mod, 'redis_info', return_value=None), patch.object(mod.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'not running'):
                mod.ensure_bench_redis(self.bench)
            run.assert_not_called()

    def test_conflicting_instance_refused(self):
        with patch.object(mod, 'redis_info', return_value={'config_file': '/other/redis.conf'}):
            with patch.object(mod.subprocess, 'run') as run:
                with self.assertRaisesRegex(RuntimeError, 'another instance'):
                    mod.ensure_bench_redis(self.bench, start=True)
                run.assert_not_called()

    def test_public_bind_refused_before_start(self):
        p = self.bench / 'config/redis_queue.conf'
        p.write_text(p.read_text().replace('127.0.0.1', '0.0.0.0'))
        with patch.object(mod, 'redis_info', return_value=None), patch.object(mod.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'bind/port'):
                mod.ensure_bench_redis(self.bench, start=True)
            run.assert_not_called()

    def test_starts_only_missing_managed_dependencies(self):
        with patch.object(mod, 'redis_info', side_effect=[None, None, {'ready': 1}, {'ready': 1}]), \
             patch.object(mod, 'require_owned') as owned, \
             patch.object(mod.shutil, 'which', return_value='/usr/bin/redis-server'), \
             patch.object(mod.subprocess, 'run') as run:
            mod.ensure_bench_redis(self.bench, start=True)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(owned.call_count, 2)
        for call in run.call_args_list:
            self.assertEqual(call.args[0][0], '/usr/bin/redis-server')
            self.assertIn('--protected-mode', call.args[0])
            self.assertEqual(call.kwargs['cwd'], self.bench)

    def test_existing_owned_instances_are_not_restarted(self):
        with patch.object(mod, 'redis_info', return_value={'ready': 1}), \
             patch.object(mod, 'require_owned'), patch.object(mod.subprocess, 'run') as run:
            mod.ensure_bench_redis(self.bench, start=True)
            run.assert_not_called()
