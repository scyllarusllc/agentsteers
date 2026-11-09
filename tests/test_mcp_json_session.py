"""JSON proxy transformations must preserve production hosts and TLS settings."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/mcp_json_session.py'
spec = importlib.util.spec_from_file_location('mcp_json_session', SCRIPT)
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)


class JSONSessionTests(unittest.TestCase):
    def setUp(self):
        self.other = {'match': [{'host': ['agentsteers.com']}], 'handle': [{'handler': 'reverse_proxy', 'upstreams': [{'dial': '127.0.0.1:8010'}]}]}
        self.mcp = {'match': [{'host': [mod.HOST], 'path': ['/mcp', '/mcp/*']}], 'handle': [{'handler': 'reverse_proxy', 'upstreams': [{'dial': '127.0.0.1:8765'}]}]}
        self.maintenance = {'match': [{'host': [mod.HOST]}], 'handle': [{'handler': 'static_response', 'status_code': 503}]}
        self.source = {'admin': {'disabled': True}, 'apps': {'http': {'servers': {'srv0': {'listen': [':80'], 'routes': [self.other, self.mcp, self.maintenance]}}}, 'tls': {'certificates': {'automate': ['existing.example']}}}}

    def test_preserves_all_other_config_and_original_object(self):
        before = copy.deepcopy(self.source); result = mod.mock_candidate(self.source)
        self.assertEqual(self.source, before)
        self.assertEqual(result['admin'], before['admin']); self.assertEqual(result['apps']['tls'], before['apps']['tls'])
        routes = result['apps']['http']['servers']['srv0']['routes']
        self.assertEqual(routes[0], self.other)
        handler = routes[1]['handle'][0]
        self.assertEqual(handler['upstreams'], [{'dial': '127.0.0.1:8766'}])
        self.assertEqual(handler['headers']['request']['set'], {'Host': [mod.HOST], 'X-Forwarded-Proto': ['https']})
        self.assertEqual(routes[1]['match'][0]['path'], ['/mcp'])

    def test_unknown_existing_proxy_refused(self):
        self.mcp['handle'][0]['upstreams'][0]['dial'] = '127.0.0.1:9999'
        with self.assertRaisesRegex(RuntimeError, 'unknown'):
            mod.mock_candidate(self.source)

    def test_shared_host_match_refused(self):
        self.mcp['match'][0]['host'].append('production.example')
        with self.assertRaisesRegex(RuntimeError, 'shared'):
            mod.mock_candidate(self.source)

    def test_rejects_missing_host_and_existing_session(self):
        with self.assertRaises(RuntimeError):mod.mock_candidate({'apps': {}})
        with self.assertRaises(RuntimeError):mod.mock_candidate(mod.mock_candidate(self.source))

    def test_in_place_write_keeps_docker_bind_mount_inode(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / 'config.json'; config.write_text('old')
            inode = config.stat().st_ino
            with patch.object(mod, 'CONFIG', config), patch.object(mod, 'docker') as docker:
                mod.apply('old', 'new content')
            self.assertEqual(config.stat().st_ino, inode)
            self.assertEqual(config.read_text(), 'new content')
            docker.assert_called_once_with('restart', mod.CONTAINER)

    def test_concurrent_edit_never_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / 'config.json'; config.write_text('concurrent edit')
            with patch.object(mod, 'CONFIG', config), patch.object(mod, 'docker') as docker:
                with self.assertRaisesRegex(RuntimeError, 'concurrently'):
                    mod.apply('old', 'new')
            self.assertEqual(config.read_text(), 'concurrent edit'); docker.assert_not_called()
