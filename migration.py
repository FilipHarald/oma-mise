#!/usr/bin/python3 -I
"""Migrate the oma-mise plugin ID without relocating its source checkout."""
import argparse
import json
import math
import os
from pathlib import Path
import ctypes
import fcntl
import secrets
import stat
from contextlib import ExitStack

OLD_ID = "local.mise-status"
NEW_ID = "io.github.filipharald.oma-mise"
MAX_BYTES = 1024 * 1024
MAX_DEPTH = 32
MAX_ITEMS = 10000
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
READ_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


def identity(info):
    return info.st_dev, info.st_ino


def file_version(info):
    return (identity(info), info.st_mode, info.st_uid, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def rename_version(info):
    # A rename changes ctime, but not these approved inode properties.
    return file_version(info)[:-1] + (info.st_gid,)


def verify_published(dirfd, fd, approved, payload, name="shell.json"):
    before = os.fstat(fd)
    if rename_version(before) != rename_version(approved):
        raise ValueError("Published config metadata changed")
    # The stage stays readable; never reopen the now-public pathname.
    if os.pread(fd, MAX_BYTES + 1, 0) != payload:
        raise ValueError("Published config payload changed")
    if file_version(os.fstat(fd)) != file_version(before):
        raise ValueError("Published config changed during verification")
    require_entry(dirfd, name, before)


def checked_directory(fd, leaf=False):
    info = os.fstat(fd)
    if (not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o022
            or info.st_uid not in ({os.getuid()} if leaf else {0, os.getuid()})):
        raise ValueError("Unsafe directory owner or writable parent chain")
    return info


def directory_chain(path, stack):
    if ".." in Path(path).parts or os.fspath(path).startswith("//"):
        raise ValueError("Refusing parent traversal or double-slash root")
    path = Path(os.path.abspath(path))
    if len(path.parts) > 64:
        raise ValueError("Directory chain too deep")
    fd = os.open("/", DIR_FLAGS)
    stack.callback(os.close, fd)
    checked_directory(fd)
    chain = []
    for name in path.parts[1:]:
        child = os.open(name, DIR_FLAGS, dir_fd=fd)
        stack.callback(os.close, child)
        info = checked_directory(child)
        chain.append((fd, name, child, identity(info)))
        fd = child
    checked_directory(fd, leaf=True)
    return fd, chain


def revalidate_chain(chain):
    for parent, name, child, expected in chain:
        checked_directory(parent)
        checked_directory(child)
        if identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) != expected:
            raise ValueError("Directory identity changed during migration")


def read_config(fd):
    info = os.fstat(fd)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or info.st_nlink != 1 or info.st_mode & 0o7022 or info.st_size > MAX_BYTES):
        raise ValueError("Unsafe shell.json type, owner, links, permissions or size")
    raw = os.read(fd, MAX_BYTES + 1)
    if len(raw) > MAX_BYTES or len(raw) != info.st_size or file_version(os.fstat(fd)) != file_version(info):
        raise ValueError("shell.json changed or exceeded input limit")
    return raw, info


def bounded_json(raw):
    # Scan BEFORE the recursive JSON decoder allocates containers. Ignore
    # delimiters inside strings, including escaped quotes/backslashes.
    depth = count = 0
    quoted = escaped = False
    for byte in raw:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (91, 123):
            depth += 1
            count += 1
            if depth > MAX_DEPTH:
                raise ValueError("JSON nesting limit exceeded")
        elif byte in (93, 125):
            depth -= 1
        elif byte in (44, 58):
            count += 1
        if count > MAX_ITEMS:
            raise ValueError("JSON cardinality limit exceeded")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object,
                      parse_constant=invalid_constant, parse_float=finite_float)


def finite_float(text):
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("Non-finite JSON number")
    return value


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


def entry(dirfd, name):
    try:
        return os.stat(name, dir_fd=dirfd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def require_entry(dirfd, name, expected):
    current = entry(dirfd, name)
    if current is None or file_version(current) != file_version(expected):
        raise ValueError(f"Entry changed during migration: {name}")


def lock(fd):
    # Directory inode locks avoid creating/replacing a predictable lock file.
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def rename_noreplace(dirfd, source, destination):
    # Linux renameat2 is essential: a check followed by rename can clobber a
    # destination created concurrently. Never fall back to ordinary rename.
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        rename = libc.renameat2
    except AttributeError as error:
        raise OSError("Linux renameat2 is required") from error
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(dirfd, os.fsencode(source), dirfd, os.fsencode(destination), 1):
        number = ctypes.get_errno()
        raise OSError(number, os.strerror(number), destination)


def cleanup_stage(dirfd, name, fd):
    current = entry(dirfd, name)
    if current is not None and identity(current) == identity(os.fstat(fd)):
        os.unlink(name, dir_fd=dirfd)


def create_file(dirfd, prefix, data, mode, stack, temporary=False):
    name = prefix + secrets.token_hex(16)
    fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                 | os.O_NONBLOCK | os.O_CLOEXEC, 0o600, dir_fd=dirfd)
    stack.callback(os.close, fd)
    if temporary:
        stack.callback(cleanup_stage, dirfd, name, fd)
    # Never reopen this name, including for chmod or copying the backup.
    os.fchmod(fd, mode)
    view = memoryview(data)
    while view:
        count = os.write(fd, view)
        if count <= 0:
            raise OSError("Short migration write")
        view = view[count:]
    os.fsync(fd)
    info = os.fstat(fd)
    if info.st_nlink != 1 or info.st_size != len(data) or stat.S_IMODE(info.st_mode) != mode:
        raise ValueError("Created file changed during migration")
    require_entry(dirfd, name, info)
    return name, fd, info


