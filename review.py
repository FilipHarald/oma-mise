#!/usr/bin/env python3
"""Read-only dotfiles review in the invoking terminal."""
import os
from pathlib import Path
import subprocess
import sys


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        if len(argv) != 1 or argv[0] not in ('conflicts', 'changes'):
            print('Usage: review.py conflicts|changes', file=sys.stderr)
            return 2
        home = Path.home()
        local = home / '.local/bin/mise'
        executable = str(local) if local.is_file() and os.access(local, os.X_OK) else 'mise'
        commands = [['status']]
        if argv[0] == 'changes':
            commands.append(['history', 'diff'])
        commands.append(['pull', '--dry-run'])
        failed = False
        for args in commands:
            label = ' '.join(args)
            try:
                result = subprocess.run(
                    [executable, 'bootstrap', 'dotfiles', *args],
                    cwd=str(home), timeout=30, check=False,
                    stdin=subprocess.DEVNULL)
                if result.returncode:
                    print(f'mise {label} failed; see terminal output.', file=sys.stderr)
                    failed = True
            except subprocess.TimeoutExpired:
                print(f'mise {label} timed out after 30 seconds.', file=sys.stderr)
                failed = True
        return 1 if failed else 0
    except (OSError, RuntimeError):
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
