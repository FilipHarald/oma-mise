"""Migration integration tests: every invocation targets a temporary home/config."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "migration.py"
OLD = "local.mise-status"
NEW = "io.github.filipharald.oma-mise"


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.config = self.home / ".config" / "omarchy"
        self.plugins = self.config / "plugins"
        self.plugins.mkdir(parents=True)
        self.shell = self.config / "shell.json"
        self.source = self.home / "checkout"
        self.source.mkdir()
        (self.source / "sentinel").write_text("source stays here")
        self.old = self.plugins / OLD
        self.new = self.plugins / NEW

    def run_migration(self, default=False):
        args = [] if default else ["--config-dir", str(self.config)]
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args],
            env={**os.environ, "HOME": str(self.home)},
            capture_output=True, text=True,
        )

    def write_config(self, value):
        self.shell.write_text(json.dumps(value, indent=2) + "\n")
        return self.shell.read_bytes()

    def backups(self):
        return list(self.config.glob("shell.json.backup-*"))

    def test_failed_staging_write_keeps_install_and_original_config(self):
        spec = importlib.util.spec_from_file_location("migration_under_test", SCRIPT)
        assert spec is not None and spec.loader is not None
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        self.old.mkdir()
        (self.old / "data").write_text("keep")
        original = self.write_config({"id": OLD})
        with patch.object(migration.os, "fsync", side_effect=OSError("injected disk failure")):
            with self.assertRaisesRegex(OSError, "injected disk failure"):
                migration.migrate(self.config)
        self.assertEqual(self.shell.read_bytes(), original)
        self.assertEqual((self.old / "data").read_text(), "keep")
        self.assertFalse(self.new.exists())
        self.assertEqual(self.backups()[0].read_bytes(), original)
        self.assertEqual(set(self.config.iterdir()), {self.plugins, self.shell, *self.backups()})

    def test_failed_atomic_config_replace_rolls_back_install(self):
        spec = importlib.util.spec_from_file_location("migration_under_test", SCRIPT)
        assert spec is not None and spec.loader is not None
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        self.old.symlink_to(self.source, target_is_directory=True)
        original = self.write_config({"id": OLD})
        with patch.object(Path, "replace", side_effect=OSError("injected replace failure")):
            with self.assertRaisesRegex(OSError, "injected replace failure"):
                migration.migrate(self.config)
        self.assertEqual(self.shell.read_bytes(), original)
        self.assertTrue(self.old.is_symlink())
        self.assertFalse(self.new.is_symlink())
        self.assertEqual(self.backups()[0].read_bytes(), original)
        self.assertEqual(set(self.config.iterdir()), {self.plugins, self.shell, *self.backups()})

    def test_install_only_migration_does_not_reformat_config(self):
        self.old.mkdir()
        self.shell.write_text('{ "other": "keep formatting" }\n')
        original = self.shell.read_bytes()
        mtime = self.shell.stat().st_mtime_ns
        result = self.run_migration()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.new.is_dir())
        self.assertEqual(self.shell.read_bytes(), original)
        self.assertEqual(self.shell.stat().st_mtime_ns, mtime)
        self.assertEqual(self.backups()[0].read_bytes(), original)

    def test_default_home_path_and_directory_install(self):
        self.old.mkdir()
        (self.old / "data").write_text("keep")
        original = self.write_config({"id": OLD})
        self.shell.chmod(0o640)
        result = self.run_migration(default=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.old.exists())
        self.assertEqual((self.new / "data").read_text(), "keep")
        self.assertEqual(self.backups()[0].read_bytes(), original)
        self.assertEqual(self.shell.stat().st_mode & 0o777, 0o640)

    def test_relative_dangling_symlink_target_is_preserved(self):
        self.old.symlink_to("../missing-checkout")
        self.write_config({"id": OLD})
        result = self.run_migration()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(os.readlink(self.new), "../missing-checkout")

    def test_config_only_migration_and_unrelated_noop(self):
        self.write_config({"plugins": [OLD], "other": True})
        result = self.run_migration()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.shell.read_text()), {"plugins": [NEW], "other": True})
        original = self.write_config({"other": True})
        backups = self.backups()
        result = self.run_migration()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.shell.read_bytes(), original)
        self.assertEqual(self.backups(), backups)

    def test_missing_config_does_not_rename_install(self):
        self.old.symlink_to(self.source, target_is_directory=True)
        result = self.run_migration()
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.old.is_symlink())
        self.assertEqual(self.backups(), [])

    def test_symlink_config_and_non_directory_install_are_rejected(self):
        target = self.home / "external.json"
        target.write_text(json.dumps({"id": OLD}))
        self.shell.symlink_to(target)
        self.old.symlink_to(self.source, target_is_directory=True)
        result = self.run_migration()
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.old.is_symlink())
        self.assertEqual(json.loads(target.read_text()), {"id": OLD})
        self.assertEqual(self.backups(), [])
        self.shell.unlink()
        self.write_config({"id": OLD})
        self.old.unlink()
        self.old.write_text("not a plugin directory")
        result = self.run_migration()
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.old.is_file())
        self.assertEqual(self.backups(), [])

    def test_repeated_run_is_noop_including_backup_and_config_mtime(self):
        self.old.symlink_to(self.source, target_is_directory=True)
        self.write_config({"id": OLD})
        first = self.run_migration()
        self.assertEqual(first.returncode, 0, first.stderr)
        contents, mtime = self.shell.read_bytes(), self.shell.stat().st_mtime_ns
        backups = self.backups()
        result = self.run_migration()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("No migration needed", result.stdout)
        self.assertEqual(self.backups(), backups)
        self.assertEqual(self.shell.read_bytes(), contents)
        self.assertEqual(self.shell.stat().st_mtime_ns, mtime)

    def test_existing_destination_with_stale_config_is_rejected(self):
        self.new.symlink_to(self.source, target_is_directory=True)
        original = self.write_config({"id": OLD})
        result = self.run_migration()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("destination", result.stderr.lower())
        self.assertEqual(self.shell.read_bytes(), original)
        self.assertEqual(self.backups(), [])

    def test_invalid_config_fails_before_any_writes(self):
        cases = [
            "not json", "[]", "null", '{"x": NaN}',
            '{"x": 1, "x": 2}',
            json.dumps({"nested": {OLD: {"a": 1}, NEW: {"b": 2}}}),
        ]
        self.old.symlink_to(self.source, target_is_directory=True)
        for contents in cases:
            with self.subTest(contents=contents):
                self.shell.write_text(contents)
                result = self.run_migration()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.shell.read_text(), contents)
                self.assertTrue(self.old.is_symlink())
                self.assertFalse(self.new.is_symlink())
                self.assertEqual(self.backups(), [])

    def test_destination_conflicts_fail_before_any_writes(self):
        for kind in ("directory", "file", "dangling_symlink"):
            with self.subTest(kind=kind):
                self.old.symlink_to(self.source, target_is_directory=True)
                if kind == "directory":
                    self.new.mkdir()
                elif kind == "file":
                    self.new.write_text("do not overwrite")
                else:
                    self.new.symlink_to(self.home / "missing")
                original = self.write_config({"id": OLD})
                result = self.run_migration()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("destination", result.stderr.lower())
                self.assertEqual(self.shell.read_bytes(), original)
                self.assertTrue(self.old.is_symlink())
                self.assertEqual(self.backups(), [])
                if kind == "directory":
                    self.new.rmdir()
                else:
                    self.new.unlink()
                self.old.unlink()

    def test_migrates_symlink_and_all_exact_nested_references(self):
        self.old.symlink_to(self.source, target_is_directory=True)
        original = self.write_config({
            "bar": {"layout": {"right": [{"id": "omarchy.tray"}, {"id": OLD}]}},
            "plugins": ["io.github.filipharald.omacoach"],
            "settings": {OLD: {"nested": [OLD, {OLD: True}], "enabled": False}},
            "untouched": [OLD + ".suffix", "prefix:" + OLD, 4, None],
        })
        result = self.run_migration()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.old.is_symlink())
        self.assertTrue(self.new.is_symlink())
        self.assertEqual(os.readlink(self.new), str(self.source))
        self.assertEqual((self.source / "sentinel").read_text(), "source stays here")
        updated = json.loads(self.shell.read_text())
        self.assertEqual(updated["bar"]["layout"]["right"], [{"id": "omarchy.tray"}, {"id": NEW}])
        self.assertEqual(updated["plugins"], ["io.github.filipharald.omacoach"])
        self.assertEqual(updated["settings"], {NEW: {"nested": [NEW, {NEW: True}], "enabled": False}})
        self.assertEqual(updated["untouched"], [OLD + ".suffix", "prefix:" + OLD, 4, None])
        self.assertEqual(len(self.backups()), 1)
        self.assertEqual(self.backups()[0].read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
