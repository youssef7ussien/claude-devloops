"""Runs that need no extra commands: no plan pause by default, decisions that continue the run,
`--review-plan`, the review prompt, and `devloops run`'s up-front tool check.

By default (`questions: accept-suggested`) a run plans, approves, and implements in one command.
`approve`, `retry`, and `replan` take no loop name (003 FR-009): each records its decision for the
loop that waits for it, then continues the whole run, unless `--no-continue`.
"""
import contextlib
import importlib.util
import io
import json
import os
import socket
import sys
import unittest
from unittest import mock

import helpers  # noqa: F401 - puts the package on sys.path
from devloops import cli, state
from stub_loop import StubLoopMixin
import test_run_command  # not `from ... import`: the base class would be collected here too
from test_suggested_answers import plan_with, steps

FAIL = {"DEVLOOPS_STUB": "fail"}


def default_questions(t):
    """Drop the test projects' `questions: ask`, so the packaged default applies."""
    path = os.path.join(t.root, ".devloops", "devloops.json")
    data = state.read_json(path)
    data["config"].pop("questions")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


class DefaultRunTest(StubLoopMixin, unittest.TestCase):
    def test_a_run_plans_and_implements_without_pausing(self):
        default_questions(self.t)
        self.scenario(steps(plan_with(("OQ1", "Port 8765."))))
        self.assertEqual(self.first_run(), 0, self.last_output)
        rs = self.run_state()
        self.assertEqual((rs["status"], rs["effective_config"]["questions"]),
                         ("completed", "accept-suggested"))
        self.assertEqual(rs["approval"]["action"], "auto-approve")
        self.assertEqual(rs["approval"]["accepted_suggestions"], ["OQ1"])
        report = self.read("outputs/final-report.md")
        # The decisions to review come before the results.
        self.assertLess(report.index("## Suggested answers accepted"), report.index("## Milestones"))
        self.assertLess(report.index("## Assumptions for review"), report.index("## Milestones"))

    def test_review_plan_pauses_after_the_plan(self):
        default_questions(self.t)
        self.assertEqual(self.first_run("--review-plan"), 10, self.last_output)
        self.assertEqual(self.run_state()["effective_config"]["questions"], "ask")
        self.assertIn("devloops approve", self.last_output)

    def test_a_question_without_a_suggestion_still_pauses(self):
        default_questions(self.t)
        self.scenario(steps(plan_with(("OQ1", ""))))
        self.assertEqual(self.first_run(), 10, self.last_output)
        self.assertIn("OQ1 has no suggested answer", self.last_output)


class DecisionsContinueTest(StubLoopMixin, unittest.TestCase):
    def test_approve_implements_the_plan_in_the_same_command(self):
        self.assertEqual(self.first_run(), 10, self.last_output)
        self.assertEqual(self.cli("approve"), 0, self.last_output)
        rs = self.run_state()
        self.assertEqual((rs["status"], rs["approval"]["action"]), ("completed", "approve"))
        self.assertEqual(self.steps_called(), ["plan", "implement", "implement"])

    def test_approve_no_continue_only_records(self):
        self.assertEqual(self.first_run(), 10, self.last_output)
        self.assertEqual(self.cli("approve", "--no-continue"), 0, self.last_output)
        self.assertEqual(self.run_state()["status"], "implementing")
        self.assertIn("run `devloops run` to implement it", self.last_output)
        self.assertEqual(self.steps_called(), ["plan"])

    def test_retry_grants_and_continues_without_a_reason(self):
        self.approved()
        self.assertEqual(self.cli("run", env=FAIL), 20, self.last_output)
        self.assertIn("devloops retry --milestone M01", self.last_output)
        self.assertEqual(self.cli("retry", "--milestone", "M01", "--trials", "1"),
                         0, self.last_output)
        rs = self.run_state()
        self.assertEqual(rs["status"], "completed")
        self.assertEqual(rs["grants"][-1]["reason"], "")
        # No reason, no guidance: the fix prompt gets nothing made up.
        self.assertNotIn("developer_guidance", self.context_of(self.calls("fix")[-1]))

    def test_a_questions_flag_with_no_continue_is_refused(self):
        self.assertEqual(self.first_run(), 10, self.last_output)
        self.assertEqual(self.cli("approve", "--no-continue", "--accept-suggested"),
                         2, self.last_output)
        self.assertEqual(self.run_state()["status"], "awaiting-approval")

    def test_a_missing_tool_refuses_a_continuing_approval(self):
        self.assertEqual(self.first_run(), 10, self.last_output)
        self.t.write_file(os.path.join("backend-dev", "loop.json"), json.dumps({
            "name": "backend-dev", "required_inputs": ["requirements"],
            "required_tools": ["no-such-tool-xyz"], "validator": "stub",
            "requires_openapi_path": False}), base=os.path.join(self.t.root, "loops"))
        self.assertEqual(self.cli("approve"), 30, self.last_output)
        # Not recorded: the run still awaits approval, and approves once the tool is there.
        self.assertEqual(self.run_state()["status"], "awaiting-approval")

    def test_a_refused_retry_runs_nothing(self):
        self.approved()
        before = len(self.t.fake_calls())
        self.assertEqual(self.cli("retry", "--milestone", "M01"), 2)
        self.assertEqual(len(self.t.fake_calls()), before)
        self.assertEqual(self.run_state()["status"], "implementing")

    def test_replan_continues_under_accept_suggested(self):
        self.scenario(steps(plan_with(("OQ1", "Port 8765.")),
                            replan={"structured_output": plan_with(("OQ1", "Port 8765."))}))
        self.assertEqual(self.first_run(), 10, self.last_output)   # the sandbox reviews plans
        self.assertEqual(self.cli("replan", "--accept-suggested"), 0,
                         self.last_output)
        rs = self.run_state()
        self.assertEqual((rs["status"], rs["approval"]["action"]), ("completed", "auto-approve"))
        self.assertEqual([t["kind"] for t in rs["planning"]["trials"]], ["plan", "replan"])

    def test_a_refused_replan_records_no_override(self):
        self.scenario(steps(plan_with(), replan={"structured_output": plan_with()}))
        self.assertEqual(self.first_run(), 10, self.last_output)
        for _ in range(2):  # planning trials 2 and 3 of 3
            self.assertEqual(self.cli("replan", "--no-continue"), 10,
                             self.last_output)
        self.assertEqual(self.cli("replan", "--accept-suggested"), 2,
                         self.last_output)
        self.assertEqual(self.events("config-override"), [])
        self.assertEqual(self.run_state()["effective_config"]["questions"], "ask")

    def test_replan_pauses_again_when_plans_are_reviewed(self):
        self.scenario(steps(plan_with(), replan={"structured_output": plan_with()}))
        self.assertEqual(self.first_run(), 10, self.last_output)
        self.assertEqual(self.cli("replan"), 10, self.last_output)
        self.assertEqual(self.run_state()["status"], "awaiting-approval")


