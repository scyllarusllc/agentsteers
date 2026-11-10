"""Verify the public command naming cannot silently enable legacy auth."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MCPCommandSplitTests(unittest.TestCase):
    def test_make_targets_are_separate(self):
        source = (ROOT / "Makefile").read_text()
        self.assertIn("mcp-mock:\n\t@$(PYTHON) scripts/run_mcp_mock_session.py", source)
        self.assertIn("mcp: mcp-bridge-test\n\t@PYTHONPATH=src $(PYTHON) scripts/run_mcp_oauth_session.py", source)

    def test_oauth_startup_fails_closed(self):
        from agentsteers.oauth_bridge_core import RESOURCE
        from scripts.run_mcp_oauth_session import readiness, main
        ready, pending = readiness()
        self.assertFalse(ready)
        self.assertIn("MCP resource-server validation for Bridge-issued tokens", pending)
        self.assertEqual(main(), 1)
        self.assertEqual(RESOURCE, "https://mcp.agentsteers.com/mcp")

    def test_mock_session_does_not_launch_from_new_entrypoint(self):
        source = (ROOT / "scripts" / "run_mcp_oauth_session.py").read_text()
        self.assertNotIn("subprocess.Popen", source)
        self.assertNotIn("run_mcp_mock_session", source)
        self.assertNotIn("os.exec", source)


if __name__ == "__main__":
    unittest.main()
