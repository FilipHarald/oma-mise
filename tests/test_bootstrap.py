"""Bootstrap action contract tests; no real mise commands are run."""
import contextlib
from datetime import datetime, timezone
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / 'bootstrap.py'


def status(changed):
    stamp = datetime.now(timezone.utc).isoformat()
    return subprocess.CompletedProcess([], 0, json.dumps({
        'files': [{'state': 'tracked'}], 'edits': [],
        'history': {
            'enabled': True, 'checkpoints': 1, 'pending_operations': 0,
            'watcher': 'running', 'unavailable': None,
            'health': {'watcher': {'consecutive_failures': 0, 'degraded': []},
                       'throttled': []},
            'sync': {'mode': 'sync', 'pending_applications': [], 'conflicts': [],
                     'declarations_changed': changed, 'last_error': None,
                     'application_failure': None, 'validation_error': None,
                     'failing_since': None, 'consecutive_failures': 0,
                     'last_publish': stamp, 'last_fetch': stamp, 'last_apply': stamp}}
    }), 'PRIVATE')


class BootstrapTests(unittest.TestCase):
    def invoke(self, args, responses):
        spec = importlib.util.spec_from_file_location('bootstrap_under_test', MODULE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        output = io.StringIO()
        with patch.object(module.runtime, 'mise_executable', return_value='/usr/bin/mise'), \
             patch.object(module.runtime, 'run', side_effect=responses) as run, \
             contextlib.redirect_stdout(output):
            code = module.main(args)
        data = json.loads(output.getvalue())
        self.assertEqual(set(data), {'ok', 'error'})
        self.assertNotIn('PRIVATE', output.getvalue())
        return code, data, run

    def test_complete_bootstrap_is_verified_without_yes(self):
        applied = subprocess.CompletedProcess([], 0, 'PRIVATE', 'PRIVATE')
        code, data, run = self.invoke(['apply'], [status(True), applied, status(False)])
        self.assertEqual(code, 0)
        self.assertEqual(data, {'ok': True, 'error': ''})
        self.assertEqual([call.args[0] for call in run.call_args_list], [
            ['/usr/bin/mise', 'bootstrap', 'dotfiles', 'status', '--json'],
            ['/usr/bin/mise', 'bootstrap', '--silent'],
            ['/usr/bin/mise', 'bootstrap', 'dotfiles', 'status', '--json'],
        ])
        self.assertNotIn('--yes', run.call_args_list[1].args[0])
        self.assertEqual(run.call_args_list[1].kwargs['timeout'], 840)
        self.assertEqual(run.call_args_list[1].kwargs['stderr_limit'], 1048576)

    def test_stale_action_does_not_run_bootstrap(self):
        code, data, run = self.invoke(['apply'], [status(False)])
        self.assertEqual(code, 0)
        self.assertTrue(data['ok'])
        self.assertEqual(run.call_count, 1)

    def test_fresh_status_must_pass_full_action_predicate(self):
        unsafe = json.loads(status(True).stdout)
        unsafe['edits'] = [{}]
        response = subprocess.CompletedProcess([], 0, json.dumps(unsafe), 'PRIVATE')
        code, data, run = self.invoke(['apply'], [response])
        self.assertEqual(code, 0)
        self.assertFalse(data['ok'])
        self.assertIn('status changed', data['error'].lower())
        self.assertEqual(run.call_count, 1)

    def test_declined_or_uncleared_bootstrap_needs_terminal(self):
        failed = subprocess.CompletedProcess([], 1, 'PRIVATE', 'PRIVATE')
        for responses in ([status(True), failed],
                          [status(True), subprocess.CompletedProcess([], 0, '', ''), status(True)]):
            with self.subTest(responses=responses):
                code, data, _ = self.invoke(['apply'], responses)
                self.assertEqual(code, 0)
                self.assertFalse(data['ok'])
                self.assertTrue(data['error'])

    def test_unhealthy_post_bootstrap_status_is_reported(self):
        after = json.loads(status(False).stdout)
        after['history']['sync']['conflicts'] = [{}]
        response = subprocess.CompletedProcess([], 0, json.dumps(after), 'PRIVATE')
        code, data, _ = self.invoke(['apply'], [
            status(True), subprocess.CompletedProcess([], 0, '', ''), response])
        self.assertEqual(code, 0)
        self.assertFalse(data['ok'])
        self.assertIn('still need attention', data['error'])
        after = json.loads(status(False).stdout)
        after['history']['watcher'] = 'stopped'
        after['history']['sync']['last_fetch'] = '2000-01-01T00:00:00Z'
        response = subprocess.CompletedProcess([], 0, json.dumps(after), 'PRIVATE')
        _, data, _ = self.invoke(['apply'], [
            status(True), subprocess.CompletedProcess([], 0, '', ''), response])
        self.assertFalse(data['ok'])

    def test_invalid_input_and_failures_are_sanitized(self):
        code, data, run = self.invoke([], [])
        self.assertNotEqual(code, 0)
        run.assert_not_called()
        self.assertTrue(data['error'])
        for failure in (OSError('PRIVATE'), subprocess.TimeoutExpired('PRIVATE', 1),
                        ValueError('PRIVATE'), UnicodeError('PRIVATE')):
            code, data, _ = self.invoke(['apply'], [failure])
            self.assertEqual(code, 0)
            self.assertNotIn('PRIVATE', str(data))


if __name__ == '__main__':
    unittest.main()
