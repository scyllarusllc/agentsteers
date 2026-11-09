"""Development Bench must not inherit production data or launch with invalid code."""
import ast
from pathlib import Path
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import dev_environment


class DevEnvironmentSafetyTests(unittest.TestCase):
    def test_launchers_parse(self):
        for name in ("dev_environment.py", "run_frappe_dev.py"):
            with self.subTest(name=name):
                ast.parse((SCRIPTS / name).read_text(encoding="utf-8"))

    def test_production_sync_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "disabled"):
            dev_environment.sync()

    def test_no_production_data_import_commands(self):
        text = (SCRIPTS / "dev_environment.py").read_text(encoding="utf-8")
        self.assertNotIn("mariadb-dump", text)
        self.assertNotIn("mysqldump", text)
        self.assertNotIn("ENABLE LOCAL DEV SYNC", text)


if __name__ == "__main__":
    unittest.main()
