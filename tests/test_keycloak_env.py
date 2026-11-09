"""Offline Keycloak environment preflight tests."""
import tempfile
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_keycloak_env import validate_env_file


class KeycloakEnvTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file = Path(self.tmp.name) / ".env.auth"
        self.write("KC_DB_PASSWORD=" + "a" * 32 + "\n" +
                   "KC_BOOTSTRAP_ADMIN_USERNAME=operator\n" +
                   "KC_BOOTSTRAP_ADMIN_PASSWORD=" + "b" * 32 + "\n")

    def write(self, content):
        self.file.write_text(content)
        self.file.chmod(0o600)

    def test_valid(self):
        validate_env_file(self.file)

    def test_placeholder_rejected(self):
        self.write("KC_DB_PASSWORD=REPLACE_WITH_LONG_RANDOM_DATABASE_PASSWORD\n" +
                   "KC_BOOTSTRAP_ADMIN_USERNAME=admin\n" +
                   "KC_BOOTSTRAP_ADMIN_PASSWORD=" + "b" * 32)
        with self.assertRaisesRegex(ValueError, "KC_DB_PASSWORD"):
            validate_env_file(self.file)

    def test_missing_value_rejected(self):
        self.write("KC_DB_PASSWORD=" + "a" * 32)
        with self.assertRaisesRegex(ValueError, "KC_BOOTSTRAP_ADMIN_USERNAME"):
            validate_env_file(self.file)

    def test_world_readable_rejected(self):
        self.file.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "0600"):
            validate_env_file(self.file)

    def test_symlink_rejected(self):
        link = self.file.with_name("linked")
        link.symlink_to(self.file)
        with self.assertRaisesRegex(ValueError, "symlink"):
            validate_env_file(link)


if __name__ == "__main__":
    unittest.main()
