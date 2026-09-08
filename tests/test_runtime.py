"""Real subprocess containment tests (no live mise/service operations)."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
import signal
import json
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

def runtime():
    spec = importlib.util.spec_from_file_location('runtime_test', ROOT / 'runtime.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class RuntimeTests(unittest.TestCase):
    def helper(self, code, timeout=.2):
        script = (f'import importlib.util; s=importlib.util.spec_from_file_location("r",{str(ROOT / "runtime.py")!r}); '
                  'r=importlib.util.module_from_spec(s); s.loader.exec_module(r); '
                  f'r.run(["/usr/bin/python3","-I","-S","-c",{code!r}],timeout={timeout!r})')
        return subprocess.Popen(['/usr/bin/python3', '-I', '-S', '-c', script],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def test_escaped_descendant_cannot_hang_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            record = Path(directory) / 'pid'
            code = ('import os,signal,time\n'
                    'if os.fork()==0:\n os.setsid()\n signal.signal(signal.SIGTERM,signal.SIG_IGN)\n'
                    f' open({str(record)!r},"w").write(str(os.getpid()))\n'
                    'time.sleep(20)')
            helper = self.helper(code)
            try:
                try:
                    helper.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.fail('escaped descendant made cleanup unbounded')
                self.assertFalse(Path('/proc', record.read_text()).exists())
            finally:
                if record.exists():
                    try: os.kill(int(record.read_text()), signal.SIGKILL)
                    except ProcessLookupError: pass
                helper.kill()
                helper.wait(timeout=2)

    def test_helper_term_and_kill_clean_up_descendants(self):
        for sig in (signal.SIGTERM, signal.SIGKILL):
            with self.subTest(signal=sig), tempfile.TemporaryDirectory() as directory:
                record = Path(directory) / 'pid'
                code = ('import os,signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); '
                        f'open({str(record)!r},"w").write(str(os.getpid())); time.sleep(20)')
                helper = self.helper(code, timeout=10)
                try:
                    deadline = time.monotonic()+2
                    while not record.exists() and time.monotonic()<deadline:
                        time.sleep(.01)
                    self.assertTrue(record.exists())
                    helper.send_signal(sig)
                    helper.wait(timeout=2)
                    pid = record.read_text()
                    deadline = time.monotonic()+2
                    while Path('/proc', pid).exists() and time.monotonic()<deadline:
                        time.sleep(.01)
                    self.assertFalse(Path('/proc', pid).exists())
                finally:
                    helper.kill()
                    helper.wait(timeout=2)

    def test_unsafe_local_symlink_does_not_override_system_mise(self):
        r = runtime()
        with tempfile.TemporaryDirectory() as home:
            local = Path(home) / '.local/bin/mise'
            local.parent.mkdir(parents=True)
            local.symlink_to('/usr/bin/true')
            try:
                self.assertEqual(r.mise_executable(home), '/usr/bin/mise')
            except FileNotFoundError:
                pass

    def test_unsafe_local_parent_does_not_override_system_mise(self):
        r = runtime()
        with tempfile.TemporaryDirectory() as home:
            local = Path(home) / '.local/bin/mise'
            local.parent.mkdir(parents=True)
            local.write_text('#!/usr/bin/python3 -I\nprint("ok")\n')
            local.chmod(0o700)
            self.assertEqual(r.mise_executable(home), str(local))
            local.parent.chmod(0o777)
            try:
                self.assertEqual(r.mise_executable(home), '/usr/bin/mise')
            except FileNotFoundError:
                pass

    def test_isolated_status_real_fake_mise_and_hostile_path(self):
        from test_status import healthy
        payload = healthy()
        # Deliberately unknown freshness: the expected yellow must not depend
        # on the wall clock matching this fixture's historical timestamp.
        payload['history']['sync']['last_fetch'] = None
        with tempfile.TemporaryDirectory() as home:
            local = Path(home) / '.local/bin/mise'
            local.parent.mkdir(parents=True)
            local.write_text('#!/usr/bin/python3 -I\nimport json,os\n'
                             'assert os.getcwd()==os.environ["HOME"]\n'
                             'assert "MISE_CONFIG_FILE" not in os.environ\n'
                             f'print({json.dumps(payload)!r})\n')
            local.chmod(0o700)
            (Path(home) / 'runtime.py').write_text('raise RuntimeError("SHADOW")')
            env = dict(os.environ, HOME=home, PATH=home, PYTHONPATH=home,
                       MISE_BIN='/hostile', MISE_CONFIG_FILE='/hostile')
            result = subprocess.run(['/usr/bin/python3', '-I', '-S', str(ROOT / 'status.py')],
                                    env=env, cwd=home, capture_output=True, timeout=3)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data['summary'], 'Dotfiles need attention')
            self.assertIn('Files: 1', data['details'][0])
            self.assertNotIn(b'SHADOW', result.stdout + result.stderr)

    def test_clean_environment_ignores_injection_and_preserves_home(self):
        r = runtime()
        with patch.dict(os.environ, {'PATH': '/hostile', 'MISE_BIN': '/hostile/mise',
                 'MISE_CONFIG_FILE': '/hostile/config', 'PYTHONPATH': '/hostile',
                 'LD_PRELOAD': '/hostile.so', 'BASH_ENV': '/hostile',
                 'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/hostile'}):
            env = r.environment('/trusted/home', systemctl=True)
            result = r.run(['/usr/bin/python3', '-I', '-S', '-c',
                            'import os,json; print(json.dumps(dict(os.environ)))'], env=env)
        data = json.loads(result.stdout)
        self.assertEqual(data['HOME'], '/trusted/home')
        self.assertEqual(data['XDG_CONFIG_HOME'], '/trusted/home/.config')
        self.assertNotIn('hostile', result.stdout)

    def test_deadline_kills_and_reaps_term_ignoring_descendant(self):
        r = runtime()
        with tempfile.TemporaryDirectory() as directory:
            record = Path(directory) / 'pid'
            code = ('import os,signal,time; p=os.fork(); '
                    'signal.signal(signal.SIGTERM,signal.SIG_IGN); '
                    f'open({str(record)!r},"w").write(str(os.getpid())) if p==0 else None; '
                    'time.sleep(20)')
            start = time.monotonic()
            with self.assertRaises(subprocess.TimeoutExpired):
                r.run(['/usr/bin/python3', '-I', '-S', '-c', code], timeout=.2)
            self.assertLess(time.monotonic()-start, 1.5)
            self.assertFalse(Path('/proc', record.read_text()).exists())

    def test_drip_output_does_not_extend_absolute_deadline(self):
        r = runtime()
        start = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            r.run(['/usr/bin/python3', '-I', '-S', '-c',
                   'import os,time\nwhile True: os.write(1,b"x"); time.sleep(.03)'],
                  timeout=.2)
        self.assertLess(time.monotonic()-start, 1.5)

    def test_executable_replacement_is_revalidated_at_launch(self):
        r = runtime()
        with tempfile.TemporaryDirectory() as home:
            local = Path(home) / '.local/bin/mise'
            local.parent.mkdir(parents=True)
            local.write_text('#!/usr/bin/python3 -I\nprint("ok")\n')
            local.chmod(0o700)
            executable = r.mise_executable(home)
            local.unlink()
            local.symlink_to('/usr/bin/true')
            with self.assertRaises(OSError):
                r.run([executable, 'bootstrap', 'dotfiles', 'status'], cwd=home)

    def test_stream_limits_reject_stdout_and_stderr(self):
        self.assertTrue((ROOT / 'runtime.py').exists(), 'bounded runtime must exist')
        r = runtime()
        for fd in (1, 2):
            with self.subTest(fd=fd):
                start = time.monotonic()
                with self.assertRaises(r.OutputLimit):
                    r.run(['/usr/bin/python3', '-I', '-S', '-c',
                           f'import os; b=b"x"*8192\nwhile True: os.write({fd}, b)'],
                          timeout=2, stdout_limit=4096, stderr_limit=4096)
                self.assertLess(time.monotonic()-start, 2)

if __name__ == '__main__':
    unittest.main()
