# Migrate the plugin ID

The plugin and its IPC target are now `io.github.filipharald.oma-mise`, replacing
`local.mise-status`. The source checkout stays wherever you already keep it.
This migration does not rename the repository or move a symlink's target.

## Run once for an existing installation

Use the system Python 3 on Linux; no third-party packages are needed. Close/stop the shell using your
normal session controls before migrating, and do not run other configuration
writers or another migration concurrently. The two paths cannot be updated as
one filesystem transaction.

From the existing **source checkout** (not the installed symlink):

```sh
/usr/bin/python3 -I -S migration.py
```

By default the script uses `Path.home() / ".config" / "omarchy"`, regardless of
where the checkout lives. For a different Omarchy configuration directory:

```sh
/usr/bin/python3 -I -S /path/to/oma-mise/migration.py --config-dir /path/to/omarchy-config
```

`-I -S` avoids Python environment, current-directory imports, and site startup
hooks. The script has no sibling-module dependencies. The selected config and
its existing `plugins` directory must be owned by your UID. Every component
from `/` to those directories must be a real directory owned by root or your
UID, without group/other write permission. Symlinked homes, config parents,
config directories, and `plugins` directories are deliberately unsupported;
only the **installation entry** may be a symlink. Paths containing `..`, a
double-slash root, or more than 63 components below `/` are refused. Relative
paths are anchored to the current working directory before the descriptor walk.
This also refuses configurations under shared `/tmp`, even below a private
temporary directory. No directories or permissions are silently repaired.
Linux `renameat2(RENAME_NOREPLACE)`, directory/file advisory locks, descriptor-
relative operations, and filesystem `fsync` support are required; failures
have no unsafe fallback. Do not migrate on untrusted/remote filesystems that
cannot provide the local Linux semantics described here.

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
- Creates a randomly named `shell.json.backup-*` with the exact original bytes,
  mode **0600**, before modifying the installation or configuration. Its path
  is printed on success. Backup timestamps, ACLs, extended attributes, and the
  original permission mode are not copied. Existing backups are not overwritten
  or permission-repaired on later runs.
- Stages changed JSON in a sibling temporary file, preserves permission bits,
  flushes it to disk, then atomically replaces `shell.json`. JSON indentation may
  change. If only the installation name changes, `shell.json` is not rewritten.

A successful repeated run prints `No migration needed.` without writing a new
backup or touching the configuration. Configuration-only migration is supported
when neither installation path exists.

## Refusals and recovery

Preflight rejects missing/non-regular/symlinked `shell.json`, files not owned by
your UID, hard links (link count must be one), group/other-writable files, and
special permission bits. FIFO opens are nonblocking and rejected without
reading. The input is read once from a validated descriptor, at most 1 MiB + 1
byte; oversize files, short reads, and observed modifications are refused. JSON
input and serialized output are each limited to 1 MiB. Before JSON decoding,
a string/escape-aware scan limits nesting to 32 containers and the combined
count of opening containers, commas, and colons outside strings to 10,000.
This bounds collection cardinality before allocation, not after decoding.
Invalid JSON/UTF-8, non-finite numbers (including exponent overflow), non-object
top-level JSON, duplicate dictionary keys, and old/new ID dictionary key
collisions are refused. It refuses an existing destination (even a dangling symlink)
when any migration remains to be done. These failures happen before backup or
other writes. An already-migrated destination is accepted only when the old
installation is absent and the configuration needs no changes.

### Descriptor binding and concurrency limits

The complete validated parent chain stays open throughout the operation. All
file opens, entry checks, renames, and cleanup use those directory descriptors;
no backup or staged file is reopened by name. Files are created exclusively
with unpredictable names and mode 0600, written in checked loops through held
descriptors, and flushed. Stage permission bits are set to the original shell
mode using `fchmod` on its descriptor, never pathname `chmod`. Backup mode stays
0600. File identity/version and parent-chain identity/permissions are rechecked
before mutation and publication. After publication and directory `fsync`, the
retained readable stage descriptor is checked against the approved identity,
type, UID/GID, link count, mode, size, mtime, and intended payload (a bounded
`pread`, never a pathname reopen). Rename legitimately changes ctime, so the
pre-rename ctime is not required to survive; full version checks bracket the
payload read and bind the published pathname to the verified descriptor.
Before success, a renamed installation is checked at the new ID against its
original identity and the same rename-stable metadata, and the old ID must be
absent. This end-state check also runs for installation-only migrations.
The backup is also rechecked through its retained readable descriptor against
the original bytes and approved private mode, and its path must still identify
that descriptor. A detected backup change is a failure, not a verified recovery
copy.

