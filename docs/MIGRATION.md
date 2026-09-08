# Migrate the plugin ID

The plugin and its IPC target are now `io.github.filipharald.oma-mise`, replacing
`local.mise-status`. The source checkout stays wherever you already keep it.
This migration does not rename the repository or move a symlink's target.

## Run once for an existing installation

Use Python 3; no third-party packages are needed. Close/stop the shell using your
normal session controls before migrating, and do not run other configuration
writers or another migration concurrently. The two paths cannot be updated as
one filesystem transaction.

From the existing **source checkout** (not the installed symlink):

```sh
python3 migration.py
```

By default the script uses `Path.home() / ".config" / "omarchy"`, regardless of
where the checkout lives. For a different Omarchy configuration directory:

```sh
python3 /path/to/oma-mise/migration.py --config-dir /path/to/omarchy-config
```

Do not use `sudo`: run as the owner of the configuration. The script **does not
restart or launch the shell**. After it succeeds, start/reload the shell yourself
using your normal session controls, then verify discovery and the popup:

```sh
omarchy plugin list
omarchy-shell io.github.filipharald.oma-mise open
```

Update any personal scripts using the old IPC target to the new ID. The migrator
only edits the selected Omarchy installation/configuration, not external scripts.

## What changes

- Renames `plugins/local.mise-status` to
  `plugins/io.github.filipharald.oma-mise` inside the selected config directory.
  Directories are renamed intact. Symlinks are renamed without dereferencing;
  absolute, relative, and dangling targets are preserved verbatim.
- Replaces every **exact** old-ID string value and dictionary key recursively in
  `shell.json`, including bar layout, plugin lists, disabled/enabled settings,
  and nested per-plugin options. Substrings are not changed.
- Keeps bar ordering, other plugins (including omacoach), and unrelated settings.
  It does not insert this plugin into a list where it was previously absent.
- Creates a uniquely named `shell.json.backup-*` with the original bytes and file
  metadata **before** modifying the installation or configuration. Its path is
  printed on success. Backups are not overwritten on later runs.
- Stages changed JSON in a sibling temporary file, preserves permission bits,
  flushes it to disk, then atomically replaces `shell.json`. JSON indentation may
  change. If only the installation name changes, `shell.json` is not rewritten.

A successful repeated run prints `No migration needed.` without writing a new
backup or touching the configuration. Configuration-only migration is supported
when neither installation path exists.

## Refusals and recovery

Preflight rejects missing/non-regular/symlinked `shell.json`, invalid JSON,
non-object top-level JSON, duplicate dictionary keys, and old/new ID dictionary
key collisions. It refuses an existing destination (even a dangling symlink)
when any migration remains to be done. These failures happen before backup or
other writes. An already-migrated destination is accepted only when the old
installation is absent and the configuration needs no changes.

If staging fails, the original config and installation stay intact. If atomic
config replacement fails after the plugin rename, the script attempts to rename
the installation back and leaves the original config intact. Temporary staging
files are cleaned up; the backup is retained. Filesystem failure during rollback,
power loss, or forced termination between the two updates may require manual
recovery. This is not a concurrent-writer lock or a cross-file transaction.

For manual recovery, keep the shell stopped, inspect the reported error and the
backup, and restore the chosen `shell.json.backup-*` to `shell.json`. If only the
new installation name exists, rename it back to `local.mise-status` without
changing its symlink target. Never overwrite either plugin path if both exist;
resolve the conflict first. A full return to the old ID also requires the old
plugin code/manifest; restoring config alone does not downgrade the checkout.

## Tests (temporary fixtures only)

```sh
python3 -B -m unittest discover -s tests -p test_migration.py -v
```

Tests invoke the CLI with a temporary `HOME` and/or `--config-dir`, exercise
symlink/directory installs, nested settings, collisions, validation, idempotence,
and injected staging/replacement failures. They never migrate the real profile.
