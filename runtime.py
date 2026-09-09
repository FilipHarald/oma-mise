"""Linux subprocess boundary shared by isolated (-I -S) plugin helpers.

Each invocation has a separate guardian. Its lifetime pipe survives neither a
normal helper exit nor SIGKILL. The guardian owns/reaps the command session and
adopted descendants. No threads, shell, ambient PATH, or unbounded collectors.
Trusted mise config/templates under HOME intentionally remain enabled.
"""
import ctypes
import os
from pathlib import Path
import select
import selectors
import signal
import stat
import subprocess
import time

TERM_GRACE = 0.15

class OutputLimit(subprocess.SubprocessError):
    pass


def _kill_group(pid, sig):
    try:
        os.killpg(pid, sig)
    except ProcessLookupError:
        pass


def _guardian(argv, cwd, env, control, out, err, timeout):
    # A subreaper also reaps grandchildren orphaned by the group teardown.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        os._exit(125)
    os.setsid()
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    child = None
    code = 125
    deadline = time.monotonic() + timeout
    try:
        executable_fd = None
        try:
            if argv[1:2] == ['bootstrap']:
                executable_fd = _open_mise(argv[0], Path(cwd))
            child = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                     stdout=out, stderr=err, start_new_session=True,
                                     executable=f'/proc/self/fd/{executable_fd}' if executable_fd is not None else None,
                                     pass_fds=() if executable_fd is None else (executable_fd,),
                                     close_fds=True)
        finally:
            if executable_fd is not None:
                os.close(executable_fd)
        os.close(out)
        os.close(err)
        while True:
            if select.select([control], [], [], 0.02)[0]:
                if not os.read(control, 1):
                    break
            if time.monotonic() >= deadline:
                code = 124
                break
            result = os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
            if result is not None:
                # Keep the leader unreaped until the last killpg: its PID pins
                # the process-group identity against reuse during the grace.
                code = result.si_status if result.si_code == os.CLD_EXITED and result.si_status < 124 else 125
                break
    except BaseException:
        code = 125
    finally:
        if child is not None:
            _kill_group(child.pid, signal.SIGTERM)
            time.sleep(TERM_GRACE)
            _kill_group(child.pid, signal.SIGKILL)
            _reap_descendants()
    os._exit(code)


def _reap_descendants():
    """Bounded adoption drain, including children that escaped via setsid().

    pidfd signals bind to a process identity; verify parentage after opening.
    No blocking waitpid: even an uninterruptible kernel task cannot hang us.
    This is containment of trusted CLI work, not a hostile fork-bomb sandbox.
    """
    deadline = time.monotonic() + 0.75
    term_until = time.monotonic() + TERM_GRACE
    children_file = f'/proc/self/task/{os.getpid()}/children'
    while time.monotonic() < deadline:
        with open(children_file, 'rb', buffering=0) as stream:
            children = stream.read(65536).split()
        if not children:
            return
        for token in children:
            fd = None
            try:
                pid = int(token)
                fd = os.pidfd_open(pid)
                with open(f'/proc/{pid}/stat', 'rb', buffering=0) as stream:
                    fields = stream.read(4096).rsplit(b')', 1)[1].split()
                if int(fields[1]) == os.getpid():
                    signal.pidfd_send_signal(fd, signal.SIGTERM if time.monotonic() < term_until else signal.SIGKILL)
            except (ProcessLookupError, FileNotFoundError):
                pass
            finally:
                if fd is not None:
                    os.close(fd)
        while True:
            try:
                pid, _ = os.waitpid(-1, os.WNOHANG)
                if not pid:
                    break
            except ChildProcessError:
                return
        time.sleep(0.01)