Nonblocking exclusive `flock` locks on the config directory, plugins directory,
and original config inode serialize cooperating migrators without creating a
replaceable lock file. Other tools must cooperate with those locks; the shell
does not necessarily do so. Observed inode, size, mode, link-count, or timestamp
changes detected before replacement cause refusal instead of overwriting that
observed concurrent edit. Postpublication changes cause an explicit failure.
Installation rename and rollback use `RENAME_NOREPLACE`, so a newly created
destination is never overwritten even if it appears after the last check.

**This is not a filesystem transaction or isolation from malicious same-UID
processes.** A process with your UID can ignore advisory locks, change directory
permissions, mutate open file contents, rename directories, or substitute an
entry in the final check-to-rename window. Held descriptors prevent parent
redirection and symlink-target reads/writes; they cannot make pathname rename a
compare-and-swap operation. Stage identity is checked immediately before and
after config replacement. A substitution at the last instant can therefore
publish an unwanted entry, including a symlink, before detection; the script
reports failure, not success, and does not follow that link. In-place stage
payload/mode mutations present at verification are also refused, rather than
adopted as a fresh trusted baseline. An original-config edit made inside the
last check-to-replace window can still be overwritten and is not in the backup;
this is not generic same-UID compare-and-swap protection. A writer can also
race after the final observation of either path. Stop all configuration writers
before running. Installation metadata checks do not recursively audit its files.

If backup/staging fails before mutation, the original config and installation
stay intact; a failed backup write may leave a partial backup, not a usable
recovery copy. If config replacement fails before publication after the plugin
rename, the script attempts to rename the installation back, checking its
identity and rename-stable metadata and refusing any occupied rollback destination.
This also applies when an installation-only final check fails: a substituted or
modified installation is left untouched, and rollback failure requires manual
recovery. Rollback failures are
reported explicitly with the backup path, never hidden as successful recovery.
Owned staging files are cleaned up; substituted entries are left untouched.
The backup is retained. If verification or `fsync` fails **after publication**,
the error identifies that state and the backup: the script does not blindly
overwrite a concurrent writer or roll only the plugin name back. Inspect and
recover manually. Power loss, forced termination, filesystem failure, or hostile
same-UID races can require manual recovery between the separate updates.

For manual recovery, keep the shell stopped, inspect the reported error and the
backup, and restore the chosen `shell.json.backup-*` to `shell.json`. If only the
new installation name exists, rename it back to `local.mise-status` without
changing its symlink target. Never overwrite either plugin path if both exist;
resolve the conflict first. A full return to the old ID also requires the old
plugin code/manifest; restoring config alone does not downgrade the checkout.

## Tests (temporary fixtures only)

```sh
/usr/bin/python3 -I -S -B -m unittest discover -s tests -p test_migration.py -v
```

Tests create disposable fixtures beneath the real home (shared `/tmp` is refused)
and invoke the CLI with a temporary `HOME` and/or `--config-dir`. They exercise
symlink/directory installs, exact nested ID semantics, collisions, idempotence,
FIFO/hard-link/symlink and writable-parent refusals, bounded JSON, read/backup/
stage substitution races, destination creation during rename, advisory locking,
concurrent-writer revalidation, atomic publication, and staging/replacement
failures. Replace-boundary stage content/mode mutations (including same-length
content with restored mtime), delayed installation replacement/mode changes,
and recreation of the old entry exercise final checks, including install-only
paths. A last-instant stage swap explicitly verifies the documented
postpublication detection limitation. They never migrate the real profile.
