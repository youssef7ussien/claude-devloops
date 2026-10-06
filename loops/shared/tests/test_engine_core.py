"""The shared engine end to end, through `bin/devloops`, with fake Claude and a stub validator."""
import json
import os
import unittest

import helpers
import samples
from devloops import schema, state

WS = "core"

STUB = '''"""Test-only validator: every criterion passes unless DEVLOOPS_STUB says otherwise."""
import os


def validate(ctx):
    mode = os.environ.get("DEVLOOPS_STUB", "pass")
    if mode == "decode-error":  # an exception with an unrelated `.reason` attribute
        b"\\xff".decode("utf-8")
    if mode == "call-failed":
        from devloops.claude import CallFailed
        raise CallFailed("timeout", "no result within invocation_timeout_seconds=1")
    passed = mode == "pass"
    os.makedirs(ctx.evidence_dir, exist_ok=True)
    with open(os.path.join(ctx.evidence_dir, "stub.txt"), "w") as f:
        f.write("stub evidence")
    return {
        "kind": "curl",
        "criteria": [{"criterion_id": c["id"], "passed": passed, "observed": "stub",
                      "evidence": ["evidence/stub.txt"]}
                     for c in ctx.milestone["acceptance_criteria"]],
        "contract": {"passed": True, "unmatched_operations": []},
        "unit_tests": {"enabled": False},
    }
'''


def implemented(task_id):
    return {"structured_output": {
        "tasks": [{"task_id": task_id, "status": "implemented", "note": "done"}],
        "assumptions": [{"text": f"assumed something for {task_id}", "affects": [task_id]}],
        "needs_input": [], "files_changed": ["app.py"]},
        "writes": [{"path": "app.py", "content": f"# {task_id}\n", "tool": "Write"}]}