def migrate(config_dir):
    with ExitStack() as stack:
        dirfd, chain = directory_chain(config_dir, stack)
        lock(dirfd)
        plugins = os.open("plugins", DIR_FLAGS, dir_fd=dirfd)
        stack.callback(os.close, plugins)
        plugin_info = checked_directory(plugins, leaf=True)
        chain.append((dirfd, "plugins", plugins, identity(plugin_info)))
        lock(plugins)
        fd = os.open("shell.json", READ_FLAGS, dir_fd=dirfd)
        stack.callback(os.close, fd)
        lock(fd)
        raw, info = read_config(fd)
        original = bounded_json(raw)
        if not isinstance(original, dict):
            raise ValueError("shell.json must contain a JSON object")
        updated = replace_ids(original)
        old = entry(plugins, OLD_ID)
        if old is not None and (old.st_uid != os.getuid() or not
                (stat.S_ISDIR(old.st_mode) or stat.S_ISLNK(old.st_mode))):
            raise ValueError("Old plugin installation must be an owned directory or symlink")
        if old is None and updated == original:
            revalidate_chain(chain)
            require_entry(dirfd, "shell.json", info)
            return None
        if entry(plugins, NEW_ID) is not None:
            raise ValueError("Migration destination already exists")
        payload = (json.dumps(updated, indent=2, ensure_ascii=False, allow_nan=False)
                   + "\n").encode("utf-8")
        if len(payload) > MAX_BYTES:
            raise ValueError("Migrated JSON exceeds byte limit")

        def validate():
            revalidate_chain(chain)
            require_entry(dirfd, "shell.json", info)
            if file_version(os.fstat(fd)) != file_version(info):
                raise ValueError("Concurrent shell.json writer detected")

        validate()
        backup, backup_fd, backup_info = create_file(dirfd, "shell.json.backup-", raw,
                                                    0o600, stack)
        os.fsync(dirfd)
        staged = stage_fd = stage_info = None
        if updated != original:
            staged, stage_fd, stage_info = create_file(dirfd, ".shell.json.migration-", payload,
                                                       stat.S_IMODE(info.st_mode), stack, temporary=True)
        renamed = published = False
        try:
            validate()
            require_entry(dirfd, backup, backup_info)
            if entry(plugins, NEW_ID) is not None:
                raise ValueError("Migration destination already exists")
            if old is not None:
                require_entry(plugins, OLD_ID, old)
                rename_noreplace(plugins, OLD_ID, NEW_ID)
                renamed = True
                current = entry(plugins, NEW_ID)
                if current is None or identity(current) != identity(old):
                    raise ValueError("Installation changed during rename")
                os.fsync(plugins)
            if staged is not None:
                assert stage_fd is not None
                validate()
                require_entry(dirfd, staged, stage_info)
                os.replace(staged, "shell.json", src_dir_fd=dirfd, dst_dir_fd=dirfd)
                published = True
                os.fsync(dirfd)
            revalidate_chain(chain)
            if published:
                verify_published(dirfd, stage_fd, stage_info, payload)
            if renamed:
                current = entry(plugins, NEW_ID)
                if current is None or rename_version(current) != rename_version(old):
                    raise ValueError("Installation changed after rename")
                if entry(plugins, OLD_ID) is not None:
                    raise ValueError("Old installation entry reappeared")
            verify_published(dirfd, backup_fd, backup_info, raw, name=backup)
        except (OSError, ValueError) as error:
            if renamed and not published:
                try:
                    revalidate_chain(chain)
                    current = entry(plugins, NEW_ID)
                    if current is None or rename_version(current) != rename_version(old):
                        raise ValueError("Installation identity or metadata changed; refusing rollback")
                    rename_noreplace(plugins, NEW_ID, OLD_ID)
                    os.fsync(plugins)
                except (OSError, ValueError) as rollback_error:
                    raise OSError(f"Migration failed ({error}); rollback failed ({rollback_error}); "
                                  f"backup: {Path(config_dir) / backup}") from error
            if published:
                raise OSError(f"Config published but verification/durability failed; inspect both paths; "
                              f"backup: {Path(config_dir) / backup}") from error
            raise
        return Path(config_dir) / backup


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
