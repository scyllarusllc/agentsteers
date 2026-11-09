"""Offline checks for Mock MCP credential rotation (no live server changes)."""
from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import rotate_mock_token as module


class RotateMockTokenTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / ".config" / "agentsteers"
        self.path = self.directory / "mock-mcp.token"

    def rotate(self):
        # Simulate a non-root current user; all paths still belong to the test user.
        with patch.object(module.os, "geteuid", return_value=os.getuid()):
            module.rotate_token(self.path, require_stopped=False)

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0,
                     "Ownership test requires a non-root user")
    def test_secret_changes_and_permissions(self):
        self.rotate()
        original = self.path.read_text()
        self.assertGreaterEqual(len(original.strip()), 32)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.directory.stat().st_mode), 0o700)
        self.rotate()
        self.assertNotEqual(original, self.path.read_text())
        self.assertEqual(list(self.directory.glob(".mock-mcp.rotate-*")), [])

    def test_reject_token_symlink(self):
        self.directory.mkdir(parents=True, mode=0o700)
        external = Path(self.temp.name) / "outside"
        external.write_text("old-value")
        self.path.symlink_to(external)
        with self.assertRaisesRegex(RuntimeError, "symlink"):
            self.rotate()
        self.assertEqual(external.read_text(), "old-value")

    def test_reject_insecure_existing_token(self):
        self.directory.mkdir(parents=True, mode=0o700)
        self.path.write_text("old-value")
        self.path.chmod(0o644)
        with self.assertRaisesRegex(RuntimeError, "0600"):
            self.rotate()
        self.assertEqual(self.path.read_text(), "old-value")

    def test_refuse_running_server(self):
        with patch.object(module, "assert_stopped", side_effect=RuntimeError("active")):
            with self.assertRaisesRegex(RuntimeError, "active"):
                module.rotate_token(self.path)
        self.assertFalse(self.path.exists())

    def test_refuse_listener_timeout(self):
        with patch.object(module.socket, "create_connection", side_effect=TimeoutError()):
            with self.assertRaisesRegex(RuntimeError, "Cannot verify"):
                module.assert_stopped()


if __name__ == "__main__":
    unittest.main()
