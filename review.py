#!/usr/bin/python3 -I
"""Read-only dotfiles review in the invoking terminal."""
import os
from pathlib import Path
import subprocess
import sys
import importlib.util

_spec = importlib.util.spec_from_file_location('oma_mise_runtime', Path(__file__).resolve().with_name('runtime.py'))
runtime = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runtime)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        if len(argv) != 1 or argv[0] not in ('status', 'conflicts', 'changes'):
            print('Usage: review.py status|conflicts|changes', file=sys.stderr)
            return 2
        home = Path.home()
        executable = runtime.mise_executable(home)
        commands = [['status']]
        if argv[0] == 'changes':
            commands.append(['history', 'diff'])
        if argv[0] != 'status':
            commands.append(['pull', '--dry-run'])
        failed = False
        for args in commands:
            label = ' '.join(args)
            try:
                result = runtime.run(
                    [executable, 'bootstrap', 'dotfiles', *args],
                    cwd=str(home), env=runtime.environment(home), timeout=30,
                    stdout_limit=1048576, stderr_limit=65536)
                # Preserve terminal review without letting output execute OSC,
                # ANSI, or other terminal control sequences.
                for text, stream in ((result.stdout, sys.stdout), (result.stderr, sys.stderr)):
                    if text:
                        print(''.join(c for c in text if c in '\n\t' or c.isprintable()),
                              end='', file=stream)
                if result.returncode:
                    print(f'mise {label} failed; see terminal output.', file=sys.stderr)
                    failed = True
            except subprocess.TimeoutExpired:
                print(f'mise {label} timed out after 30 seconds.', file=sys.stderr)
                failed = True
        return 1 if failed else 0
    except (OSError, RuntimeError, subprocess.SubprocessError, UnicodeError):
        print('Review could not run; check mise installation and home permissions.',
              file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('\nReview interrupted.', file=sys.stderr)
        return 130
    finally:
        try:
            input('Press Enter to close…')
        except (EOFError, KeyboardInterrupt):
            pass


if __name__ == '__main__':
    sys.exit(main())
