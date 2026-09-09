#!/usr/bin/python3 -I
"""Read-only mise dotfiles status with a small, display-safe JSON contract."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import importlib.util

# Isolated Python excludes the script directory. Load only this trusted sibling,
# never add a directory to sys.path or resolve a module through cwd/PYTHONPATH.
_spec = importlib.util.spec_from_file_location('oma_mise_runtime', Path(__file__).resolve().with_name('runtime.py'))
runtime = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runtime)

MAX_ITEMS = 4096
MAX_NUMBER = 1000000
MAX_FIELDS = 64


def collect(now=None):
    """Run read-only status and bounded recent-history commands from HOME."""
    try:
        home = Path.home()
        executable = runtime.mise_executable(home)
        env = runtime.environment(home)
        result = runtime.run(
            [executable, 'bootstrap', 'dotfiles', 'status', '--json'],
            cwd=str(home), env=env, timeout=15,
            stdout_limit=1048576, stderr_limit=65536)
        if result.returncode:
            reason = 'mise status command failed; review it locally'
        else:
            payload = json.loads(result.stdout)
            history_payload = None
            try:
                history = runtime.run(
                    [executable, 'bootstrap', 'dotfiles', 'history', '--json',
                     '--limit', '50'],
                    cwd=str(home), env=env, timeout=15,
                    stdout_limit=1048576, stderr_limit=65536)
                if not history.returncode:
                    history_payload = json.loads(history.stdout)
            except (OSError, RuntimeError, subprocess.SubprocessError, UnicodeError,
                    ValueError, TypeError, OverflowError, KeyboardInterrupt):
                pass
            return evaluate(payload, history_payload=history_payload, now=now)
    except subprocess.TimeoutExpired:
        reason = 'mise status timed out after 15 seconds'
    except (OSError, RuntimeError, subprocess.SubprocessError, KeyboardInterrupt):
        reason = 'mise status could not run; check mise installation and permissions'
    except (ValueError, TypeError, OverflowError):
        reason = 'mise status returned malformed data'
    now = now or datetime.now(timezone.utc)
    return {'level': 'yellow', 'summary': 'Dotfiles status unavailable',
            'details': [reason],
            'actions': [], 'needs_attention': True, 'history_available': False,
            'checkpoints': [], 'recent_files': [],
            'checked_at': now.isoformat(), 'checked_label': format_timestamp(now, now)}


def _object(value):
    return value if isinstance(value, dict) and len(value) <= MAX_FIELDS else {}


def _number(value):
    return type(value) is int and 0 <= value <= MAX_NUMBER


def _date(value):
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        stamp = datetime.fromisoformat(value)
        # Reject boundary dates whose offset overflows on local conversion.
        stamp.astimezone()
        return stamp if stamp.tzinfo is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


def _safe_text(value, limit):
    return isinstance(value, str) and 0 < len(value) <= limit and not any(
        ord(char) < 32 or 127 <= ord(char) <= 159
        or ord(char) in (0x061c, 0x200e, 0x200f)
        or 0x202a <= ord(char) <= 0x202e
        or 0x2066 <= ord(char) <= 0x2069 for char in value)


def recent_history(payload, managed_paths):
    """Return display-safe checkpoint and unique file activity from mise history."""
    if not isinstance(payload, list) or len(payload) > 50:
        return False, [], []
    checkpoints, files, seen = [], [], set()
    for item in payload:
        if not isinstance(item, dict) or len(item) > MAX_FIELDS:
            return False, [], []
        stamp = _date(item.get('created_at'))
        message = item.get('description')
        if stamp is None or not _safe_text(message, 256):
            return False, [], []
        at = stamp.isoformat()
        if len(checkpoints) < 10:
            checkpoints.append({'message': message, 'at': at})
        changes = item.get('changes', {})
        if not isinstance(changes, dict) or len(changes) > MAX_FIELDS:
            return False, [], []
        for kind in ('added', 'modified', 'removed'):
            paths = changes.get(kind, [])
            if not isinstance(paths, list) or len(paths) > MAX_ITEMS:
                return False, [], []
            for path in paths:
                if not _safe_text(path, 512):
                    return False, [], []
                if path not in managed_paths:
                    continue
                if path in seen:
                    continue
                seen.add(path)
                if len(files) < 10:
                    files.append({'path': path, 'at': at})
    return True, checkpoints, files


def format_timestamp(stamp, now):
    """Use local calendar days, not elapsed 24-hour intervals."""
    if stamp is None:
        return 'unknown'
    local = stamp.astimezone()
    days = (now.astimezone().date() - local.date()).days
    months = ('jan', 'feb', 'mar', 'apr', 'may', 'jun',
              'jul', 'aug', 'sep', 'oct', 'nov', 'dec')
    day = 'today' if days == 0 else 'yesterday' if days == 1 else f'{local.day} {months[local.month - 1]}'
    return f'{day} {local:%H:%M}'


def evaluate(payload, history_payload=None, now=None):
    """Translate status and bounded history without echoing origins or errors."""
    now = now or datetime.now(timezone.utc)
    payload = _object(payload)
    managed_paths = {
        item.get('target') for item in payload.get('files', [])
        if isinstance(item, dict) and _safe_text(item.get('target'), 512)
    } if isinstance(payload.get('files'), list) else set()
    history_available, recent_checkpoints, recent_files = recent_history(
        history_payload, managed_paths)
    history = _object(payload.get('history'))
    sync = _object(history.get('sync'))
    health = _object(history.get('health'))
    watcher = _object(health.get('watcher'))
    warnings, errors, details = [], [], []

    counts = []

    def count(source, key, label, is_list=True):
        value = source.get(key)
        valid = isinstance(value, list) and len(value) <= MAX_ITEMS if is_list else _number(value)
        if not valid:
            warnings.append('Some status fields are missing or unrecognized')
            counts.append(f'{label}: unknown')
            return 0
        total = len(value) if is_list else value
        if total or key in ('files', 'checkpoints'):
            counts.append(f'{label}: {total}')
        return total

    count(payload, 'files', 'Files')
    count(history, 'checkpoints', 'Checkpoints', False)
    details.append(' | '.join(counts))
    counts.clear()
    files = payload.get('files')
    if files == []:
        warnings.append('No dotfiles are configured')
    if isinstance(files, list) and len(files) <= MAX_ITEMS and any(
        not isinstance(item, dict) or len(item) > MAX_FIELDS or item.get('state') != 'tracked'
        for item in files
    ):
        warnings.append('File states need review')
    edits = count(payload, 'edits', 'Edits')
    operations = count(history, 'pending_operations', 'Pending operations', False)
    pending = count(sync, 'pending_applications', 'Pending applications')
    conflicts = count(sync, 'conflicts', 'Conflicts')
    if counts:
        details.append(' | '.join(counts))
    declarations_changed = sync.get('declarations_changed') is True
    if edits or operations or pending:
        warnings.append('Pending dotfiles changes need review')
    if declarations_changed:
        warnings.append('Changed bootstrap declarations need applying')
    if conflicts:
        errors.append('Sync conflicts need review')
    state = history.get('watcher')
    details.append('Watcher: ' + (state if state in ('running', 'stopped') else 'unknown'))
    if state not in ('running', 'stopped'):
        warnings.append('Watcher status is unconfirmed')
    if history.get('enabled') is not True:
        warnings.append('Dotfiles history is not confirmed enabled')
    if sync.get('mode') != 'sync':
        warnings.append('Automatic sync is not confirmed enabled')
    for source, key, label in (
        (history, 'unavailable', 'Dotfiles history is unavailable'),
        (sync, 'last_error', 'Sync reported an error'),
        (sync, 'application_failure', 'Sync application failed'),
        (sync, 'validation_error', 'Sync validation failed'),
        (sync, 'failing_since', 'Sync failure is ongoing'),
    ):
        if key not in source:
            warnings.append('Some status fields are missing or unrecognized')
        elif source[key] is not None:
            errors.append(label)
    for source, label in ((sync, 'Sync'), (watcher, 'Watcher')):
        failures = source.get('consecutive_failures')
        if not _number(failures):
            warnings.append('Failure count is unconfirmed')
        elif failures:
            (errors if source is sync else warnings).append(f'{label} reported failures')
    for source, key in ((watcher, 'degraded'), (health, 'throttled')):
        if not isinstance(source.get(key), list) or source[key]:
            warnings.append('Watcher health needs review')
    if type(sync.get('declarations_changed')) is not bool:
        warnings.append('Declaration status is unconfirmed')
    timestamps = {}
    for field in ('publish', 'fetch', 'apply'):
        stamp = _date(sync.get(f'last_{field}'))
        timestamps[field] = stamp.isoformat() if stamp else None
        readable = format_timestamp(stamp, now)
        details.append(f'Last {field}: {readable}')
        # Health timestamps update on work, not a heartbeat. Only fetch age
        # determines sync freshness; allow five minutes of clock skew.
        if field == 'fetch' and (stamp is None or not -300 <= (now - stamp).total_seconds() <= 900):
            warnings.append('Sync freshness is unconfirmed')
    unique_errors = list(dict.fromkeys(errors))
    unique_warnings = list(dict.fromkeys(warnings))
    if unique_errors:
        details.append('; '.join(unique_errors))
    if unique_warnings:
        details.append('; '.join(unique_warnings))
    if errors or warnings:
        details.append('Review mise dotfiles status locally; this monitor makes no changes')
    level = 'red' if errors else 'blue' if state == 'stopped' else 'yellow' if warnings else 'green'
    summary = {'red': 'Dotfiles error', 'yellow': 'Dotfiles need attention',
               'green': 'Dotfiles synced', 'blue': 'Dotfiles watcher stopped'}[level]
    actions = []
    if declarations_changed and not unique_errors \
            and unique_warnings == ['Changed bootstrap declarations need applying']:
        actions.append('bootstrap')
    return {'level': level, 'summary': summary, 'details': details, 'actions': actions,
            'needs_attention': bool(unique_errors or unique_warnings),
            'history_available': history_available,
            'checkpoints': recent_checkpoints, 'recent_files': recent_files,
            'checked_at': now.isoformat(), 'checked_label': format_timestamp(now, now),
            'timestamps': timestamps}


def main():
    print(json.dumps(collect(), ensure_ascii=True))


if __name__ == '__main__':
    main()
