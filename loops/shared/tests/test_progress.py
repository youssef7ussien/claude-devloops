"""Progress while a command runs: lines on stderr, `state/run.log`, and the dashboard hints."""
import io
import os
import re
import time
import unittest
from unittest import mock

import helpers  # noqa: F401 - puts the package on sys.path
import samples
from devloops import progress
from stub_loop import WS, StubLoopMixin, implemented

LINE = re.compile(r"^\d\d:\d\d:\d\d ")


class ProgressUnitTest(unittest.TestCase):
    def setUp(self):
        t = helpers.TempEnv().__enter__()
        self.addCleanup(t.__exit__, None, None, None)
        self.out = io.StringIO()
        self.log = os.path.join(t.base, "state", "run.log")

    def make(self, level="normal", tty=False):
        return progress.Progress(level, stream=self.out, env={}, tty=tty)

    def lines(self):
        return self.out.getvalue().splitlines()

    def log_lines(self):
        with open(self.log, encoding="utf-8") as f:
            return f.read().splitlines()

    def test_an_event_is_one_line_on_the_stream_and_in_the_log(self):
        p = self.make()
        p.event("backend-dev", "validation-failed", "trial 1 failed: C4", "M01", 1, self.log)
        [line] = self.lines()
        self.assertRegex(line, r"^\d\d:\d\d:\d\d backend-dev M01 #1  ✕ trial 1 failed: C4$")
        [logged] = self.log_lines()
        self.assertRegex(logged, r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d backend-dev M01 #1  "
                                 r"trial 1 failed: C4$")

    def test_a_call_starts_lists_its_tools_and_ends_with_its_cost(self):
        p = self.make("verbose")
        p.call_started("backend-dev", "implement", "M01", 1, "sonnet", self.log, "/t")
        p.tool_use("Bash", {"command": "pytest -q\nsecond line"})
        p.tool_use("Edit", {"file_path": "/t/app/models.py"})
        p.call_ended("implement", 125, 1.234)
        messages = [line.split("  ", 1)[1] for line in self.lines()]
        self.assertEqual(messages, ["implementing (sonnet)", "  Bash: pytest -q",
                                    "  Edit app/models.py",
                                    "implement done (2m05s, $1.23, 2 tool call(s))"])
        self.assertEqual(len(self.log_lines()), 4)

    def test_normal_level_logs_tools_without_printing_them(self):
        p = self.make()
        p.call_started("backend-dev", "fix", "M01", 2, None, self.log)
        p.tool_use("Read", {"file_path": "/x/a.py"})
        p.call_ended("fix", 3, None, failure="timeout: no result")
        messages = [line.split("  ", 1)[1] for line in self.lines()]
        self.assertEqual(messages, ["fixing", "■ fix failed: timeout: no result (3s, 1 tool call(s))"])
        self.assertIn("  Read /x/a.py", self.log_lines()[1])

    def test_quiet_prints_nothing_but_still_logs(self):
        p = self.make("quiet")
        p.event("backend-dev", "completed", "all 2 milestone(s) achieved", log_path=self.log)
        p.note("dashboard: x")
        self.assertEqual(self.out.getvalue(), "")
        self.assertEqual(len(self.log_lines()), 1)

    def test_without_a_terminal_a_long_call_prints_a_still_line(self):
        p = self.make()
        with mock.patch.object(progress, "HEARTBEAT_SECONDS", 0.5):
            p.call_started("backend-dev", "implement", "M01", 1, None, self.log)
            p.tool_use("Bash", {"command": "make test"})
            time.sleep(2.2)
            p.call_ended("implement", 2)
        still = [line for line in self.lines() if "still implementing" in line]
        self.assertTrue(still, self.lines())
        self.assertIn("1 tool call(s) · last: Bash: make test", still[0])
        self.assertNotIn("\x1b", self.out.getvalue())  # no terminal: no escapes, no colors

    def test_the_log_gets_the_still_line_even_when_quiet(self):
        p = self.make("quiet")
        with mock.patch.object(progress, "HEARTBEAT_SECONDS", 0.5):
            p.call_started("backend-dev", "implement", "M01", 1, None, self.log)
            time.sleep(1.8)
            p.call_ended("implement", 2)
        self.assertEqual(self.out.getvalue(), "")
        self.assertTrue(any("still implementing" in line for line in self.log_lines()),
                        self.log_lines())

    def test_a_terminal_gets_a_status_line_redrawn_in_place(self):
        p = self.make(tty=True)
        p.call_started("backend-dev", "plan", None, 1, "opus", self.log)
        time.sleep(0.6)
        p.call_ended("plan", 1, 0.5)
        text = self.out.getvalue()
        self.assertIn("\r\x1b[2K", text)  # the status line is cleared and redrawn
        self.assertIn("planning · ", text)
        # The status line is gone once the call ends; its last line is the call's result.
        self.assertIn("plan done (1s, $0.50)", text.rsplit("\r\x1b[2K", 1)[1])

    def test_no_color_is_respected(self):
        p = progress.Progress("normal", stream=self.out, env={"NO_COLOR": "1"}, tty=True)
        p.event("backend-dev", "completed", "done")
        self.assertNotIn("\x1b[", self.out.getvalue())

    def test_tool_summaries(self):
        cases = [("Bash", {"command": "ls -la"}, "Bash: ls -la"),
                 ("Write", {"file_path": "/repo/app/x.py"}, "Write app/x.py"),
                 ("Read", {"file_path": "/elsewhere/y.md"}, "Read /elsewhere/y.md"),
                 ("Grep", {"pattern": "TODO"}, "Grep TODO"),
                 ("mcp__playwright__browser_click", {}, "browser_click"),
                 ("TodoWrite", None, "TodoWrite")]
        for name, tool_input, expected in cases:
            self.assertEqual(progress.tool_summary(name, tool_input, "/repo"), expected)


