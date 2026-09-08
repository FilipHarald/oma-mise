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
        self.temp = tempfile.TemporaryDirectory(dir=Path.home())
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
            [sys.executable, "-I", "-S", "-B", str(SCRIPT), *args],
            env={**os.environ, "HOME": str(self.home)},
            capture_output=True, text=True, timeout=5,
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
        with patch.object(migration.os, "replace", side_effect=OSError("injected replace failure")):
            with self.assertRaisesRegex(OSError, "injected replace failure"):
                migration.migrate(self.config)
        self.assertEqual(self.shell.read_bytes(), original)
        self.assertTrue(self.old.is_symlink())
        self.assertFalse(self.new.is_symlink())
        self.assertEqual(self.backups()[0].read_bytes(), original)
        self.assertEqual(set(self.config.iterdir()), {self.plugins, self.shell, *self.backups()})

    def load_migration(self):
        spec = importlib.util.spec_from_file_location("migration_security_test", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_backup_changed_during_publication_is_not_reported_verified(self):
        migration = self.load_migration()
        self.write_config({"id": OLD})
        real_replace = migration.os.replace

        def mutate_backup(source, destination, **kwargs):
            backup = self.backups()[0]
            before = backup.stat()
            raw = backup.read_bytes()
            backup.write_bytes(raw.replace(b"local", b"other", 1))
            os.utime(backup, ns=(before.st_atime_ns, before.st_mtime_ns))
            return real_replace(source, destination, **kwargs)

        with patch.object(migration.os, "replace", side_effect=mutate_backup):
            with self.assertRaisesRegex(OSError, "Config published but verification"):
                migration.migrate(self.config)

    def test_hardlinked_input_refused_before_backup(self):
        self.write_config({"id": OLD})
        os.link(self.shell, self.home / "alias")
        result = self.run_migration()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.backups(), [])

    def test_backup_is_written_through_created_descriptor(self):
        migration = self.load_migration()
        original = self.write_config({"id": OLD})
        victim = self.home / "victim"
        victim.write_text("KEEP")
        real_open = migration.os.open
        def swap_after_create(name, flags, *args, **kwargs):
            fd = real_open(name, flags, *args, **kwargs)
            if str(name).startswith("shell.json.backup-"):
                os.unlink(name, dir_fd=kwargs["dir_fd"])
                os.symlink(victim, name, dir_fd=kwargs["dir_fd"])
            return fd
        with patch.object(migration.os, "open", side_effect=swap_after_create):
            with self.assertRaises((ValueError, OSError)):
                migration.migrate(self.config)
        self.assertEqual(victim.read_text(), "KEEP")
        self.assertEqual(self.shell.read_bytes(), original)

    def test_depth_and_cardinality_rejected_before_writes(self):
        migration = self.load_migration()
        for raw in ('{"id":"' + OLD + '","x":' + '[' * 33 + '0' + ']' * 33 + '}',
                    json.dumps({"id": OLD, "items": [0] * 10001})):
            with self.subTest(raw=raw[:60]):
                self.shell.write_text(raw)
                with self.assertRaises(ValueError):
                    migration.migrate(self.config)
                self.assertEqual(self.backups(), [])

    def test_parent_traversal_and_double_slash_root_refused(self):
        migration = self.load_migration()
        self.write_config({"id": OLD})
        for path in (self.config / "plugins" / "..", Path("/" + str(self.config))):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    migration.migrate(path)
                self.assertEqual(self.backups(), [])

    def test_staged_inode_mutation_is_detected_before_publication(self):
        migration = self.load_migration()
        original = self.write_config({"id": OLD})
        real_validate = migration.revalidate_chain
        def mutate_stage(chain):
            for stage in self.config.glob(".shell.json.migration-*"):
                stage.write_text('{"attacker":true}')
            return real_validate(chain)
        with patch.object(migration, "revalidate_chain", side_effect=mutate_stage):
            with self.assertRaises(ValueError):
                migration.migrate(self.config)
        self.assertEqual(self.shell.read_bytes(), original)

    def test_replace_boundary_stage_mutation_reports_manual_recovery(self):
        migration = self.load_migration()
        real_replace = migration.os.replace
        for attack in ("content", "mode"):
            with self.subTest(attack=attack):
                original = self.write_config({"id": OLD})
                self.shell.chmod(0o600)
                def mutate(src, dst, **kwargs):
                    stage = self.config / src
                    if attack == "content":
                        # Same length and restored mtime: retained bytes matter.
                        before = stage.stat()
                        stage.write_bytes(stage.read_bytes().replace(b"oma-mise", b"bad-mise"))
                        os.utime(stage, ns=(before.st_atime_ns, before.st_mtime_ns))
                    else:
                        stage.chmod(0o666)
                    return real_replace(src, dst, **kwargs)
                with patch.object(migration.os, "replace", side_effect=mutate):
                    with self.assertRaisesRegex(OSError, "published.*verification.*backup:"):
                        migration.migrate(self.config)
                self.assertTrue(all(p.read_bytes() == original for p in self.backups()))
                if attack == "content":
                    self.assertIn(b"bad-mise", self.shell.read_bytes())
                else:
                    self.assertEqual(self.shell.stat().st_mode & 0o777, 0o666)

    def delayed_installation_mutation(self, attack, install_only=False):
        migration = self.load_migration()
        original = self.write_config({"other": True} if install_only else {"id": OLD})
        self.old.mkdir()
        saved = self.plugins / "saved-install"
        def mutate():
            if attack == "replacement":
                self.new.rename(saved)
                self.new.symlink_to("attacker-target")
            elif attack == "mode":
                self.new.chmod(0o777)
            else:
                self.old.symlink_to("concurrent-install")
        if install_only:
            real_call = migration.os.fsync
            changed = False
            def sync_hook(fd):
                nonlocal changed
                if self.new.exists() and not changed:
                    changed = True
                    mutate()
                return real_call(fd)
            target = "fsync"
            hook = sync_hook
        else:
            real_call = migration.os.replace
            def replace_hook(*args, **kwargs):
                mutate()
                return real_call(*args, **kwargs)
            target = "replace"
            hook = replace_hook
        with patch.object(migration.os, target, side_effect=hook):
            message = "rollback failed.*backup:" if install_only else "published.*verification.*backup:"
            with self.assertRaisesRegex(OSError, message):
                migration.migrate(self.config)
        self.assertEqual(self.backups()[0].read_bytes(), original)
        if install_only:
            self.assertEqual(self.shell.read_bytes(), original)
        else:
            self.assertEqual(json.loads(self.shell.read_text()), {"id": NEW})
        if attack == "replacement":
            self.assertEqual(os.readlink(self.new), "attacker-target")
            self.assertTrue(saved.is_dir())
        elif attack == "mode":
            self.assertEqual(self.new.stat().st_mode & 0o777, 0o777)
        else:
            self.assertEqual(os.readlink(self.old), "concurrent-install")

    def test_delayed_installation_replacement_after_rename(self):
        self.delayed_installation_mutation("replacement")

    def test_delayed_installation_mode_change_after_rename(self):
        self.delayed_installation_mutation("mode")

    def test_delayed_old_installation_recreation_after_rename(self):
        self.delayed_installation_mutation("old")

    def test_install_only_delayed_installation_replacement(self):
        self.delayed_installation_mutation("replacement", install_only=True)

    def test_install_only_delayed_installation_mode_change(self):
        self.delayed_installation_mutation("mode", install_only=True)

    def test_install_only_delayed_old_installation_recreation(self):
        self.delayed_installation_mutation("old", install_only=True)

    def test_noop_still_revalidates_source_identity(self):
        migration = self.load_migration()
        self.write_config({"other": True})
        real_parse = migration.bounded_json
        def replace_after_parse(raw):
            value = real_parse(raw)
            self.shell.unlink()
            self.shell.symlink_to(self.source / "sentinel")
            return value
        with patch.object(migration, "bounded_json", side_effect=replace_after_parse):
            with self.assertRaises(ValueError):
                migration.migrate(self.config)
        self.assertEqual(self.backups(), [])

    def test_nonfinite_number_rejected_even_for_noop(self):
        self.shell.write_text('{"x": 1e999}')
        result = self.run_migration()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.backups(), [])

    def test_fifo_oversize_and_writable_input_fail_before_writes(self):
        os.mkfifo(self.shell)
        result = self.run_migration()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.backups(), [])
        self.shell.unlink()
        with self.shell.open("wb") as stream:
            stream.truncate(1024 * 1024 + 1)
        result = self.run_migration()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.backups(), [])
        self.write_config({"id": OLD})
        self.shell.chmod(0o666)
        result = self.run_migration()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.backups(), [])

    def test_symlink_and_writable_parent_chains_refused(self):
        self.write_config({"id": OLD})
        moved = self.home / "real-config"
        self.config.rename(moved)
        self.config.symlink_to(moved, target_is_directory=True)
        result = self.run_migration()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(moved.glob("shell.json.backup-*")), [])
        self.config.unlink()
        moved.rename(self.config)
        self.home.chmod(0o777)
        try:
            result = self.run_migration()
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(self.backups(), [])
        finally:
            self.home.chmod(0o700)
        real_plugins = self.home / "real-plugins"
        self.plugins.rename(real_plugins)
        self.plugins.symlink_to(real_plugins, target_is_directory=True)
        result = self.run_migration()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.backups(), [])

    def test_read_open_swap_does_not_read_private_target(self):
        migration = self.load_migration()
        self.write_config({"id": OLD})
        private = self.home / "private.json"
        private.write_text(json.dumps({"id": OLD, "private": "SECRET"}))
        real_open = migration.os.open
        def swap_before_open(name, flags, *args, **kwargs):
            if name == "shell.json":
                self.shell.unlink()
                self.shell.symlink_to(private)
            return real_open(name, flags, *args, **kwargs)
        with patch.object(migration.os, "open", side_effect=swap_before_open):
            with self.assertRaises(OSError):
                migration.migrate(self.config)
        self.assertEqual(self.backups(), [])
        self.assertIn("SECRET", private.read_text())

    def test_stage_swap_cannot_chmod_victim_or_publish_symlink(self):
        migration = self.load_migration()
        original = self.write_config({"id": OLD})
        self.shell.chmod(0o644)
        victim = self.home / "victim"
        victim.write_text("KEEP")
        victim.chmod(0o600)
        real_chmod = migration.os.fchmod
        def swap_before_fchmod(fd, mode):
            for stage in self.config.glob(".shell.json.migration-*"):
                stage.unlink()
                stage.symlink_to(victim)
            return real_chmod(fd, mode)
        with patch.object(migration.os, "fchmod", side_effect=swap_before_fchmod):
            with self.assertRaises((OSError, ValueError)):
                migration.migrate(self.config)
        self.assertEqual(victim.read_text(), "KEEP")
        self.assertEqual(victim.stat().st_mode & 0o777, 0o600)
        self.assertFalse(self.shell.is_symlink())
        self.assertEqual(self.shell.read_bytes(), original)

    def test_destination_creation_in_rename_window_never_overwritten(self):
        migration = self.load_migration()
        original = self.write_config({"id": OLD})
        self.old.symlink_to(self.source)
        real_rename = migration.rename_noreplace
        def collide(dirfd, src, dst):
            self.new.symlink_to("attacker-target")
            return real_rename(dirfd, src, dst)
        with patch.object(migration, "rename_noreplace", side_effect=collide):
            with self.assertRaises(FileExistsError):
                migration.migrate(self.config)
        self.assertEqual(os.readlink(self.new), "attacker-target")
        self.assertTrue(self.old.is_symlink())
        self.assertEqual(self.shell.read_bytes(), original)

    def test_directory_swap_after_read_refuses_before_writes(self):
        migration = self.load_migration()
        original = self.write_config({"id": OLD})
        moved = self.home / "detached"
        real_read = migration.os.read
        def swap_after_read(fd, count):
            data = real_read(fd, count)
            self.config.rename(moved)
            self.config.symlink_to(self.source)
            return data
        with patch.object(migration.os, "read", side_effect=swap_after_read):
            with self.assertRaises(ValueError):
                migration.migrate(self.config)
        self.assertEqual((moved / "shell.json").read_bytes(), original)
        self.assertEqual(list(moved.glob("shell.json.backup-*")), [])
        self.assertEqual(list(self.source.iterdir()), [self.source / "sentinel"])

    def test_concurrent_writer_revalidation_preserves_its_data(self):
        migration = self.load_migration()
        self.write_config({"id": OLD})
        self.old.mkdir()
        real_fsync = migration.os.fsync
        changed = False
        def change_during_staging(fd):
            nonlocal changed
            if not changed:
                changed = True
                self.shell.write_text('{"concurrent":true}')
            return real_fsync(fd)
        with patch.object(migration.os, "fsync", side_effect=change_during_staging):
            with self.assertRaises(ValueError):
                migration.migrate(self.config)
        self.assertEqual(self.shell.read_text(), '{"concurrent":true}')
        self.assertTrue(self.old.is_dir())

    def test_directory_lock_blocks_second_migrator_without_writes(self):
        import fcntl
        self.write_config({"id": OLD})
        fd = os.open(self.config, os.O_RDONLY | os.O_DIRECTORY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.run_migration()
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(self.backups(), [])
        finally:
            os.close(fd)

    def test_publication_is_atomic_shell_mode_preserved_backup_private(self):
        migration = self.load_migration()
        original = self.write_config({"id": OLD})
        self.shell.chmod(0o640)
        real_replace = migration.os.replace
        observations = []
        with self.shell.open("rb") as held_original:
            def observe(src, dst, **kwargs):
                observations.append(self.shell.read_bytes())
                result = real_replace(src, dst, **kwargs)
                observations.append(json.loads(self.shell.read_text()))
                return result
            with patch.object(migration.os, "replace", side_effect=observe):
                backup = migration.migrate(self.config)
            self.assertEqual(held_original.read(), original)
        self.assertEqual(observations, [original, {"id": NEW}])
        self.assertEqual(backup.read_bytes(), original)
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.shell.stat().st_mode & 0o777, 0o640)

    def test_last_instant_stage_swap_reports_postpublication_failure(self):
        migration = self.load_migration()
        original = self.write_config({"id": OLD})
        self.old.symlink_to(self.source)
        victim = self.home / "victim"
        victim.write_text("KEEP")
        victim.chmod(0o600)
        real_replace = migration.os.replace
        def swap_at_syscall(src, dst, **kwargs):
            os.unlink(src, dir_fd=kwargs["src_dir_fd"])
            os.symlink(victim, src, dir_fd=kwargs["src_dir_fd"])
            return real_replace(src, dst, **kwargs)
        with patch.object(migration.os, "replace", side_effect=swap_at_syscall):
            with self.assertRaisesRegex(OSError, "published.*verification"):
                migration.migrate(self.config)
        self.assertEqual(victim.read_text(), "KEEP")
        self.assertEqual(victim.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.backups()[0].read_bytes(), original)
        self.assertTrue(self.new.is_symlink())
        self.assertTrue(self.shell.is_symlink())

    def test_rollback_refuses_concurrently_created_old_destination(self):
        migration = self.load_migration()
        original = self.write_config({"id": OLD})
        self.old.symlink_to(self.source)
        def fail_with_collision(*args, **kwargs):
            self.old.symlink_to("concurrent-install")
            raise OSError("replace failed")
        with patch.object(migration.os, "replace", side_effect=fail_with_collision):
            with self.assertRaisesRegex(OSError, "rollback failed.*backup:"):
                migration.migrate(self.config)
        self.assertEqual(os.readlink(self.old), "concurrent-install")
        self.assertEqual(os.readlink(self.new), str(self.source))
        self.assertEqual(self.shell.read_bytes(), original)

    def test_postpublication_fsync_failure_does_not_rollback_only_install(self):
        migration = self.load_migration()
        self.write_config({"id": OLD})
        self.old.mkdir()
        real_fsync = migration.os.fsync
        def fail_after_publish(fd):
            if json.loads(self.shell.read_text())["id"] == NEW:
                raise OSError("durability failure")
            return real_fsync(fd)
        with patch.object(migration.os, "fsync", side_effect=fail_after_publish):
            with self.assertRaisesRegex(OSError, "published.*durability failed"):
                migration.migrate(self.config)
        self.assertEqual(json.loads(self.shell.read_text())["id"], NEW)
        self.assertTrue(self.new.is_dir())
        self.assertFalse(self.old.exists())

    def test_read_bound_catches_growth_and_uses_single_read(self):
        migration = self.load_migration()
        self.write_config({"id": OLD})
        real_read = migration.os.read
        reads = []
        def grow_at_read(fd, count):
            reads.append(count)
            with self.shell.open("ab") as stream:
                stream.truncate(migration.MAX_BYTES + 100)
            return real_read(fd, count)
        with patch.object(migration.os, "read", side_effect=grow_at_read):
            with self.assertRaises(ValueError):
                migration.migrate(self.config)
        self.assertEqual(reads, [migration.MAX_BYTES + 1])
        self.assertEqual(self.backups(), [])

    def test_bounds_ignore_delimiters_inside_escaped_strings(self):
        value = {"id": OLD, "text": ('\\\"[]{}:,\\' * 2000)}
        self.write_config(value)
        result = self.run_migration()
        self.assertEqual(result.returncode, 0, result.stderr)
        value["id"] = NEW
        self.assertEqual(json.loads(self.shell.read_text()), value)

    def test_staging_write_failure_cleans_owned_stage(self):
        migration = self.load_migration()
        original = self.write_config({"id": OLD})
        self.old.mkdir()
        real_write = migration.os.write
        def fail_stage(fd, data):
            if list(self.config.glob(".shell.json.migration-*")):
                raise OSError("staging write failed")
            return real_write(fd, data)
        with patch.object(migration.os, "write", side_effect=fail_stage):
            with self.assertRaisesRegex(OSError, "staging write failed"):
                migration.migrate(self.config)
        self.assertEqual(self.shell.read_bytes(), original)
        self.assertTrue(self.old.is_dir())
        self.assertEqual(list(self.config.glob(".shell.json.migration-*")), [])
        self.assertEqual(self.backups()[0].read_bytes(), original)

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
