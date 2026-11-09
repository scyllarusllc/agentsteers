"""Offline checks for guarded MCP Caddy integration (no Caddy reload)."""
import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/mcp_mock_caddy.py"
spec = importlib.util.spec_from_file_location("mcp_mock_caddy", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class MCPMockCaddyTests(unittest.TestCase):
    def setUp(self):
        self.site = (SCRIPT.parents[1] / "deploy/Caddyfile.prelaunch").read_text()
        self.replacement = (SCRIPT.parents[1] / "deploy/Caddyfile.mock-mcp").read_text()
        self.website = "agentsteers.com {\n    reverse_proxy 127.0.0.1:8010\n}\n"

    def test_replaces_only_mcp_prelaunch_block(self):
        source = self.website + "\n" + self.site
        modified = module.replace_site(source, self.replacement)
        self.assertTrue(modified.startswith(self.website))
        self.assertIn("reverse_proxy 127.0.0.1:8766", modified)
        self.assertNotIn("AgentSteers MCP endpoint not yet enabled", modified)

    def test_rejects_missing_block(self):
        with self.assertRaises(ValueError):
            module.replace_site(self.website, self.replacement)

    def test_rejects_duplicate_site_blocks(self):
        with self.assertRaises(ValueError):
            module.replace_site(self.site + "\n" + self.site, self.replacement)

    def test_refuses_unexpected_live_configuration(self):
        unknown = "mcp.agentsteers.com {\n    reverse_proxy 127.0.0.1:9999\n}\n"
        with self.assertRaises(ValueError):
            module.replace_site(unknown, self.replacement)

    def test_does_not_modify_non_mcp_sites(self):
        source = self.site + "\n" + self.website
        changed = module.replace_site(source, self.replacement)
        self.assertTrue(changed.endswith(self.website))


if __name__ == "__main__":
    unittest.main()
