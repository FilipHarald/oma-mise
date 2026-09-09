#!/usr/bin/python3 -I
"""Run a complete mise bootstrap when changed declarations require it."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

_spec = importlib.util.spec_from_file_location(
    'oma_mise_runtime', Path(__file__).resolve().with_name('runtime.py'))
runtime = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runtime)
_status_spec = importlib.util.spec_from_file_location(
    'oma_mise_status', Path(__file__).resolve().with_name('status.py'))
status_contract = importlib.util.module_from_spec(_status_spec)
_status_spec.loader.exec_module(status_contract)


def result(ok=False, error=''):
    return {'ok': ok, 'error': error}


def declaration_status(executable, home, env):
    response = runtime.run(
        [executable, 'bootstrap', 'dotfiles', 'status', '--json'],
        cwd=str(home), env=env, timeout=15,
        stdout_limit=1048576, stderr_limit=65536)
    if response.returncode:
        raise RuntimeError('status failed')
    payload = json.loads(response.stdout)
    value = payload['history']['sync']['declarations_changed']
    if type(value) is not bool:
        raise ValueError('invalid declaration state')
    evaluated = status_contract.evaluate(payload)
    return value, 'bootstrap' in evaluated['actions'], not evaluated['needs_attention']


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    data = result(error='Expected exactly one command: apply.')
    if args == ['apply']:
        try:
            home = Path.home()
            executable = runtime.mise_executable(home)
            env = runtime.environment(home)
            changed, safe, _ = declaration_status(executable, home, env)
            if not changed:
                data = result(ok=True)
            elif not safe:
                data = result(error='Dotfile status changed; review it before bootstrapping')
            else:
                response = runtime.run(
                    [executable, 'bootstrap', '--silent'], cwd=str(home), env=env,
                    timeout=840, stdout_limit=1048576, stderr_limit=1048576)
                if response.returncode:
                    data = result(error='Complete bootstrap in a terminal')
                else:
                    changed, _, healthy = declaration_status(executable, home, env)
                    if changed:
                        data = result(error='Bootstrap completed but declarations still need attention')
                    elif not healthy:
                        data = result(error='Bootstrap completed but dotfiles still need attention')
                    else:
                        data = result(ok=True)
        except (KeyError, TypeError, ValueError, OSError, RuntimeError, UnicodeError,
                subprocess.SubprocessError, KeyboardInterrupt):
            data = result(error='Unable to complete bootstrap; run it in a terminal')
    print(json.dumps(data, ensure_ascii=True))
    # Valid action failures are protocol results, not transport failures. QML
    # discards stdout from a nonzero process and would lose the safe guidance.
    return 0 if args == ['apply'] else 1


if __name__ == '__main__':
    sys.exit(main())