class ProgressCommandTest(StubLoopMixin, unittest.TestCase):
    def run_logged(self):
        with open(self.path(os.path.join("state", "run.log")), encoding="utf-8") as f:
            return f.read()

    def stderr_of(self, *args, env=None):
        code, out, err = self.t.run_cli([*args, "--workspace", WS], extra_env=env)
        self.last_output = out + err
        return code, out, err

    def test_a_run_prints_each_step_and_logs_it(self):
        self.scenario({"plan": {"structured_output": samples.plan()},
                       "implement": [dict(implemented("M01-T01"), tool_uses=[
                                         {"name": "Edit", "input": {"file_path": "app.py"}}]),
                                     implemented("M02-T01")]})
        self.t.make_project(self.t.root, {"workspaces_dir": "workspaces",
                                          "config": {"questions": "accept-suggested"}})
        code, out, err = self.stderr_of("run", "backend-dev", "--requirements", self.prd,
                                        "--target", self.t.target_dir)
        self.assertEqual(code, 0, self.last_output)
        lines = err.splitlines()
        messages = [line.split("  ", 1)[1] for line in lines if LINE.match(line)]
        for expected in ("first run", "planning", "plan done (0s, $0.01)", "trial 1 (implement)",
                         "implementing", "validating", "✓ trial 1 passed",
                         "✓ milestone achieved: M02 Create items", "■ all 2 milestone(s) achieved"):
            self.assertIn(expected, messages, err)
        self.assertNotIn("  Edit app.py", messages)  # tools only with --verbose
        # The hints: where to look while it runs, then the summary on stdout.
        self.assertIn(f"files and conversations: devloops dashboard --serve --workspace {WS}", err)
        self.assertIn(f"log: {self.path(os.path.join('state', 'run.log'))}", err)
        self.assertIn(f"dashboard: {os.path.join(self.t.workspace_dir, 'dashboard.html')}", out)
        self.assertIn("files and conversations: devloops dashboard --serve", out)
        # Everything printed is in the log too, tools included; the log has no colors.
        logged = self.run_logged()
        for expected in ("first run", "implementing", "  Edit app.py", "all 2 milestone(s)"):
            self.assertIn(expected, logged)
        self.assertNotIn("\x1b", logged)
        # Writing the log during a call is not a write outside the target.
        self.assertEqual(self.run_state()["status"], "completed")

    def test_verbose_prints_each_tool(self):
        self.scenario({"plan": {"structured_output": samples.plan()},
                       "implement": [dict(implemented("M01-T01"), tool_uses=[
                                         {"name": "Bash", "input": {"command": "pytest -q"}}]),
                                     implemented("M02-T01")]})
        self.approved("--quiet")
        _, _, err = self.stderr_of("run", "backend-dev", "--verbose")
        self.assertIn("  Bash: pytest -q", err)

    def test_quiet_and_json_print_no_progress(self):
        for flag in ("--quiet", "--json"):
            with self.subTest(flag=flag):
                self.t.write_scenario({"steps": {"plan": {"structured_output": samples.plan()}}})
                code, _, err = self.stderr_of("run", "backend-dev", "--requirements", self.prd,
                                                "--target", self.t.target_dir, flag)
                self.assertEqual(code, 10, self.last_output)
                self.assertNotRegex(err, r"(?m)^\d\d:\d\d:\d\d ")
                self.assertIn("planning", self.run_logged())


if __name__ == "__main__":
    unittest.main()
