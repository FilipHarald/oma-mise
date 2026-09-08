"""Controller contract tests; all service operations are stubbed."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / "watcher.py"
UNIT = "dev.mise.mise-history.service"
SHOW = ["/usr/bin/systemctl", "--user", "show", UNIT,
        "--property=LoadState,ActiveState,SubState"]


def reply(active="active", sub="running", load="loaded", returncode=0):
    return subprocess.CompletedProcess([], returncode,
        f"LoadState={load}\nActiveState={active}\nSubState={sub}\n", "PRIVATE STDERR")


class WatcherTests(unittest.TestCase):
    def invoke(self, args, results):
        self.assertTrue(PATH.exists(), "watcher.py must implement the CLI")
        spec = importlib.util.spec_from_file_location("watcher_under_test", PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(module.runtime, "run", side_effect=results) as run:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = module.main(args)
        self.assertEqual(stderr.getvalue(), "")
        data = json.loads(stdout.getvalue())
        self.assertEqual(set(data), {"state", "can_control", "error"})
        self.assertIn(data["state"], ("running", "stopped", "unknown"))
        self.assertIsInstance(data["can_control"], bool)
        self.assertIsInstance(data["error"], str)
        self.assertNotIn("PRIVATE", stdout.getvalue())
        for call in run.call_args_list:
            self.assertEqual(call.kwargs["stdout_limit"], 16384)
            self.assertEqual(call.kwargs["stderr_limit"], 16384)
            self.assertEqual(call.kwargs["env"]["PATH"], "/usr/bin:/bin")
            self.assertEqual(call.kwargs["timeout"], 15)
            self.assertFalse(call.kwargs.get("shell", False))
        return code, data, run

    def test_status_state_mapping(self):
        cases = [
            (reply("inactive", "dead"), 0, "stopped", True),
            (reply("failed", "failed"), 0, "stopped", True),
            (reply("activating", "start"), 0, "unknown", False),
            (reply("deactivating", "stop"), 0, "unknown", False),
            (reply("active", "exited"), 0, "unknown", False),
            (reply(load="not-found"), 1, "unknown", False),
            (reply(returncode=1), 1, "unknown", False),
            (subprocess.CompletedProcess([], 0, "garbage PRIVATE", ""), 1, "unknown", False),
        ]
        for result, expected_code, state, control in cases:
            with self.subTest(result=result):
                code, data, run = self.invoke(["status"], [result])
                self.assertEqual(code, expected_code)
                self.assertEqual(data["state"], state)
                self.assertEqual(data["can_control"], control)
                self.assertEqual(bool(data["error"]), bool(expected_code))
                self.assertEqual(run.call_count, 1)

    def test_invalid_arguments_never_invoke_systemctl(self):
        for args in ([], ["restart"], ["--help"], ["status", "extra"], ["start; PRIVATE"]):
            with self.subTest(args=args):
                code, data, run = self.invoke(args, [reply()])
                self.assertNotEqual(code, 0)
                self.assertEqual(data["state"], "unknown")
                self.assertFalse(data["can_control"])
                self.assertTrue(data["error"])
                run.assert_not_called()

    def test_actions_require_verified_desired_state(self):
        stopped = reply("inactive", "dead")
        for action, before, after, state in (
            ("start", stopped, reply(), "running"),
            ("stop", reply(), stopped, "stopped"),
            ("start", reply(), reply(), "running"),
            ("stop", stopped, stopped, "stopped"),
        ):
            with self.subTest(action=action, state=state):
                code, data, run = self.invoke([action], [before, reply(), after])
                self.assertEqual(code, 0)
                self.assertEqual(data, {"state": state, "can_control": True, "error": ""})
                self.assertEqual([c.args[0] for c in run.call_args_list],
                                 [SHOW, ["/usr/bin/systemctl", "--user", action, UNIT], SHOW])

    def test_actions_reject_unavailable_or_transitioning_unit(self):
        for before in (reply(load="not-found"), reply("activating", "start"),
                       reply("deactivating", "stop"), reply(returncode=1)):
            for action in ("start", "stop"):
                with self.subTest(action=action, before=before):
                    code, data, run = self.invoke([action], [before])
                    self.assertNotEqual(code, 0)
                    self.assertFalse(data["can_control"])
                    self.assertTrue(data["error"])
                    self.assertEqual(run.call_count, 1)

    def test_action_final_state_mismatch_is_failure(self):
        for action, before, after in (
            ("start", reply("inactive", "dead"), reply("inactive", "dead")),
            ("stop", reply(), reply()),
            ("start", reply(), reply("activating", "start")),
            ("stop", reply(), reply(load="not-found")),
        ):
            with self.subTest(action=action, after=after):
                code, data, run = self.invoke([action], [before, reply(), after])
                self.assertNotEqual(code, 0)
                self.assertTrue(data["error"])
                self.assertEqual(run.call_count, 3)

    def test_subprocess_exceptions_return_safe_unknown_json(self):
        exceptions = [FileNotFoundError("PRIVATE path"), PermissionError("PRIVATE permission"),
                      subprocess.TimeoutExpired("PRIVATE command", 15, output="PRIVATE output"),
                      subprocess.CalledProcessError(1, "PRIVATE command", stderr="PRIVATE stderr"),
                      UnicodeError("PRIVATE decoding")]
        for failure in exceptions:
            for args, results in ((["status"], [failure]),
                                  (["start"], [reply(), failure, reply()]),
                                  (["stop"], [reply(), reply(), failure])):
                with self.subTest(args=args, failure=type(failure).__name__):
                    code, data, _ = self.invoke(args, results)
                    self.assertNotEqual(code, 0)
                    self.assertEqual(data["state"], "unknown")
                    self.assertFalse(data["can_control"])
                    self.assertTrue(data["error"])

    def test_action_command_failure_is_not_success_even_if_state_matches(self):
        for action, after in (("start", reply()), ("stop", reply("inactive", "dead"))):
            with self.subTest(action=action):
                code, data, run = self.invoke([action], [reply(), reply(returncode=1), after])
                self.assertNotEqual(code, 0)
                self.assertTrue(data["error"])
                self.assertEqual(run.call_count, 3)

    def test_status_running(self):
        code, data, run = self.invoke(["status"], [reply()])
        self.assertEqual(code, 0)
        self.assertEqual(data, {"state": "running", "can_control": True, "error": ""})
        self.assertEqual(run.call_args.args[0], SHOW)


if __name__ == "__main__":
    unittest.main()