class EngineCoreTest(unittest.TestCase):
    def setUp(self):
        self.t = helpers.TempEnv(workspace=WS).__enter__()
        self.addCleanup(self.t.__exit__, None, None, None)
        loops = os.path.join(self.t.root, "loops")
        self.t.write_file(os.path.join("backend-dev", "loop.json"), json.dumps({
            "name": "backend-dev", "required_inputs": ["requirements"], "required_tools": [],
            "validator": "stub", "requires_openapi_path": False}), base=loops)
        self.t.write_file(os.path.join("backend-dev", "Loop-instructions.md"),
                          "Backend loop (test).\n", base=loops)
        self.t.write_file(os.path.join("shared", "devloops", "validators", "stub.py"), STUB,
                          base=loops)
        self.prd = self.t.write_file("prd.md", "# PRD\n\n- FR-1 list items\n- FR-2 create items\n")
        self.loop_dir = os.path.join(self.t.workspace_dir, "backend-dev")
        self.scenario({"plan": {"structured_output": samples.plan()},
                       "implement": [implemented("M01-T01"), implemented("M02-T01")]})

    def scenario(self, steps):
        self.t.write_scenario({"steps": steps})

    def cli(self, *args, env=None):
        code, out, err = self.t.run_cli([*args, "--workspace", WS], extra_env=env)
        self.last_output = out + err
        return code

    def first_run(self, *extra, env=None):
        return self.cli("run", "backend-dev", "--requirements", self.prd, "--target",
                        self.t.target_dir, *extra, env=env)

    def run_state(self):
        return state.read_json(os.path.join(self.loop_dir, "state", "run.json"))

    def read(self, relpath):
        with open(os.path.join(self.loop_dir, relpath), encoding="utf-8") as f:
            return f.read()

    def trial(self, mid, n):
        return state.read_json(os.path.join(self.loop_dir, "state", "milestones", mid, "trials",
                                            str(n), "trial.json"))

    def steps_called(self):
        return [c["step"] for c in self.t.fake_calls()]

    # --- the happy path ---

    def test_plan_pauses_for_approval(self):
        self.assertEqual(self.first_run(), 10, self.last_output)
        rs = self.run_state()
        self.assertEqual(rs["status"], "awaiting-approval")
        self.assertEqual(schema.validate(rs, "run-state.schema.json"), [])
        self.assertEqual(self.steps_called(), ["plan"])
        for name in ("milestone-01-list-items.md", "milestone-02-create-items.md",
                     "open-questions.md", "plan-summary.md"):
            self.assertTrue(os.path.exists(os.path.join(self.loop_dir, "outputs", name)), name)
        self.assertIn("_No open questions._", self.read("outputs/open-questions.md"))
        self.assertEqual(rs["milestones"]["M01"], {"status": "pending",
                                                   "tasks": {"M01-T01": "pending"}, "trials": [],
                                                   "started_at": None, "ended_at": None})
        # A second run while awaiting approval makes no call and still exits 10.
        self.assertEqual(self.cli("run", "backend-dev"), 10)
        self.assertEqual(self.steps_called(), ["plan"])

    def test_approve_then_run_completes(self):
        self.assertEqual(self.first_run(), 10)
        self.assertEqual(self.cli("approve", "backend-dev"), 0, self.last_output)
        rs = self.run_state()
        self.assertEqual(rs["status"], "implementing")
        self.assertEqual(rs["approval"]["action"], "approve")
        self.assertEqual(len(rs["approval"]["answers_sha256"]), 64)

        self.assertEqual(self.cli("run", "backend-dev"), 0, self.last_output)
        rs = self.run_state()
        self.assertEqual(rs["status"], "completed")
        self.assertEqual(self.steps_called(), ["plan", "implement", "implement"])
        self.assertEqual({m: s["status"] for m, s in rs["milestones"].items()},
                         {"M01": "achieved", "M02": "achieved"})
        self.assertIn("- [x] **M01-T01**", self.read("outputs/milestone-01-list-items.md"))
        self.assertIn("assumed something for M01-T01",
                      self.read("outputs/milestone-01-list-items.md"))
        progress = self.read("progress.md")
        row = next(line for line in progress.splitlines() if line.startswith("| M01 "))
        self.assertIn("| 1200 | 300 | 0 | 800 | 0.0100 |", row)
        report = self.read("outputs/final-report.md")
        self.assertIn("**Outcome**: completed", report)
        self.assertIn("assumed something for M02-T01", report)
        vr = state.read_json(os.path.join(self.loop_dir, "state", "milestones", "M01", "trials",
                                          "1", "validation.json"))
        self.assertTrue(vr["passed"])
        self.assertEqual(vr["boundary"], {"passed": True, "violations": []})
        with open(os.path.join(self.t.target_dir, "app.py")) as f:
            self.assertEqual(f.read(), "# M02-T01\n")

        # FR-029: a completed run makes no calls and changes nothing.
        before = self.read("state/run.json")
        self.assertEqual(self.cli("run", "backend-dev"), 0)
        self.assertEqual(self.steps_called(), ["plan", "implement", "implement"])
        self.assertEqual(self.read("state/run.json"), before)

    def test_fix_prompt_carries_the_previous_failure_and_only_open_tasks(self):
        self.assertEqual(self.first_run(), 10)
        self.cli("approve", "backend-dev")
        self.scenario({"implement": implemented("M01-T01"), "fix": implemented("M01-T01")})
        self.assertEqual(self.cli("run", "backend-dev", env={"DEVLOOPS_STUB": "fail"}), 20)
        fix_prompt = [c for c in self.t.fake_calls() if c["step"] == "fix"][0]["prompt"]
        context = json.loads(fix_prompt.split("```json\n", 1)[1].rsplit("\n```", 1)[0])
        self.assertEqual(context["previous_failure"]["trial"], 1)
        self.assertEqual(context["previous_failure"]["reason"], "validation-failed")
        self.assertTrue(context["previous_failure"]["validation_path"].endswith(
            os.path.join("M01", "trials", "1", "validation.json")))
        self.assertEqual([t["id"] for t in context["milestone"]["tasks"]], ["M01-T01"])

    # --- planning trials ---

    def test_invalid_plan_counts_as_a_planning_trial(self):
        bad = samples.plan()
        bad["milestones"][0]["tasks"][0]["requirement_refs"] = ["FR-404"]
        self.scenario({"plan": [{"structured_output": bad},
                                {"structured_output": samples.plan()}]})
        self.assertEqual(self.first_run(), 10, self.last_output)
        trials = self.run_state()["planning"]["trials"]
        self.assertEqual([t["status"] for t in trials], ["failed", "passed"])
        self.assertEqual(trials[0]["failure"]["reason"], "invalid-output")
        self.assertIn("FR-404", trials[0]["failure"]["detail"])
        second_prompt = self.t.fake_calls()[1]["prompt"]
        self.assertIn('"previous_attempt"', second_prompt)
        self.assertIn("FR-404", second_prompt)

    def test_planning_trials_exhausted(self):
        self.scenario({"plan": {"structured_output": {"milestones": []}}})
        self.assertEqual(self.first_run("--max-trials", "2"), 20)
        rs = self.run_state()
        self.assertEqual(rs["status"], "stopped-on-failure")
        self.assertEqual(rs["status_reason"]["code"], "planning-trials-exhausted")
        self.assertEqual(len(self.t.fake_calls()), 2)
        self.assertEqual(self.cli("run", "backend-dev"), 20)  # terminal: no further calls
        self.assertEqual(len(self.t.fake_calls()), 2)

    # --- validation is the driver's, never the model's ---

    def test_model_claims_are_never_a_pass(self):
        self.assertEqual(self.first_run(), 10)
        self.cli("approve", "backend-dev")
        self.scenario({"implement": implemented("M01-T01"), "fix": implemented("M01-T01")})
        self.assertEqual(self.cli("run", "backend-dev", env={"DEVLOOPS_STUB": "fail"}), 20,
                         self.last_output)
        rs = self.run_state()
        self.assertEqual(rs["status_reason"]["code"], "trials-exhausted")
        self.assertEqual(rs["status_reason"]["milestone_id"], "M01")
        m1 = rs["milestones"]["M01"]
        self.assertEqual(m1["status"], "failed")
        self.assertEqual(m1["tasks"], {"M01-T01": "failed"})
        self.assertEqual([t["status"] for t in m1["trials"]], ["failed"] * 3)
        self.assertEqual(rs["milestones"]["M02"]["status"], "pending")
        self.assertEqual(self.steps_called(), ["plan", "implement", "fix", "fix"])
        self.assertIn("- [ ] **M01-T01**", self.read("outputs/milestone-01-list-items.md"))
        self.assertIn("## Stop", self.read("progress.md"))

    def test_boundary_violation_fails_the_trial(self):
        self.assertEqual(self.first_run("--max-trials", "1"), 10)
        self.cli("approve", "backend-dev")
        outside = os.path.join(self.t.root, "loops", "shared", "sneaky.txt")
        answer = implemented("M01-T01")
        answer["writes"].append({"path": outside, "content": "x"})  # Bash-style: no hook
        self.scenario({"implement": answer})
        self.assertEqual(self.cli("run", "backend-dev"), 20, self.last_output)
        failure = self.trial("M01", 1)["failure"]
        self.assertEqual(failure["reason"], "boundary-violation")
        self.assertIn(outside, failure["detail"])
        self.assertTrue(os.path.exists(outside))  # reported, never reverted
        events = state.read_jsonl(os.path.join(self.loop_dir, "state", "events.jsonl"))
        self.assertIn("boundary-violation", [e["type"] for e in events])

    def test_boundary_is_audited_even_when_the_call_fails(self):
        self.assertEqual(self.first_run("--max-trials", "2"), 10)
        self.cli("approve", "backend-dev")
        outside = os.path.join(self.t.root, "loops", "shared", "sneaky.txt")
        self.scenario({"implement": {"is_error": True,
                                     "writes": [{"path": outside, "content": "first"}]},
                       "fix": {"structured_output": {"tasks": []},
                               "writes": [{"path": outside, "content": "second"}]}})
        self.assertEqual(self.cli("run", "backend-dev"), 20, self.last_output)
        first, second = self.trial("M01", 1)["failure"], self.trial("M01", 2)["failure"]
        self.assertEqual((first["reason"], second["reason"]),
                         ("boundary-violation", "boundary-violation"))
        self.assertIn(outside, first["detail"])
        self.assertIn("the call also failed: claude-error", first["detail"])
        self.assertIn("the call also failed: invalid-output", second["detail"])
        events = state.read_jsonl(os.path.join(self.loop_dir, "state", "events.jsonl"))
        self.assertEqual([e["type"] for e in events].count("boundary-violation"), 2)

    def failed_trial_after(self, stub_mode):
        self.assertEqual(self.first_run(), 10)
        self.assertEqual(self.cli("approve", "backend-dev"), 0, self.last_output)
        self.cli("run", "backend-dev", "--max-trials", "1", env={"DEVLOOPS_STUB": stub_mode})
        return self.trial("M01", 1)["failure"]

    def test_a_validator_call_failure_keeps_its_own_reason(self):
        failure = self.failed_trial_after("call-failed")
        self.assertEqual(failure["reason"], "timeout")

    def test_other_exceptions_with_a_reason_attribute_are_driver_errors(self):
        failure = self.failed_trial_after("decode-error")
        self.assertEqual(failure["reason"], "validation-failed")
        self.assertIn("driver error: UnicodeDecodeError", failure["detail"])

    def test_failed_call_without_violation_keeps_its_own_reason(self):
        self.assertEqual(self.first_run("--max-trials", "1"), 10)
        self.cli("approve", "backend-dev")
        self.scenario({"implement": {"structured_output": {"tasks": []}}})
        self.assertEqual(self.cli("run", "backend-dev"), 20)
        self.assertEqual(self.trial("M01", 1)["failure"]["reason"], "invalid-output")

    # --- input errors ---

    def test_missing_requirements_exits_30_without_recording_a_run(self):
        code = self.cli("run", "backend-dev", "--requirements",
                        os.path.join(self.t.base, "nope.md"), "--target", self.t.target_dir)
        self.assertEqual(code, 30, self.last_output)
        self.assertIn("does not exist", self.last_output)
        self.assertIsNone(self.run_state())
        self.assertEqual(self.t.fake_calls(), [])
        # Fixing the input then works: a typo does not lock the workspace.
        self.assertEqual(self.first_run(), 10)

    def test_missing_target_exits_30(self):
        self.assertEqual(self.cli("run", "backend-dev", "--requirements", self.prd), 30)
        self.assertIn("--target", self.last_output)

    def test_requirements_changed_after_planning(self):
        self.assertEqual(self.first_run(), 10)
        with open(self.prd, "a") as f:
            f.write("- FR-3 delete items\n")
        self.assertEqual(self.cli("run", "backend-dev"), 30)
        rs = self.run_state()
        self.assertEqual(rs["status"], "stopped-on-input-error")
        self.assertEqual(rs["status_reason"]["input"], "requirements")

    def test_answers_may_change_while_awaiting_approval(self):
        self.assertEqual(self.first_run(), 10)
        with open(os.path.join(self.loop_dir, "outputs", "open-questions.md"), "a") as f:
            f.write("extra note\n")
        self.assertEqual(self.cli("run", "backend-dev"), 10)

    # --- commands and output ---

    def test_approve_only_when_awaiting_approval(self):
        self.assertEqual(self.cli("approve", "backend-dev"), 2)
        self.assertEqual(self.first_run(), 10)
        self.assertEqual(self.cli("approve", "backend-dev"), 0)
        self.assertEqual(self.cli("approve", "backend-dev"), 2)
        self.assertIn("awaiting-approval", self.last_output)

    def test_replan_uses_the_answers_and_pauses_again(self):
        plan = samples.plan()
        plan["open_questions"] = [{"id": "OQ1", "question": "Which port?", "context": "c",
                                   "affects": ["M01"], "suggested_answer": "",
                                   "suggestion_reason": ""}]
        self.scenario({"plan": {"structured_output": plan},
                       "replan": {"structured_output": samples.plan()}})
        self.assertEqual(self.first_run(), 10)
        path = os.path.join(self.loop_dir, "outputs", "open-questions.md")
        with open(path) as f:
            text = f.read()
        with open(path, "w") as f:
            f.write(text.replace("**Answer:**", "**Answer:** use 8765"))
        self.assertEqual(self.cli("replan", "backend-dev"), 10, self.last_output)
        replan_prompt = self.t.fake_calls()[-1]["prompt"]
        self.assertIn("use 8765", replan_prompt)
        rs = self.run_state()
        self.assertEqual([t["kind"] for t in rs["planning"]["trials"]], ["plan", "replan"])
        self.assertEqual(rs["status"], "awaiting-approval")

    def test_replan_with_no_planning_trials_left_is_refused(self):
        self.scenario({"plan": {"structured_output": samples.plan()},
                       "replan": {"structured_output": samples.plan()}})
        self.assertEqual(self.first_run(), 10)                       # planning trial 1 of 3
        self.assertEqual(self.cli("replan", "backend-dev"), 10)      # 2 of 3
        self.assertEqual(self.cli("replan", "backend-dev"), 10)      # 3 of 3
        plan_before = self.read("state/plan.json")
        self.assertEqual(self.cli("replan", "backend-dev"), 2, self.last_output)
        self.assertIn("no planning trials left (3 of 3 used)", self.last_output)
        rs = self.run_state()
        self.assertEqual(rs["status"], "awaiting-approval")
        self.assertIsNone(rs["status_reason"])
        self.assertEqual(len(self.t.fake_calls()), 3)
        self.assertEqual(self.read("state/plan.json"), plan_before)
        self.assertEqual(self.cli("approve", "backend-dev"), 0)     # the plan is still usable

    def test_replan_that_finds_no_valid_plan_keeps_the_previous_one(self):
        self.scenario({"plan": {"structured_output": samples.plan()},
                       "replan": {"structured_output": {"milestones": []}}})
        self.assertEqual(self.first_run("--max-trials", "2"), 10)
        plan_before = self.read("state/plan.json")
        self.assertEqual(self.cli("replan", "backend-dev"), 10, self.last_output)
        self.assertIn("previous plan still awaits approval", self.last_output)
        rs = self.run_state()
        self.assertEqual(rs["status"], "awaiting-approval")
        self.assertEqual([t["status"] for t in rs["planning"]["trials"]], ["passed", "failed"])
        self.assertEqual(self.read("state/plan.json"), plan_before)
        self.assertEqual(self.cli("approve", "backend-dev"), 0)

    def test_status_json(self):
        self.assertEqual(self.first_run(), 10)
        code, out, _ = self.t.run_cli(["status", "backend-dev", "--workspace", WS, "--json"])
        self.assertEqual(code, 0)
        obj = json.loads(out)
        self.assertEqual((obj["status"], obj["next_milestone"], obj["trials_used"],
                          obj["trial_limit"]), ("awaiting-approval", "M01", 0, 3))
        code, out, _ = self.t.run_cli(["status", "--workspace", WS, "--json"])
        self.assertEqual(json.loads(out)["loops"]["frontend-dev"]["status"], "not-started")

    def test_run_json_prints_one_status_object(self):
        code, out, _ = self.t.run_cli(["run", "backend-dev", "--workspace", WS, "--requirements",
                                       self.prd, "--target", self.t.target_dir, "--json"])
        self.assertEqual(code, 10)
        obj = json.loads(out)
        self.assertEqual((obj["status"], obj["exit_code"]), ("awaiting-approval", 10))

    def test_usage_errors_exit_2(self):
        # Outside any project (002 FR-008).
        self.assertEqual(self.t.run_cli(["status", "--workspace", WS], cwd=self.t.base)[0], 2)
        self.assertEqual(self.cli("run", "other-loop"), 2)
        self.assertEqual(self.cli("run", "backend-dev", "--max-trials", "0"), 2)
        self.assertEqual(self.t.run_cli(["status", "--workspace", "missing"])[0], 2)


if __name__ == "__main__":
    unittest.main()
