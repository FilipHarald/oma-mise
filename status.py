#!/usr/bin/python3 -I
"""Read-only mise dotfiles status, with a small, non-sensitive JSON contract."""
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
    """Run only the read-only status command, outside the plugin repository."""
    try:
        home = Path.home()
        executable = runtime.mise_executable(home)
        result = runtime.run(
            [executable, 'bootstrap', 'dotfiles', 'status', '--json'],
            cwd=str(home), env=runtime.environment(home), timeout=15,
            stdout_limit=1048576, stderr_limit=65536)
        if result.returncode:
            reason = 'mise status command failed; review it locally'
        else:
            return evaluate(json.loads(result.stdout), now=now)
    except subprocess.TimeoutExpired:
        reason = 'mise status timed out after 15 seconds'
    except (OSError, RuntimeError, subprocess.SubprocessError, KeyboardInterrupt):
        reason = 'mise status could not run; check mise installation and permissions'
    except (ValueError, TypeError, OverflowError):
        reason = 'mise status returned malformed data'
    now = now or datetime.now(timezone.utc)
    return {'level': 'yellow', 'summary': 'Dotfiles status unavailable',
            'details': [reason],
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


def evaluate(payload, now=None):
    """Translate untrusted status data; never echo paths, origins, or errors."""
    now = now or datetime.now(timezone.utc)
    payload = _object(payload)
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
    if edits or operations or pending or sync.get('declarations_changed') is True:
        warnings.append('Pending dotfiles changes need review')
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
    if errors:
        details.append('; '.join(dict.fromkeys(errors)))
    if warnings:
        details.append('; '.join(dict.fromkeys(warnings)))
    if errors or warnings:
        details.append('Review mise dotfiles status locally; this monitor makes no changes')
    level = 'red' if errors else 'blue' if state == 'stopped' else 'yellow' if warnings else 'green'
    summary = {'red': 'Dotfiles error', 'yellow': 'Dotfiles need attention',
               'green': 'Dotfiles synced', 'blue': 'Dotfiles watcher stopped'}[level]
    return {'level': level, 'summary': summary, 'details': details,
            'checked_at': now.isoformat(), 'checked_label': format_timestamp(now, now),
            'timestamps': timestamps}


def main():
    print(json.dumps(collect(), ensure_ascii=True))


if __name__ == '__main__':
    main()
