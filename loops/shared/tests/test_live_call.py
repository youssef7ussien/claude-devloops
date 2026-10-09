"""The running call as `<loop>/state/live.json`, and `api/now` built from it (specs/005-dashboard-redesign
data-model Live call and Now, research R-8, FR-016)."""
import copy
import json
import os
import socket
import unittest
from unittest import mock

import helpers  # noqa: F401 - puts the package on sys.path
import samples
from devloops import claude, dashboard, progress, state, workspace
from devloops.redact import Redactor
from stub_loop import WS, StubLoopMixin
from test_claude import IMPLEMENTED

FIELDS = {"loop", "step", "milestone_id", "trial", "model", "session_id", "started_at", "pid",
          "tools"}


class LiveCallTest(unittest.TestCase):
    def setUp(self):
        self.t = helpers.TempEnv().__enter__()
        self.addCleanup(self.t.__exit__, None, None, None)
        prompts = os.path.join(self.t.root, "loops", "shared", "prompts")
        self.t.write_file("common.md", "COMMON\n", base=prompts)
        for step in claude.STEPS:
            self.t.write_file(os.path.join("steps", f"{step}.md"), f"STEP {step}\n", base=prompts)
        self.t.write_file("Loop-instructions.md", "LOOP\n",
                          base=os.path.join(self.t.root, "loops", "backend-dev"))
        self.loop_dir = os.path.join(self.t.workspace_dir, "backend-dev")
        self.path = os.path.join(self.loop_dir, "state", progress.LIVE_NAME)
        self.t.write_scenario({"steps": {}})  # the runner copies the environment that names it
        config = dict(samples.config(), secrets={"env": [], "literals": ["s3cr3t"]})
        self.runner = claude.ClaudeRunner(self.t.kit(), "backend-dev", self.loop_dir, config,
                                          Redactor(config), {"invocation_count": 0},
                                          env=self.t.env)

    def call(self, step, answer):
        """Run one call, returning every document written to live.json during it."""
        written, write = [], progress.LiveCall.write

        def recording(live):
            written.append(copy.deepcopy(live.doc))
            write(live)
        self.t.write_scenario({"steps": {step: answer}})
        with mock.patch.object(progress.LiveCall, "write", recording):
            try:
                self.runner.call(step, {"milestone": "M01"}, self.t.target_dir,
                                 milestone_id="M01", trial=2)
            finally:
                self.written = written
        return written

    def test_written_during_the_call_and_removed_after(self):
        written = self.call("implement", dict({"structured_output": IMPLEMENTED}, tool_uses=[
            {"name": "Bash", "input": {"command": "pytest -q  # s3cr3t"}},
            {"name": "Edit", "input": {"file_path": os.path.join(self.t.target_dir, "app.py")}}]))
        self.assertEqual(len(written), 3)  # the start, then one per tool
        first = written[0]
        self.assertEqual(set(first), FIELDS)
        self.assertEqual((first["loop"], first["step"], first["milestone_id"], first["trial"],
                          first["pid"], first["tools"]),
                         ("backend-dev", "implement", "M01", 2, os.getpid(), []))
        record = state.read_jsonl(os.path.join(self.loop_dir, "state", "invocations.jsonl"))[-1]
        self.assertEqual(first["session_id"], record["session_id"])
        self.assertEqual([[t["summary"] for t in doc["tools"]] for doc in written[1:]],
                         [["Bash: pytest -q  # ***"], ["Bash: pytest -q  # ***", "Edit app.py"]])
        self.assertEqual([t["name"] for t in written[-1]["tools"]], ["Bash", "Edit"])
        self.assertTrue(all(t["at"].endswith("Z") for t in written[-1]["tools"]))
        self.assertFalse(os.path.exists(self.path))

    def test_removed_after_a_failed_call(self):
        self.call("implement", {"is_error": True, "result": "boom", "tool_uses": ["Read"]})
        self.assertEqual(len(self.written), 2)
        self.assertFalse(os.path.exists(self.path))
        self.runner.env["DEVLOOPS_CLAUDE_BIN"] = os.path.join(self.t.base, "no-such-claude")
        with self.assertRaises(FileNotFoundError):
            self.call("fix", {"structured_output": IMPLEMENTED})
        self.assertEqual(len(self.written), 1)
        self.assertFalse(os.path.exists(self.path))

    def test_keeps_the_last_tools(self):
        live = progress.LiveCall()
        live.start(self.loop_dir, "backend-dev", "fix", "M01", 1, "m", "s")
        for i in range(progress.LIVE_TOOLS + 50):
            live.tool("Bash", {"command": f"echo {i}"})
        with open(self.path, encoding="utf-8") as f:
            tools = json.load(f)["tools"]
        self.assertEqual(len(tools), progress.LIVE_TOOLS)
        self.assertEqual((tools[0]["summary"], tools[-1]["summary"]),
                         ("Bash: echo 50", f"Bash: echo {progress.LIVE_TOOLS + 49}"))
        live.end()
        live.tool("Bash", {"command": "after"})  # a tool reported after the end writes nothing
        self.assertFalse(os.path.exists(self.path))

    def test_a_write_that_fails_changes_nothing(self):
        live = progress.LiveCall()
        blocker = os.path.join(self.t.base, "file")
        with open(blocker, "w") as f:
            f.write("not a folder")
        live.start(blocker, "backend-dev", "plan")  # state/ cannot be made under a file
        live.tool("Read")
        live.end()


