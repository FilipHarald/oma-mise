"""Exercise the real Quickshell Process API without touching the live shell."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(Path('/usr/bin/quickshell').is_file(), 'Quickshell is required')
class QuickshellRuntimeTests(unittest.TestCase):
    def test_bounded_process_in_isolated_shell(self):
        self.run_harness('runtime.qml', 'PASS: all runtime cases')

    @unittest.skipUnless(Path('/usr/bin/wl-copy').is_file(), 'wl-copy is required')
    def test_clipboard_failure_and_coalescing_without_live_selection(self):
        self.run_harness('clipboard.qml', 'PASS: clipboard allowlist, coalescing, real wl-copy failure cleanup',
                         {'WAYLAND_DISPLAY': 'oma-mise-nonexistent'})

    def test_component_unload_kills_owned_process(self):
        self.run_harness('unload.qml', 'PASS: unload kills and reaps TERM-ignoring owned process')

    def run_harness(self, harness, expected, extra_env=None):
        with tempfile.TemporaryDirectory(prefix='oma-mise-qml-test-') as name:
            stage = Path(name)
            (stage / 'ui').mkdir()
            shutil.copyfile(ROOT / 'ui/BoundedProcess.qml', stage / 'ui/BoundedProcess.qml')
            shutil.copyfile(ROOT / 'ui/ReviewClipboard.qml', stage / 'ui/ReviewClipboard.qml')
            shutil.copyfile(ROOT / 'Presentation.js', stage / 'Presentation.js')
            shutil.copyfile(ROOT / 'tests' / harness, stage / 'shell.qml')
            env = {'PATH': '/usr/bin:/bin', 'HOME': str(stage),
                   'LANG': 'C.UTF-8', 'QT_QPA_PLATFORM': 'offscreen',
                   'QT_FORCE_STDERR_LOGGING': '1',
                   'XDG_CACHE_HOME': str(stage / 'cache'),
                   'XDG_RUNTIME_DIR': f'/run/user/{os.getuid()}'}
            env.update(extra_env or {})
            result = subprocess.run(
                ['/usr/bin/timeout', '-k', '2', '15', '/usr/bin/quickshell',
                 '-p', str(stage / 'shell.qml')],
                env=env, stdin=subprocess.DEVNULL, capture_output=True,
                text=True, timeout=20,
            )
            log = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, log)
            self.assertNotIn('FAIL:', log, log)
            self.assertIn(expected, log, log)


if __name__ == '__main__':
    unittest.main()
