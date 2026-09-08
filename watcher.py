#!/usr/bin/python3 -I
"""JSON controller for the local user's mise history watcher only."""
import json
import subprocess
import sys
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location('oma_mise_runtime', Path(__file__).resolve().with_name('runtime.py'))
runtime = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runtime)

UNIT = "dev.mise.mise-history.service"


def result(state="unknown", error=""):
    return {"state": state, "can_control": state in ("running", "stopped"),
            "error": error}


def run_systemctl(arguments):
    return runtime.run(
        ["/usr/bin/systemctl", "--user", *arguments],
        cwd=str(Path.home()), env=runtime.environment(systemctl=True),
        timeout=15, stdout_limit=16384, stderr_limit=16384,
    )


def read_status():
    response = run_systemctl(["show", UNIT, "--property=LoadState,ActiveState,SubState"])
    if response.returncode:
        return result(error="Unable to read watcher status.")
    properties = dict(line.split("=", 1) for line in response.stdout.splitlines() if "=" in line)
    if properties.get("LoadState") != "loaded":
        return result(error="Watcher service is unavailable.")
    active, sub = properties.get("ActiveState"), properties.get("SubState")
    if not active or not sub:
        return result(error="Unable to read watcher status.")
    if (active, sub) == ("active", "running"):
        return result("running")
    if (active, sub) == ("inactive", "dead") or active == "failed":
        return result("stopped")
    return result()


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or args[0] not in ("status", "start", "stop"):
        data = result(error="Expected exactly one command: status, start, or stop.")
    else:
        try:
            data = read_status()
            if args[0] != "status" and not data["error"]:
                if not data["can_control"]:
                    data["error"] = "Watcher service is not in a controllable state."
                else:
                    response = run_systemctl([args[0], UNIT])
                    data = read_status()
                    desired = "running" if args[0] == "start" else "stopped"
                    if response.returncode:
                        data["error"] = "Unable to control watcher service."
                    elif not data["error"] and data["state"] != desired:
                        data["error"] = "Watcher did not reach the requested state."
        except (OSError, RuntimeError, subprocess.SubprocessError, UnicodeError, KeyboardInterrupt):
            # Never expose command output, exception details, paths, or environment.
            data = result(error="Unable to communicate with watcher service.")
    print(json.dumps(data))
    return 1 if data["error"] else 0


if __name__ == "__main__":
    sys.exit(main())
