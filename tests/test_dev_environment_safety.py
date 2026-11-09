"""Development Bench must not inherit production data or launch with invalid code."""
import ast
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

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

    def test_ensure_creates_missing_bench_once(self):
        with patch.object(dev_environment.os, "geteuid", return_value=1000), \
             patch.object(dev_environment, "DEV_BENCH") as path, \
             patch.object(dev_environment, "setup") as setup, \
             patch.object(dev_environment, "validate") as validate:
            path.is_symlink.return_value = False
            path.exists.return_value = False
            dev_environment.ensure()
            setup.assert_called_once_with()
            validate.assert_called_once_with()

    def test_ensure_existing_bench_does_not_reinitialize(self):
        with patch.object(dev_environment.os, "geteuid", return_value=1000), \
             patch.object(dev_environment, "DEV_BENCH") as path, \
             patch.object(dev_environment, "setup") as setup, \
             patch.object(dev_environment, "validate") as validate:
            path.is_symlink.return_value = False
            path.exists.return_value = True
            path.is_dir.return_value = True
            dev_environment.ensure()
            setup.assert_not_called()
            validate.assert_called_once_with()

    def test_ensure_refuses_symlinked_bench(self):
        with patch.object(dev_environment.os, "geteuid", return_value=1000), \
             patch.object(dev_environment, "DEV_BENCH") as path, \
             patch.object(dev_environment, "setup") as setup:
            path.is_symlink.return_value = True
            with self.assertRaisesRegex(RuntimeError, "symlinked"):
                dev_environment.ensure()
            setup.assert_not_called()

    def test_ensure_refuses_incomplete_existing_bench(self):
        with patch.object(dev_environment.os, "geteuid", return_value=1000), \
             patch.object(dev_environment, "DEV_BENCH") as path, \
             patch.object(dev_environment, "setup") as setup, \
             patch.object(dev_environment, "validate", side_effect=RuntimeError("incomplete")):
            path.is_symlink.return_value = False
            path.exists.return_value = True
            path.is_dir.return_value = True
            with self.assertRaisesRegex(RuntimeError, "incomplete"):
                dev_environment.ensure()
            setup.assert_not_called()

    def test_no_production_data_import_commands(self):
        text = (SCRIPTS / "dev_environment.py").read_text(encoding="utf-8")
        self.assertNotIn("mariadb-dump", text)
        self.assertNotIn("mysqldump", text)
        self.assertNotIn("ENABLE LOCAL DEV SYNC", text)


if __name__ == "__main__":
    unittest.main()
