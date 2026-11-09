"""Offline tests for the one-time private Frappe OAuth MCP configuration helper."""
import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import frappe_mcp_auth_config as config


class PrivateFrappeOAuthConfigTests(unittest.TestCase):
    def test_all_missing_fields_reported_together(self):
        with self.assertRaisesRegex(ValueError, "AGENTSTEERS_FRAPPE_CLIENT_ID") as cm:
            config.preflight(dict(config.DEFAULTS))
        self.assertIn("AGENTSTEERS_FRAPPE_CLIENT_SECRET", str(cm.exception))
        self.assertIn("AGENTSTEERS_FRAPPE_SUBJECTS", str(cm.exception))

    def test_private_config_loaded_with_defaults(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "frappe-oauth.env"
            path.write_text(
                "AGENTSTEERS_FRAPPE_CLIENT_ID=actual-client\n"
                "AGENTSTEERS_FRAPPE_CLIENT_SECRET=secret-value-long-enough\n"
                "AGENTSTEERS_FRAPPE_SUBJECTS=owner\n",
                encoding="utf-8")
            path.chmod(0o600)
            with patch.object(config, "CONFIG", path), patch.dict(os.environ, {}, clear=True):
                env = config.environment()
                self.assertEqual(env["AGENTSTEERS_FRAPPE_ISSUER"], "https://agentsteers.com")
                self.assertEqual(env["AGENTSTEERS_FRAPPE_REPOS"], "scyllarusllc/agentsteers")
                config.preflight(env)

    def test_start_skips_setup_when_valid(self):
        complete = dict(config.DEFAULTS, **{
            "AGENTSTEERS_FRAPPE_CLIENT_ID": "real-client",
            "AGENTSTEERS_FRAPPE_CLIENT_SECRET": "long-valid-client-secret",
            "AGENTSTEERS_FRAPPE_SUBJECTS": "owner",
        })
        with patch.object(config, "environment", return_value=complete), \
             patch.object(config, "setup") as setup:
            self.assertEqual(config.ensure_ready_for_start(), complete)
            setup.assert_not_called()

    def test_start_sets_up_missing_config_and_rechecks(self):
        partial = dict(config.DEFAULTS)
        complete = dict(partial, **{
            "AGENTSTEERS_FRAPPE_CLIENT_ID": "real-client",
            "AGENTSTEERS_FRAPPE_CLIENT_SECRET": "long-valid-client-secret",
            "AGENTSTEERS_FRAPPE_SUBJECTS": "owner",
        })
        with patch.object(config, "environment", side_effect=[partial, complete]), \
             patch.object(config.sys.stdin, "isatty", return_value=True), \
             patch.object(config, "setup") as setup:
            self.assertEqual(config.ensure_ready_for_start(), complete)
            setup.assert_called_once_with()

    def test_start_without_tty_does_not_prompt_or_launch(self):
        with patch.object(config, "environment", return_value=dict(config.DEFAULTS)), \
             patch.object(config.sys.stdin, "isatty", return_value=False), \
             patch.object(config, "setup") as setup:
            with self.assertRaisesRegex(ValueError, "interactive terminal"):
                config.ensure_ready_for_start()
            setup.assert_not_called()

    def test_invalid_existing_config_fails_without_overwriting(self):
        invalid = dict(config.DEFAULTS, **{
            "AGENTSTEERS_FRAPPE_CLIENT_ID": "real-client",
            "AGENTSTEERS_FRAPPE_CLIENT_SECRET": "short",
            "AGENTSTEERS_FRAPPE_SUBJECTS": "owner",
        })
        with patch.object(config, "environment", return_value=invalid), \
             patch.object(config, "setup") as setup:
            with self.assertRaisesRegex(ValueError, "Client secret too short"):
                config.ensure_ready_for_start()
            setup.assert_not_called()

    def test_insecure_file_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "frappe-oauth.env"
            path.write_text("AGENTSTEERS_FRAPPE_CLIENT_ID=abc\n")
            path.chmod(0o644)
            with patch.object(config, "CONFIG", path):
                with self.assertRaisesRegex(ValueError, "mode 600"):
                    config.read_private_config()

    def test_environment_override(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "frappe-oauth.env"
            with patch.object(config, "CONFIG", path), patch.dict(os.environ, {
                "AGENTSTEERS_FRAPPE_ISSUER": "https://auth.example.test"
            }, clear=True):
                self.assertEqual(config.environment()["AGENTSTEERS_FRAPPE_ISSUER"],
                                 "https://auth.example.test")


if __name__ == "__main__":
    unittest.main()
