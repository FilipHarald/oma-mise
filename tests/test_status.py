"""Read-only status monitor contract tests; no external mise required."""
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import os
import time
import unittest
from unittest.mock import patch

NOW = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
STAMP = NOW.isoformat()
MODULE = Path(__file__).resolve().parents[1] / 'status.py'


def healthy():
    return {
        'files': [{'target': '~/.bashrc', 'mode': 'track', 'state': 'tracked', 'origin': {}}],
        'edits': [],
        'history': {
            'enabled': True, 'tracked_entries': 1, 'tracked_files': 1,
            'checkpoints': 4, 'pending_operations': 0, 'watcher': 'running',
            'unavailable': None,
            'health': {'updated_at': STAMP, 'watcher': {
                'started_at': STAMP, 'last_capture': STAMP, 'last_reconcile': STAMP,
                'consecutive_failures': 0, 'degraded': []}, 'throttled': []},
            'sync': {'origin': 'git@example.com:private/repo', 'branch': 'main',
                     'mode': 'sync', 'last_publish': STAMP, 'last_fetch': STAMP,
                     'last_apply': STAMP, 'pending_applications': [], 'conflicts': [],
                     'declarations_changed': False, 'last_error': None,
                     'failing_since': None, 'consecutive_failures': 0,
                     'application_failure': None, 'validation_error': None}}}


class StatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.status = None
        if MODULE.exists():
            spec = importlib.util.spec_from_file_location('mise_status', MODULE)
            cls.status = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.status)

    def evaluate(self, payload):
        self.assertIsNotNone(self.status, 'status.py must exist')
        return self.status.evaluate(payload, now=NOW)

    def test_no_files_is_not_synced(self):
        payload = healthy()
        payload['files'] = []
        self.assertEqual(self.evaluate(payload)['level'], 'yellow')

    def test_timestamps_use_local_calendar_days_and_24_hour_time(self):
        previous_tz = os.environ.get('TZ')
        self.addCleanup(self.restore_timezone, previous_tz)
        os.environ['TZ'] = 'Europe/Stockholm'
        time.tzset()
        cases = (
            ('2026-09-08T11:25:02Z', 'today 13:25'),
            ('2026-09-07T21:05:59Z', 'yesterday 23:05'),
            ('2026-09-04T06:03:45Z', '4 sep 08:03'),
            ('2026-09-07T22:05:00Z', 'today 00:05'),
            (None, 'unknown'),
        )
        for stamp, expected in cases:
            with self.subTest(stamp=stamp):
                payload = healthy()
                for field in ('publish', 'fetch', 'apply'):
                    payload['history']['sync'][f'last_{field}'] = stamp
                result = self.evaluate(payload)
                for field in ('publish', 'fetch', 'apply'):
                    self.assertIn(f'Last {field}: {expected}', result['details'])
                self.assertEqual(result['checked_label'], 'today 14:00')

    @staticmethod
    def restore_timezone(previous_tz):
        if previous_tz is None:
            os.environ.pop('TZ', None)
        else:
            os.environ['TZ'] = previous_tz
        time.tzset()

    def test_pending_work_is_yellow(self):
        for section, field, value in (
            ('root', 'edits', [{'secret': 'credential'}]),
            ('history', 'pending_operations', 2),
            ('sync', 'pending_applications', ['private/path']),
            ('sync', 'declarations_changed', True),
            ('watcher', 'degraded', ['private/path']),
            ('health', 'throttled', ['private/path']),
        ):
            with self.subTest(field=field):
                payload = healthy()
                targets = {'root': payload, 'history': payload['history'],
                           'sync': payload['history']['sync'],
                           'health': payload['history']['health'],
                           'watcher': payload['history']['health']['watcher']}
                targets[section][field] = value
                result = self.evaluate(payload)
                self.assertEqual(result['level'], 'yellow')
                self.assertNotIn('private/path', str(result))
                self.assertNotIn('credential', str(result))

    def test_errors_override_pending(self):
        for section, field, value in (
            ('sync', 'conflicts', ['SECRET']),
            ('sync', 'last_error', 'SECRET'),
            ('sync', 'application_failure', {'error': 'SECRET'}),
            ('sync', 'validation_error', 'SECRET'),
            ('sync', 'failing_since', STAMP),
            ('sync', 'consecutive_failures', 1),
            ('history', 'unavailable', 'SECRET'),
        ):
            with self.subTest(field=field):
                payload = healthy()
                payload['edits'] = ['SECRET']
                target = payload['history'] if section == 'history' else payload['history']['sync']
                target[field] = value
                result = self.evaluate(payload)
                self.assertEqual(result['level'], 'red')
                self.assertNotIn('SECRET', str(result))

    def test_stopped_watcher_is_blue_unless_sync_error(self):
        payload = healthy()
        payload['history']['watcher'] = 'stopped'
        payload['edits'] = ['private/path']
        result = self.evaluate(payload)
        self.assertEqual(result['level'], 'blue')
        self.assertEqual(result['summary'], 'Dotfiles watcher stopped')
        payload['history']['sync']['conflicts'] = ['private/path']
        self.assertEqual(self.evaluate(payload)['level'], 'red')

    def test_unknown_or_malformed_status_never_green(self):
        cases = [None, [], {}, {'history': None}]
        for path, value in (
            (('files',), None), (('files',), [{}]),
            (('files',), [{'state': 'SECRET'}]), (('edits',), {}),
            (('history',), None), (('history', 'enabled'), False),
            (('history', 'sync'), None), (('history', 'health'), []),
            (('history', 'watcher'), 'SECRET'),
            (('history', 'pending_operations'), 'SECRET'),
            (('history', 'sync', 'mode'), 'SECRET'),
            (('history', 'sync', 'conflicts'), {}),
            (('history', 'sync', 'last_fetch'), None),
            (('history', 'sync', 'last_fetch'), 'SECRET'),
            (('history', 'sync', 'declarations_changed'), 'false'),
        ):
            payload = healthy()
            target = payload
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            cases.append(payload)
        for payload in cases:
            with self.subTest(payload=payload):
                result = self.evaluate(payload)
                self.assertEqual(result['level'], 'yellow')
                self.assertNotIn('SECRET', str(result))
        for section in ('root', 'history', 'sync', 'health', 'watcher'):
            original = healthy()
            targets = {'root': original, 'history': original['history'],
                       'sync': original['history']['sync'],
                       'health': original['history']['health'],
                       'watcher': original['history']['health']['watcher']}
            for key in list(targets[section]):
                payload = copy.deepcopy(original)
                target = payload
                for part in {'root': [], 'history': ['history'],
                             'sync': ['history', 'sync'],
                             'health': ['history', 'health'],
                             'watcher': ['history', 'health', 'watcher']}[section]:
                    target = target[part]
                del target[key]
                if key in ('files', 'edits', 'enabled', 'pending_operations', 'watcher',
                           'unavailable', 'sync', 'health', 'mode', 'conflicts',
                           'pending_applications', 'last_fetch', 'last_error',
                           'consecutive_failures', 'degraded', 'throttled',
                           'application_failure', 'validation_error', 'failing_since',
                           'declarations_changed'):
                    self.assertNotEqual(self.evaluate(payload)['level'], 'green', (section, key))

    def test_known_error_survives_other_malformed_fields(self):
        payload = healthy()
        payload['files'] = None
        payload['history']['sync']['conflicts'] = ['SECRET']
        self.assertEqual(self.evaluate(payload)['level'], 'red')

    def test_fetch_freshness_not_idle_health_age(self):
        for seconds, level in ((900, 'green'), (901, 'yellow'), (-301, 'yellow')):
            payload = healthy()
            payload['history']['health']['updated_at'] = '2000-01-01T00:00:00Z'
            payload['history']['sync']['last_fetch'] = (NOW - timedelta(seconds=seconds)).isoformat()
            self.assertEqual(self.evaluate(payload)['level'], level)

    def test_command_is_read_only_home_scoped_and_prefers_local_mise(self):
        self.assertTrue(hasattr(self.status, 'collect'), 'collect must exist')
        with patch.object(self.status.os, 'access', return_value=True), \
             patch.object(self.status.Path, 'is_file', return_value=True), \
             patch.object(self.status.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, json.dumps(healthy()), 'SECRET')) as run:
            result = self.status.collect(now=NOW)
        self.assertEqual(result['level'], 'green')
        run.assert_called_once_with(
            [str(Path.home() / '.local/bin/mise'), 'bootstrap', 'dotfiles', 'status', '--json'],
            cwd=str(Path.home()), capture_output=True, text=True, timeout=15,
            check=False, stdin=subprocess.DEVNULL)

    def test_subprocess_failures_are_sanitized_yellow(self):
        cases = [FileNotFoundError('SECRET'), PermissionError('SECRET'),
                 subprocess.TimeoutExpired('SECRET', 15, output='SECRET'),
                 UnicodeDecodeError('utf-8', b'\xff', 0, 1, 'SECRET'),
                 subprocess.CompletedProcess([], 2, json.dumps(healthy()), 'SECRET'),
                 subprocess.CompletedProcess([], 0, 'SECRET', 'SECRET'),
                 subprocess.CompletedProcess([], 0, '', 'SECRET')]
        for case in cases:
            with self.subTest(case=type(case).__name__), \
                 patch.object(self.status.subprocess, 'run') as run:
                if isinstance(case, Exception):
                    run.side_effect = case
                else:
                    run.return_value = case
                result = self.status.collect(now=NOW)
                self.assertEqual(result['level'], 'yellow')
                self.assertNotIn('SECRET', str(result))

    def test_path_fallback(self):
        with patch.object(self.status.os, 'access', return_value=False), \
             patch.object(self.status.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '{}', '')) as run:
            self.status.collect(now=NOW)
        self.assertEqual(run.call_args.args[0][0], 'mise')

    def test_cli_prints_exactly_one_json_object(self):
        self.assertTrue(hasattr(self.status, 'main'), 'main must exist')
        with patch.object(self.status, 'collect', return_value=self.evaluate(healthy())), \
             patch('sys.stdout', new_callable=io.StringIO) as stdout:
            self.status.main()
        self.assertEqual(json.loads(stdout.getvalue())['level'], 'green')
        self.assertEqual(len(stdout.getvalue().splitlines()), 1)

    def test_details_are_compact_with_checkpoints(self):
        result = self.evaluate(healthy())
        self.assertIn('Checkpoints: 4', ' | '.join(result['details']))
        self.assertNotIn('Edits: 0', ' | '.join(result['details']))
        self.assertNotIn('Conflicts: 0', ' | '.join(result['details']))
        payload = healthy()
        payload['edits'] = ['SECRET']
        payload['history']['sync']['conflicts'] = ['SECRET']
        result = self.evaluate(payload)
        self.assertIn('Edits: 1', ' | '.join(result['details']))
        self.assertIn('Conflicts: 1', ' | '.join(result['details']))
        self.assertLessEqual(len(self.evaluate({})['details']), 14)

    def test_confirmed_healthy_sync(self):
        result = self.evaluate(healthy())
        self.assertEqual(result['level'], 'green')
        self.assertEqual(set(result), {'level', 'summary', 'details', 'checked_at', 'checked_label', 'timestamps'})
        self.assertEqual(result['timestamps'], dict.fromkeys(('publish', 'fetch', 'apply'), STAMP))
        self.assertEqual(result['checked_at'], STAMP)
        self.assertTrue(all(isinstance(item, str) for item in result['details']))
        self.assertIn('Files: 1', ' | '.join(result['details']))
        self.assertIn('Watcher: running', result['details'])
        self.assertTrue(any(item.startswith('Last fetch: ') for item in result['details']))
        self.assertNotIn('private/repo', str(result))


if __name__ == '__main__':
    unittest.main()
