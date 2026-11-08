"""Static fail-closed checks for the prelaunch public hostname example."""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class DeploymentScaffoldTests(unittest.TestCase):
    def test_prelaunch_does_not_proxy_into_dev_mcp(self):
        text = (ROOT / "deploy" / "Caddyfile.prelaunch").read_text()
        self.assertIn("mcp.agentsteers.com {", text)
        self.assertIn('respond "AgentSteers MCP endpoint not yet enabled" 503', text)
        # No active proxy or import directives in prelaunch config.
        directives = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
        self.assertFalse(any(line.startswith(("reverse_proxy", "forward_auth", "import ")) for line in directives))

    def test_docs_warn_not_to_expose_dev_server(self):
        text = (ROOT / "deploy" / "README.md").read_text()
        self.assertIn("must NEVER be put behind the public hostname", text)
        self.assertIn("audience", text)
        self.assertIn("Voice Mode", text)


if __name__ == "__main__":
    unittest.main()
