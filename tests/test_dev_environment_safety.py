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
    def setUp(self):
        p = patch.object(dev_environment, 'prepare_dev_app')
        self.prepare_app = p.start()
        self.addCleanup(p.stop)

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

    def test_existing_bench_without_site_resumes_setup(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            bench = Path(folder) / "dev"
            bench.mkdir()
            with patch.object(dev_environment.os, "geteuid", return_value=1000), \
                 patch.object(dev_environment, "DEV_BENCH", bench), \
                 patch.object(dev_environment, "setup") as setup, \
                 patch.object(dev_environment, "validate") as validate:
                dev_environment.ensure()
                setup.assert_called_once_with()
                validate.assert_called_once_with()

    def test_resuming_valid_empty_bench_never_runs_bench_init(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); bench = root / "dev"; prod = root / "prod"
            for name in ("apps/frappe", "env/bin", "sites"):
                (bench / name).mkdir(parents=True)
            (bench / "env/bin/python").touch()
            (bench / "sites/common_site_config.json").write_text("{}")
            with patch.object(dev_environment.os, "geteuid", return_value=1000), \
                 patch.object(dev_environment.sys.stdin, "isatty", return_value=True), \
                 patch.object(dev_environment, "DEV_BENCH", bench), \
                 patch.object(dev_environment, "PROD_BENCH", prod), \
                 patch.object(dev_environment, "resolve_bench", return_value=prod), \
                 patch.object(dev_environment, "ensure_yarn"), \
                 patch.object(dev_environment, "bench_cli", return_value="/managed/bench"), \
                 patch.object(dev_environment, "ensure_bench_redis"), \
                 patch.object(dev_environment, "config", return_value={"db_name": "production"}), \
                 patch.object(dev_environment, "isolate_site"), \
                 patch.object(dev_environment, "validate"), \
                 patch.object(dev_environment, "run") as run, \
                 patch("create_dev_site.create_dev_site") as create:
                dev_environment.setup()
                create.assert_called_once_with(bench, dev_environment.ROOT, {"db_name": "production"})
                self.assertFalse(any("init" in c.args[0] for c in run.call_args_list))
                self.assertTrue((bench / "apps/frappe").is_dir())

    def test_dev_bench_is_git_ignored(self):
        self.assertIn("/frappe-dev-bench/", (SCRIPTS.parent / ".gitignore").read_text())

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

    def test_bench_cli_refuses_non_executable_project_managed_cli(self):
        with patch.object(dev_environment, "ROOT") as root, \
             patch.object(dev_environment.os.path, "isfile", return_value=False):
            # The .bench-cli-venv executable is checked first.
            path = root / ".bench-cli-venv/bin/bench"
            path.is_file.return_value = True
            with patch.object(dev_environment.os, "access", return_value=False):
                with self.assertRaisesRegex(RuntimeError, "not executable"):
                    dev_environment.bench_cli(root / "frappe-bench")

    def test_diagnostics_do_not_modify_permissions(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(dev_environment, "ROOT", Path(directory)), \
             patch.object(dev_environment, "DEV_BENCH", Path(directory) / "dev"), \
             patch.object(dev_environment, "PROD_BENCH", Path(directory) / "prod"), \
             patch.object(dev_environment.shutil, "which", return_value=None), \
             patch.object(dev_environment.subprocess, "run") as cmd:
            dev_environment.diagnose_permissions()
            cmd.assert_not_called()

    def test_no_production_data_import_commands(self):
        text = (SCRIPTS / "dev_environment.py").read_text(encoding="utf-8")
        self.assertNotIn("mariadb-dump", text)
        self.assertNotIn("mysqldump", text)
        self.assertNotIn("ENABLE LOCAL DEV SYNC", text)


if __name__ == "__main__":
    unittest.main()
