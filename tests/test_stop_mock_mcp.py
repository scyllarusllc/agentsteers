"""Port cleanup must stop only a verified mock master and await route restoration."""
import importlib.util
import os
from pathlib import Path
import signal
import sys
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('stop_mock_mcp', SCRIPTS / 'stop_mock_mcp.py')
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)


class StopMockTests(unittest.TestCase):
    def test_unused_port_does_not_signal_anything(self):
        with patch.object(mod, 'listeners', return_value=set()), patch.object(mod, 'signal_verified') as send:
            mod.stop_previous_mock()
        send.assert_not_called()

    def test_same_owner_master_and_worker_stop_only_master(self):
        identities = {101: ('master-start', 99), 102: ('worker-start', 101)}
        with patch.object(mod, 'listeners', side_effect=[{'inode'}, {'inode'}, set(), set()]), \
             patch.object(mod, 'matching_pids', return_value={'inode': {101, 102}}), \
             patch.object(mod, 'identity', side_effect=identities.get), \
             patch.object(mod, 'session_parent', return_value=None), \
             patch.object(mod, 'signal_verified') as send:
            mod.stop_previous_mock()
        send.assert_called_once_with(101, identities[101], signal.SIGTERM)

    def test_other_application_or_other_owner_never_signaled(self):
        with patch.object(mod, 'listeners', return_value={'inode'}), \
             patch.object(mod, 'matching_pids', return_value={'inode': {101}}), \
             patch.object(mod, 'identity', return_value=None), patch.object(mod, 'signal_verified') as send:
            with self.assertRaisesRegex(RuntimeError, 'not this user'):
                mod.stop_previous_mock()
        send.assert_not_called()

    def test_unidentified_owner_never_signaled(self):
        with patch.object(mod, 'listeners', return_value={'inode'}), \
             patch.object(mod, 'matching_pids', return_value={'inode': set()}), patch.object(mod, 'signal_verified') as send:
            with self.assertRaisesRegex(RuntimeError, 'unidentified'):
                mod.stop_previous_mock()
        send.assert_not_called()

    def test_new_session_waits_for_old_session_to_restore_caddy(self):
        with patch.object(mod, 'listeners', side_effect=[{'inode'}, {'inode'}, set(), set()]), \
             patch.object(mod, 'matching_pids', return_value={'inode': {101}}), \
             patch.object(mod, 'identity', return_value=('start', 99)), \
             patch.object(mod, 'session_parent', side_effect=['parent-start', 'parent-start', None]) as parent, \
             patch.object(mod, 'signal_verified'), patch.object(mod.time, 'sleep') as sleep:
            mod.stop_previous_mock()
        self.assertEqual(parent.call_count, 3); sleep.assert_called_once_with(.1)

    def test_changed_identity_cannot_be_signaled(self):
        with patch.object(mod.os, 'pidfd_open', return_value=12), patch.object(mod.os, 'close'), \
             patch.object(mod, 'identity', return_value=('new-process', 99)), \
             patch.object(mod.signal, 'pidfd_send_signal') as send:
            with self.assertRaisesRegex(RuntimeError, 'identity changed'):
                mod.signal_verified(101, ('old-process', 99), signal.SIGTERM)
        send.assert_not_called()

    def test_current_python_test_process_is_not_a_mock(self):
        self.assertIsNone(mod.identity(os.getpid()))