def run(argv, *, cwd=None, env=None, timeout=15, stdout_limit=1048576,
        stderr_limit=65536):
    """Return a text CompletedProcess, rejecting either stream on overflow.

    timeout is an absolute wall deadline, not a per-read idle timeout. Guardian
    cleanup adds at most 900ms of scheduled grace/drain time. SIGINT/SIGTERM
    cancel and clean up before propagating. Helper SIGKILL closes the lifetime
    pipe and triggers the same cleanup independently of the dead helper.
    Must be called from the helper's main thread (fork/signal handlers).
    """
    if not argv or not os.path.isabs(argv[0]):
        raise ValueError('absolute executable required')
    if not 0 < timeout <= 900 or not 0 < stdout_limit <= 1048576 or not 0 < stderr_limit <= 1048576:
        raise ValueError('invalid runtime limits')
    if env is None:
        env = environment()
    cr, cw = os.pipe()
    outr, outw = os.pipe()
    errr, errw = os.pipe()
    guardian = None
    previous = {}
    def cancel(signum, frame):
        raise KeyboardInterrupt
    try:
        for sig in (signal.SIGTERM, signal.SIGINT):
            previous[sig] = signal.signal(sig, cancel)
        guardian = os.fork()
        if guardian == 0:
            os.close(cw)
            os.close(outr)
            os.close(errr)
            try:
                _guardian(argv, cwd, env, cr, outw, errw, timeout)
            finally:
                # Never unwind into the caller's JSON protocol in the fork.
                os._exit(125)
        os.close(cr); cr = -1
        os.close(outw); outw = -1
        os.close(errw); errw = -1
        buffers = {outr: bytearray(), errr: bytearray()}
        limits = {outr: stdout_limit, errr: stderr_limit}
        deadline = time.monotonic() + timeout + 1
        with selectors.DefaultSelector() as selector:
            for fd in buffers:
                os.set_blocking(fd, False)
                selector.register(fd, selectors.EVENT_READ)
            while selector.get_map():
                if time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired(argv[0], timeout)
                for key, _ in selector.select(0.05):
                    fd = key.fd
                    chunk = os.read(fd, min(8192, limits[fd] - len(buffers[fd]) + 1))
                    if not chunk:
                        selector.unregister(fd)
                    else:
                        if len(buffers[fd]) + len(chunk) > limits[fd]:
                            raise OutputLimit('command output exceeded limit')
                        buffers[fd].extend(chunk)
        _, status = os.waitpid(guardian, 0)
        guardian = None
        code = os.waitstatus_to_exitcode(status)
        if code == 124:
            raise subprocess.TimeoutExpired(argv[0], timeout)
        if code == 125 or code < 0:
            raise OSError('command supervision failed')
        return subprocess.CompletedProcess(argv, code,
            buffers[outr].decode('utf-8'), buffers[errr].decode('utf-8'))
    finally:
        # Suppress repeat cancellation until the guardian has reaped its group.
        for sig in previous:
            signal.signal(sig, signal.SIG_IGN)
        for fd in (cw, cr, outr, outw, errr, errw):
            if fd >= 0:
                os.close(fd)
        if guardian:
            os.waitpid(guardian, 0)
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def environment(home=None, *, systemctl=False):
    home = Path.home() if home is None else Path(home)
    env = {'HOME': str(home), 'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8',
           'LC_ALL': 'C.UTF-8', 'XDG_CONFIG_HOME': str(home / '.config'),
           'XDG_DATA_HOME': str(home / '.local/share'),
           'XDG_STATE_HOME': str(home / '.local/state'),
           'XDG_CACHE_HOME': str(home / '.cache'),
           'MISE_NO_COLOR': '1', 'NO_COLOR': '1', 'TERM': 'dumb'}
    if systemctl:
        runtime = f'/run/user/{os.getuid()}'
        env.update(XDG_RUNTIME_DIR=runtime,
                   DBUS_SESSION_BUS_ADDRESS=f'unix:path={runtime}/bus',
                   SYSTEMD_PAGER='', SYSTEMD_COLORS='0')
    return env


def mise_executable(home):
    # HOME is the explicit trust anchor; never accept MISE_BIN or PATH lookup.
    for path in (Path(home) / '.local/bin/mise', Path('/usr/bin/mise')):
        try:
            fd = _open_mise(str(path), Path(home))
            os.close(fd)
            return str(path)
        except OSError:
            continue
    raise FileNotFoundError('trusted mise executable unavailable')


def _open_mise(path, home):
    """Validate held descriptors; the guardian executes this same final inode."""
    if path == str(home / '.local/bin/mise'):
        anchor, parts = home, ('.local', 'bin', 'mise')
    elif path == '/usr/bin/mise':
        anchor, parts = Path('/usr'), ('bin', 'mise')
    else:
        raise PermissionError('unapproved mise path')
    fd = os.open(anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        for index, part in enumerate(parts):
            info = os.fstat(fd)
            if info.st_uid not in (0, os.getuid()) or info.st_mode & 0o022:
                raise PermissionError('unsafe executable directory')
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
            if index < len(parts)-1:
                flags |= os.O_DIRECTORY
            next_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid not in (0, os.getuid()) or info.st_mode & 0o022 or not info.st_mode & 0o111:
            raise PermissionError('unsafe executable')
        result, fd = fd, -1
        return result
    finally:
        if fd >= 0:
            os.close(fd)