class ReviewPromptTest(StubLoopMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        # In-process: register the temp repo's stub validator under the package imported here.
        spec = importlib.util.spec_from_file_location(
            "devloops.validators.stub",
            os.path.join(self.t.root, "loops", "shared", "devloops", "validators", "stub.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules[spec.name] = module
        self.addCleanup(sys.modules.pop, spec.name, None)

    def main(self, answers, *args):
        """Run `devloops args` as if in a terminal, answering the prompt with `answers`."""
        replies = iter(answers)

        def ask(_prompt=""):
            try:
                return next(replies)
            except StopIteration:
                raise EOFError
        out = io.StringIO()
        with mock.patch.dict(os.environ, dict(self.t.env, VISUAL="true", EDITOR="true"), clear=True), \
                mock.patch.object(cli, "_interactive", lambda args: not args.json), \
                mock.patch("builtins.input", ask), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(io.StringIO()):
            code = cli.main([*args, "--workspace", "us3"], kit=self.t.kit(),
                            project=self.t.project())
        return code, out.getvalue()

    def run_args(self):
        return ("run", "--requirements", self.prd, "--backend-target", self.t.target_dir)

    def test_approve_at_the_prompt_continues(self):
        code, out = self.main(["e", "a"], *self.run_args())
        self.assertEqual(code, 0, out)
        self.assertIn("backend-dev plan: 2 milestone(s), 0 question(s)", out)
        self.assertEqual(self.run_state()["status"], "completed")

    def test_quit_keeps_the_pause(self):
        code, out = self.main(["q"], *self.run_args())
        self.assertEqual(code, 10, out)
        self.assertIn("`devloops approve` approves it and continues", out)
        self.assertEqual(self.run_state()["status"], "awaiting-approval")

    def test_no_prompt_after_no_continue(self):
        self.assertEqual(self.main(["q"], *self.run_args())[0], 10)
        self.scenario({"replan": {"structured_output": plan_with(("OQ1", "Port 8765."))}})
        code, out = self.main(["a"], "replan", "--no-continue")
        self.assertEqual(code, 10, out)
        self.assertNotIn("[a]pprove", out)
        self.assertEqual(self.run_state()["status"], "awaiting-approval")

    def test_the_plan_line_counts_answers(self):
        self.scenario(steps(plan_with(("OQ1", "Port 8765."), ("OQ2", ""), ("OQ3", "SQLite."))))
        code, out = self.main(["q"], *self.run_args())
        self.assertEqual(code, 10, out)
        self.assertIn("3 question(s): 2 with a suggested answer, OQ2 with neither", out)

    def test_no_prompt_with_json(self):
        code, out = self.main(["a"], *self.run_args(), "--json")
        self.assertEqual(code, 10)
        self.assertEqual(json.loads(out)["loops"]["backend-dev"]["status"], "awaiting-approval")


class RunDecisionsTest(test_run_command.RunCommandTest):
    """Decisions without a loop name in a run of both loops (003 FR-009, FR-010). Reuses the run
    command's fixtures; its own tests are not run again here."""

    def run_cli(self, *args):
        code, out, err = self.t.run_cli([*args, "--workspace", test_run_command.WS])
        self.last_output = out + err
        return code

    def test_approve_continues_both_loops_and_review_plan_is_kept(self):
        self.assertEqual(self.run_cmd("--review-plan"), 10, self.last_output)
        # One command: the backend is built, then the frontend's plan pauses (still reviewed).
        self.assertEqual(self.run_cli("approve", "--json"), 10, self.last_output)
        self.assertEqual(json.loads(self.last_output)["decision"],
                         {"command": "approve", "loop": "backend-dev"})
        self.assertEqual(self.run_state("backend-dev")["status"], "completed")
        self.assertEqual(self.run_state("frontend-dev")["status"], "awaiting-approval")
        self.assertEqual(self.orch_state()["status"], "paused")
        # The same command now applies to the frontend: the loop that awaits approval.
        self.assertEqual(self.run_cli("approve"), 0, self.last_output)
        self.assertEqual(self.orch_state()["status"], "completed")
        self.assertEqual([s["status"] for s in self.orch_state()["steps"]],
                         ["completed", "completed"])

    def test_replan_applies_to_the_loop_that_awaits_approval(self):
        self.scenario(replan={"structured_output": test_run_command.backend_plan()})
        self.assertEqual(self.run_cmd("--review-plan"), 10, self.last_output)
        self.assertEqual(self.run_cli("replan"), 10, self.last_output)
        rs = self.run_state("backend-dev")
        self.assertEqual(rs["status"], "awaiting-approval")
        self.assertEqual([t["kind"] for t in rs["planning"]["trials"]], ["plan", "replan"])
        self.assertIsNone(self.run_state("frontend-dev"))

    def test_retry_applies_to_the_loop_stopped_on_failure(self):
        self.assertEqual(self.run_cmd(), 10, self.last_output)
        self.approve("backend-dev")
        self.assertEqual(self.run_cmd(env={"DEVLOOPS_STUB": "fail"}), 20, self.last_output)
        self.assertIn("devloops retry --milestone M01", self.last_output)
        # The grant goes to backend-dev, then the whole run continues to the frontend's plan.
        self.assertEqual(self.run_cli("retry", "--milestone", "M01", "--trials", "1"), 10,
                         self.last_output)
        self.assertEqual(self.run_state("backend-dev")["status"], "completed")
        self.assertEqual(self.run_state("backend-dev")["grants"][-1]["milestone_id"], "M01")
        self.assertEqual(self.run_state("frontend-dev")["status"], "awaiting-approval")

    def test_approve_when_nothing_awaits_approval_changes_nothing(self):
        self.assertEqual(self.run_cmd(), 10, self.last_output)
        self.approve("backend-dev")
        before = (self.orch_state(), self.run_state("backend-dev"), len(self.t.fake_calls()))
        for command in ("approve", "replan"):
            self.assertEqual(self.run_cli(command), 2, self.last_output)
            self.assertIn("nothing awaits approval (run: paused)", self.last_output)
        self.assertEqual((self.orch_state(), self.run_state("backend-dev"),
                          len(self.t.fake_calls())), before)

    def test_retry_when_no_loop_is_stopped_on_failure_changes_nothing(self):
        self.assertEqual(self.run_cmd(), 10, self.last_output)
        before = (self.orch_state(), self.run_state("backend-dev"))
        self.assertEqual(self.run_cli("retry", "--milestone", "M01"), 2, self.last_output)
        self.assertIn("no loop is stopped on failure (run: paused)", self.last_output)
        self.assertEqual((self.orch_state(), self.run_state("backend-dev")), before)

    def test_no_continue_records_and_the_next_run_continues(self):
        self.assertEqual(self.run_cmd(), 10, self.last_output)
        self.assertEqual(self.run_cli("approve", "--no-continue"), 0, self.last_output)
        self.assertEqual(self.run_state("backend-dev")["status"], "implementing")
        self.assertEqual(self.steps_called(), ["plan"])  # nothing ran
        self.assertIn("run `devloops run` to implement it", self.last_output)
        code, out, err = self.t.run_cli(["run", "--workspace", test_run_command.WS])
        self.assertEqual(code, 10, out + err)  # the backend built, the frontend planned
        self.assertEqual(self.run_state("backend-dev")["status"], "completed")
        self.assertEqual(self.run_state("frontend-dev")["status"], "awaiting-approval")

    def test_a_refused_decision_leaves_the_run_as_it_was(self):
        self.assertEqual(self.run_cmd("--review-plan"), 10, self.last_output)
        before = self.orch_state()
        self.assertEqual(self.run_cli("approve", "--no-continue", "--accept-suggested"), 2)
        self.assertEqual(self.orch_state(), before)   # --accept-suggested was not recorded

    def test_a_decision_that_meets_a_lock_leaves_the_run_as_it_was(self):
        self.assertEqual(self.run_cmd("--review-plan"), 10, self.last_output)
        before = self.orch_state()
        lock = self.loop_path("backend-dev", "state", "lock")
        with open(lock, "w", encoding="utf-8") as f:   # a live driver: this test's process
            json.dump({"pid": os.getpid(), "host": socket.gethostname(),
                       "started_at": "2026-10-07T00:00:00.000Z"}, f)
        self.assertEqual(self.run_cli("approve"), 40, self.last_output)
        self.assertEqual(self.orch_state(), before)

    def test_a_refused_decision_records_no_new_target(self):
        # The backend pauses in a backend-only project; then the project adds a frontend.
        self.t.make_project(self.t.root, {"workspaces_dir": "workspaces", "targets": {
            "backend-dev": "backend", "frontend-dev": None}})
        code, out, err = self.t.run_cli(["run", "--workspace", test_run_command.WS,
                                         "--requirements", self.prd])
        self.assertEqual(code, 10, out + err)
        self.t.make_project(self.t.root, {"workspaces_dir": "workspaces", "targets": {
            "backend-dev": "backend", "frontend-dev": "frontend"}})
        ws_json = os.path.join(self.t.workspace_dir, "workspace.json")
        before = state.read_json(ws_json)
        lock = self.loop_path("backend-dev", "state", "lock")
        with open(lock, "w", encoding="utf-8") as f:   # a live driver: this test's process
            json.dump({"pid": os.getpid(), "host": socket.gethostname(),
                       "started_at": "2026-10-07T00:00:00.000Z"}, f)
        self.assertEqual(self.run_cli("approve"), 40, self.last_output)
        self.assertEqual(state.read_json(ws_json), before)  # FR-010: nothing changed
        self.assertNotIn("frontend-dev", before["targets"])
        self.assertFalse(os.path.exists(os.path.join(self.t.root, "frontend")))
        # Once decided, the frontend's target is recorded when it starts.
        os.remove(lock)
        self.assertEqual(self.run_cli("approve"), 10, self.last_output)
        self.assertEqual(state.read_json(ws_json)["targets"]["frontend-dev"], "frontend")

    def test_an_older_record_keeps_the_backends_mode_for_the_frontend(self):
        self.assertEqual(self.run_cmd("--review-plan"), 10, self.last_output)
        path = os.path.join(self.t.workspace_dir, "run", "state.json")
        data = self.orch_state()
        data.pop("questions")   # as recorded before the mode was
        state.write_json_atomic(path, data)
        self.assertEqual(self.run_cli("approve"), 10, self.last_output)
        self.assertEqual(self.run_state("frontend-dev")["status"], "awaiting-approval")

    def test_approve_no_continue_updates_the_run_step(self):
        self.assertEqual(self.run_cmd("--review-plan"), 10, self.last_output)
        self.assertEqual(self.run_cli("approve", "--no-continue"), 0, self.last_output)
        self.assertEqual(self.orch_state()["steps"][0]["status"], "implementing")
        with open(os.path.join(self.t.workspace_dir, "run", "progress.md"),
                  encoding="utf-8") as f:
            self.assertNotIn("then run `devloops approve`", f.read())

    def test_a_missing_frontend_tool_stops_before_the_backend_runs(self):
        loops = os.path.join(self.t.root, "loops")
        self.t.write_file(os.path.join("frontend-dev", "loop.json"), json.dumps({
            "name": "frontend-dev", "required_inputs": ["requirements", "api_spec"],
            "required_tools": ["no-such-tool-xyz"], "validator": "orchstub",
            "requires_openapi_path": False}), base=loops)
        self.assertEqual(self.run_cmd(), 30, self.last_output)
        self.assertIn("frontend-dev: required tool 'no-such-tool-xyz' is not on PATH",
                      self.last_output)
        self.assertEqual(self.t.fake_calls(), [])
        self.assertIsNone(self.run_state("backend-dev"))


# The base class's tests run in test_run_command; only the new ones run here.
for _name in [n for n in vars(test_run_command.RunCommandTest) if n.startswith("test_")]:
    setattr(RunDecisionsTest, _name, None)


if __name__ == "__main__":
    unittest.main()
