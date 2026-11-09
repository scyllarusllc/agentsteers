"""Development Bench must not inherit production data or launch with invalid code."""
import ast
import os
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

    def test_make_dev_disables_uv_before_bench_setup(self):
        with patch.dict(os.environ, {"BENCH_DISABLE_UV": "0"}):
            with patch.object(dev_environment.os, "geteuid", return_value=1000), \
                 patch.object(dev_environment, "DEV_BENCH") as path, \
                 patch.object(dev_environment, "setup") as setup, \
                 patch.object(dev_environment, "validate"):
                path.is_symlink.return_value = False
                path.exists.return_value = False
                dev_environment.ensure()
                self.assertEqual(os.environ["BENCH_DISABLE_UV"], "1")
                setup.assert_called_once()

    def test_direct_setup_disables_uv(self):
        with patch.dict(os.environ, {"BENCH_DISABLE_UV": "0"}), \
             patch.object(dev_environment.os, "geteuid", return_value=0):
            with self.assertRaisesRegex(RuntimeError, "root"):
                dev_environment.setup()
            self.assertEqual(os.environ["BENCH_DISABLE_UV"], "1")

    def test_setup_checks_yarn_before_creating_bench(self):
        # Fail closed if Yarn cannot execute; never start Bench init.
        with patch.object(dev_environment.os, "geteuid", return_value=1000), \
             patch.object(dev_environment.sys.stdin, "isatty", return_value=True), \
             patch.object(dev_environment, "DEV_BENCH") as path, \
             patch.object(dev_environment, "resolve_bench") as resolve, \
             patch.object(dev_environment, "ensure_yarn", side_effect=RuntimeError("Yarn permission denied")) as yarn, \
             patch.object(dev_environment, "bench_cli") as cli:
            path.is_symlink.return_value = False
            path.exists.return_value = False
            resolve.return_value = dev_environment.ROOT / "frappe-bench"
            with self.assertRaisesRegex(RuntimeError, "Yarn permission denied"):
                dev_environment.setup()
            yarn.assert_called_once_with()
            cli.assert_not_called()

    def test_setup_inherits_verified_yarn_path_for_bench_init(self):
        # Bench invokes yarn by name, so the preflight-selected executable
        # must remain available to its child processes.
        def prepare_yarn():
            os.environ["PATH"] = "/mock/agentsteers-yarn:" + os.environ["PATH"]
            return "/mock/agentsteers-yarn/yarn"

        def stop_at_init(args, cwd):
            self.assertEqual(args[1], "init")
            self.assertTrue(os.environ["PATH"].startswith("/mock/agentsteers-yarn:"))
            self.assertEqual(os.environ["BENCH_DISABLE_UV"], "1")
            raise RuntimeError("stopped before creating a real Bench")

        with patch.dict(os.environ, {"PATH": "/usr/bin", "BENCH_DISABLE_UV": "0"}), \
             patch.object(dev_environment.os, "geteuid", return_value=1000), \
             patch.object(dev_environment.sys.stdin, "isatty", return_value=True), \
             patch.object(dev_environment, "DEV_BENCH") as path, \
             patch.object(dev_environment, "resolve_bench") as resolve, \
             patch.object(dev_environment, "ensure_yarn", side_effect=prepare_yarn) as yarn, \
             patch.object(dev_environment, "bench_cli", return_value="/usr/bin/bench"), \
             patch.object(dev_environment, "run", side_effect=stop_at_init):
            path.is_symlink.return_value = False
            path.exists.return_value = False
            resolve.return_value = dev_environment.ROOT / "frappe-bench"
            with self.assertRaisesRegex(RuntimeError, "stopped before"):
                dev_environment.setup()
            yarn.assert_called_once_with()

    def test_no_production_data_import_commands(self):
        text = (SCRIPTS / "dev_environment.py").read_text(encoding="utf-8")
        self.assertNotIn("mariadb-dump", text)
        self.assertNotIn("mysqldump", text)
        self.assertNotIn("ENABLE LOCAL DEV SYNC", text)


if __name__ == "__main__":
    unittest.main()