class NowTest(StubLoopMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.first_run(), 10, self.last_output)  # awaiting approval
        self.ws = workspace.open_workspace(WS, self.t.project(), self.t.kit(), create=False)
        self.state_dir = os.path.join(self.ws.loop_dir("backend-dev"), "state")

    def now(self):
        return dashboard.now(dashboard.Context(self.ws, self.t.env))

    def lock(self, pid):
        state.write_json_atomic(os.path.join(self.state_dir, "lock"),
                                {"pid": pid, "host": socket.gethostname()})

    def live(self):
        live = progress.LiveCall()
        live.start(self.ws.loop_dir("backend-dev"), "backend-dev", "implement", "M01", 1,
                   "opus", "sess-1")
        live.tool("Bash", {"command": "pytest"})
        return live

    def test_idle_without_a_file(self):
        now = self.now()
        self.assertEqual((now["running"], now["status"], now["loop"], now["waiting_for"],
                          now["busy"]),
                         (False, "awaiting-approval", "backend-dev", "approval", []))
        self.assertIn("devloops approve", now["next_action"]["text"])

    def test_running_while_the_lock_is_held(self):
        self.live()
        self.lock(os.getpid())
        now = self.now()
        self.assertTrue(now["running"])
        self.assertEqual((now["call"]["step"], now["call"]["milestone_id"], now["call"]["model"],
                          [t["summary"] for t in now["call"]["tools"]]),
                         ("implement", "M01", "opus", ["Bash: pytest"]))
        self.assertGreaterEqual(now["elapsed_seconds"], 0)
        self.assertNotIn("status", now)

    def test_a_stale_file_is_ignored(self):
        self.live()  # left by a crash: no lock, or the lock of a process that is gone
        self.assertFalse(self.now()["running"])
        self.lock(2 ** 22 + 12345)
        now = self.now()
        self.assertEqual((now["running"], now["waiting_for"]), (False, "approval"))
        # A later command holds the lock: the file is still not its call
        self.lock(os.getppid())
        now = self.now()
        self.assertEqual((now["running"], now["busy"]), (False, ["backend-dev"]))

    def test_the_file_is_not_listed(self):
        self.live()
        ctx = dashboard.Context(self.ws, self.t.env)
        self.assertTrue(ctx.file_ref("backend-dev/state/live.json")["missing"])
        self.assertTrue(ctx.file_ref("backend-dev/state/run.json").get("id"))

    def test_what_a_stopped_loop_waits_for(self):
        def d(status, **reason):
            return {"status": status, "status_reason": reason}
        self.assertEqual(dashboard._waiting_for(d("awaiting-approval")), "approval")
        self.assertEqual(dashboard._waiting_for(
            d("stopped-on-failure", code="needs-input", milestone_id="M01")), "questions")
        self.assertEqual(dashboard._waiting_for(
            d("stopped-on-failure", code="trials-exhausted", milestone_id="M01")), "retry")
        self.assertIsNone(dashboard._waiting_for(  # `retry` is refused: the cap is raised instead
            d("stopped-on-failure", code="invocation-cap", milestone_id="M01")))

    def test_a_command_between_calls_has_no_next_action(self):
        self.lock(os.getpid())
        now = self.now()
        self.assertEqual((now["running"], now["busy"], now["next_action"], now["waiting_for"]),
                         (False, ["backend-dev"], None, None))


if __name__ == "__main__":
    unittest.main()
