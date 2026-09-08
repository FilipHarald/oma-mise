"""Read-only terminal review tests; never execute mise."""
import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import unittest
from unittest.mock import call, patch


MODULE_PATH = Path(__file__).resolve().parents[1] / 'review.py'
spec = importlib.util.spec_from_file_location('review', MODULE_PATH)
assert spec is not None and spec.loader is not None
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(review, 'review.py must implement terminal review')
        self.home = Path('/mock/home with spaces')
        self.output = io.StringIO()
        self.enter_context = contextlib.ExitStack()
        self.addCleanup(self.enter_context.close)
        enter = self.enter_context.enter_context
        enter(contextlib.redirect_stdout(self.output))
        enter(contextlib.redirect_stderr(self.output))
        enter(patch.object(review.Path, 'home', return_value=self.home))
        enter(patch.object(review.Path, 'is_file', return_value=False))
        self.access = enter(patch.object(review.os, 'access', return_value=False))
        self.executable = enter(patch.object(review.runtime, 'mise_executable', return_value='/usr/bin/mise'))
        self.run_command = enter(patch.object(review.runtime, 'run', return_value=subprocess.CompletedProcess([], 0, '', '')))
        self.prompt = enter(patch('builtins.input', return_value=''))

    def command(self, *args, executable='/usr/bin/mise'):
        return call([executable, 'bootstrap', 'dotfiles', *args],
                    cwd=str(self.home), env=review.runtime.environment(self.home),
                    timeout=30, stdout_limit=1048576, stderr_limit=65536)

    def test_conflicts_runs_status_then_read_only_pull_in_home(self):
        self.assertEqual(review.main(['conflicts']), 0)
        self.assertEqual(self.run_command.call_args_list, [self.command('status'),
                                                 self.command('pull', '--dry-run')])
        self.prompt.assert_called_once_with('Press Enter to close…')

    def test_general_status_review_does_not_pull_or_diff(self):
        self.assertEqual(review.main(['status']), 0)
        self.assertEqual(self.run_command.call_args_list, [self.command('status')])

    def test_terminal_output_is_visible_without_control_sequences(self):
        self.run_command.return_value = subprocess.CompletedProcess([], 0,
            'diff visible\n\x1b]52;c;payload\x07\r', 'warning\n\x9b31m')
        self.assertEqual(review.main(['status']), 0)
        text = self.output.getvalue()
        self.assertIn('diff visible\n', text)
        self.assertIn('warning\n', text)
        for control in ('\x1b', '\x07', '\r', '\x9b'):
            self.assertNotIn(control, text)

    def test_changes_adds_history_diff_before_dry_run(self):
        self.assertEqual(review.main(['changes']), 0)
        self.assertEqual(self.run_command.call_args_list, [self.command('status'),
                                                 self.command('history', 'diff'),
                                                 self.command('pull', '--dry-run')])

    def test_invalid_arguments_never_spawn(self):
        for args in ([], ['other'], ['conflicts', 'extra'], ['--help'], ['Changes']):
            with self.subTest(args=args):
                self.assertEqual(review.main(args), 2)
        self.run_command.assert_not_called()
        self.assertEqual(self.prompt.call_count, 5)
        self.assertIn('Usage:', self.output.getvalue())

    def test_cli_reads_sys_argv(self):
        with patch.object(review.sys, 'argv', ['review.py', 'changes']):
            self.assertEqual(review.main(), 0)
        self.assertEqual(self.run_command.call_args_list[1], self.command('history', 'diff'))

    def test_local_executable_is_preferred(self):
        self.executable.return_value = str(self.home / '.local/bin/mise')
        with patch.object(review.Path, 'is_file', return_value=True):
            self.access.return_value = True
            self.assertEqual(review.main(['conflicts']), 0)
        executable = str(self.home / '.local/bin/mise')
        self.assertEqual(self.run_command.call_args_list,
                         [self.command('status', executable=executable),
                          self.command('pull', '--dry-run', executable=executable)])
        self.executable.assert_called_once_with(self.home)

    def test_nonexecutable_local_file_uses_path(self):
        with patch.object(review.Path, 'is_file', return_value=True):
            self.assertEqual(review.main(['conflicts']), 0)
        self.assertEqual(self.run_command.call_args_list[0], self.command('status'))

    def test_nonzero_status_is_reported_but_remaining_reviews_run(self):
        self.run_command.side_effect = [subprocess.CompletedProcess([], 7),
                                subprocess.CompletedProcess([], 0),
                                subprocess.CompletedProcess([], 0)]
        self.assertEqual(review.main(['changes']), 1)
        self.assertEqual(self.run_command.call_count, 3)
        self.assertIn('status failed', self.output.getvalue())
        self.assertLess(len(self.output.getvalue()), 500)
        self.prompt.assert_called_once_with('Press Enter to close…')

    def test_timeout_is_sanitized_and_review_continues(self):
        self.run_command.side_effect = [subprocess.TimeoutExpired('SECRET\x1b[31m' * 1000, 30),
                                subprocess.CompletedProcess([], 0)]
        self.assertEqual(review.main(['conflicts']), 1)
        self.assertEqual(self.run_command.call_count, 2)
        self.assertIn('timed out after 30 seconds', self.output.getvalue())
        self.assertNotIn('SECRET', self.output.getvalue())
        self.assertNotIn('\x1b', self.output.getvalue())
        self.assertLess(len(self.output.getvalue()), 500)
        self.prompt.assert_called_once_with('Press Enter to close…')

    def test_launch_failure_is_sanitized(self):
        self.run_command.side_effect = OSError('SECRET\x1b[31m' * 1000)
        self.assertEqual(review.main(['conflicts']), 1)
        self.assertIn('could not run', self.output.getvalue())
        self.assertNotIn('SECRET', self.output.getvalue())
        self.assertLess(len(self.output.getvalue()), 500)
        self.prompt.assert_called_once_with('Press Enter to close…')

    def test_home_resolution_failure_still_prompts(self):
        with patch.object(review.Path, 'home', side_effect=RuntimeError('SECRET')):
            self.assertEqual(review.main(['conflicts']), 1)
        self.run_command.assert_not_called()
        self.assertNotIn('SECRET', self.output.getvalue())
        self.prompt.assert_called_once_with('Press Enter to close…')

    def test_command_interrupt_still_prompts_without_traceback(self):
        self.run_command.side_effect = KeyboardInterrupt
        self.assertEqual(review.main(['changes']), 130)
        self.assertEqual(self.run_command.call_count, 1)
        self.assertIn('interrupted', self.output.getvalue())
        self.prompt.assert_called_once_with('Press Enter to close…')

    def test_prompt_eof_or_interrupt_is_graceful(self):
        for error in (EOFError, KeyboardInterrupt):
            with self.subTest(error=error):
                self.prompt.side_effect = error
                self.assertEqual(review.main(['conflicts']), 0)


if __name__ == '__main__':
    unittest.main()
