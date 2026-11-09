"""Offline tests for the local MCP server discovery check."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_mcp_local.py"
spec = importlib.util.spec_from_file_location("check_mcp_local", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class LocalMCPCheckTests(unittest.TestCase):
    def test_accepts_four_expected_tools(self):
        module.verify_tool_names(set(module.EXPECTED_TOOLS))

    def test_rejects_incomplete_tool_registry(self):
        with self.assertRaisesRegex(RuntimeError, "cancel_task"):
            module.verify_tool_names(set(module.EXPECTED_TOOLS) - {"cancel_task"})

    def test_rejects_missing_token_without_connecting(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(module.main(), 2)

    def test_rejects_short_token_without_connecting(self):
        with patch.dict("os.environ", {"AGENTSTEERS_DEV_TOKEN": "weak"}, clear=True):
            self.assertEqual(module.main(), 2)


if __name__ == "__main__":
    unittest.main()
