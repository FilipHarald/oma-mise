#!/usr/bin/env python3
"""Migrate the oma-mise plugin ID without relocating its source checkout."""
import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile

OLD_ID = "local.mise-status"
NEW_ID = "io.github.filipharald.oma-mise"


def replace_ids(value):
    """Replace entire ID values and object keys, never substrings."""
    if isinstance(value, dict):
        if OLD_ID in value and NEW_ID in value:
            raise ValueError("Config key collision: both old and new plugin IDs exist")
        return {NEW_ID if key == OLD_ID else key: replace_ids(item)
                for key, item in value.items()}
    if isinstance(value, list):
        return [replace_ids(item) for item in value]
    return NEW_ID if value == OLD_ID else value


def unique_object(pairs):
    """Reject duplicate keys rather than silently discarding settings."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate config key: {key}")
        result[key] = value
    return result


def invalid_constant(value):
    raise ValueError(f"Invalid JSON number: {value}")


def migrate(config_dir):
    shell = config_dir / "shell.json"
    if shell.is_symlink() or not shell.is_file():
        raise ValueError("shell.json must be an existing regular file, not a symlink")
    original = json.loads(shell.read_text(encoding="utf-8"),
                          object_pairs_hook=unique_object, parse_constant=invalid_constant)
    if not isinstance(original, dict):
        raise ValueError("shell.json must contain a JSON object")
    updated = replace_ids(original)
    old = config_dir / "plugins" / OLD_ID
    new = config_dir / "plugins" / NEW_ID
    if old.exists() and not (old.is_dir() or old.is_symlink()):
        raise ValueError("Old plugin installation must be a directory or symlink")
    if not (old.exists() or old.is_symlink()) and updated == original:
        return None
    if new.exists() or new.is_symlink():
        raise ValueError(f"Migration destination already exists: {new}")
    # Serialize before any writes; reject non-finite numbers and encoding errors.
    payload = (json.dumps(updated, indent=2, ensure_ascii=False, allow_nan=False)
               + "\n").encode("utf-8")
    with tempfile.NamedTemporaryFile(prefix="shell.json.backup-", dir=config_dir, delete=False) as backup:
        backup_path = Path(backup.name)
    shutil.copy2(shell, backup_path)
    staged = None
    renamed = False
    try:
        if updated != original:
            with tempfile.NamedTemporaryFile(prefix=".shell.json.migration-", dir=config_dir,
                                             delete=False) as pending:
                staged = Path(pending.name)
                pending.write(payload)
                pending.flush()
                os.fsync(pending.fileno())
            shutil.copymode(shell, staged)
        if old.exists() or old.is_symlink():
            old.rename(new)  # Rename the link itself, never resolve or move its target.
            renamed = True
        if staged is not None:
            staged.replace(shell)  # Same-directory atomic replacement.
    except OSError:
        if renamed:
            new.rename(old)
        raise
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)
    return backup_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", type=Path, default=Path.home() / ".config" / "omarchy",
                        help="Omarchy config directory (default: ~/.config/omarchy)")
    args = parser.parse_args()
    try:
        backup = migrate(args.config_dir)
    except (OSError, ValueError, RecursionError) as error:
        parser.exit(1, f"Migration failed: {error}\n")
    if backup is None:
        print("No migration needed.")
    else:
        print(f"Migrated {OLD_ID} to {NEW_ID}. Backup: {backup}")


if __name__ == "__main__":
    main()
