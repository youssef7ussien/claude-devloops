"""`devloops orchestrate`: backend-dev, then frontend-dev, in one workspace (T063; FR-040-042,
FR-052, FR-056; research R-15).

Written before T064-T066 (`orchestrator.py`, the `orchestrate` command, and its progress file),
so this module fails until then.

Both loops use a stub validator, so the tests exercise the orchestration and the handoff, not a
real application. The stub publishes the target's OpenAPI document on an achieved milestone, as
the curl adapter does, so the backend leaves `outputs/openapi.json` behind.
"""
import contextlib
import importlib.util
import io
import json
import os
import sys
import unittest
from unittest import mock

import helpers
import samples
from devloops import cli, engine, inputs, state
from stub_loop import STUB, implemented

WS = "orch"
STUB_NAME = "orchstub"

ORCH_STUB = STUB + '''

def on_achieved(ctx):
    """Publish the target's OpenAPI document, as the curl adapter does (FR-019)."""
    import hashlib
    rel = (ctx.runtime or {}).get("openapi_path")
    src = os.path.join(ctx.target_dir, rel) if rel else None
    if not src or not os.path.isfile(src):
        return
    with open(src, "rb") as f:
        content = f.read()
    dest = os.path.join(ctx.loop_dir, "outputs", "openapi.json")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        f.write(content)
    ctx.run_state["openapi_artifact"] = {"path": os.path.relpath(dest, ctx.loop_dir),
                                         "sha256": hashlib.sha256(content).hexdigest()}
'''

OPENAPI = {
    "openapi": "3.0.3", "info": {"title": "items", "version": "1.0.0"},
    "paths": {"/items": {"get": {"responses": {"200": {"description": "the items"}}}}},
}


def backend_plan():
    return samples.plan()  # runtime: start_command, cwd ".", base_url, ready_url, openapi_path


def frontend_plan():
    plan = samples.plan()
    plan["requirements_inventory"] = [{"ref": "FR-1", "summary": "Show the items page"}]
    plan["runtime"] = {"start_command": "python3 -m http.server 8801", "cwd": ".",
                       "base_url": "http://127.0.0.1:8801", "ready_url": "http://127.0.0.1:8801/"}
    plan["milestones"] = plan["milestones"][:1]
    plan["milestones"][0]["title"] = "Items page"
    return plan


def backend_m01():
    answer = implemented("M01-T01")
    answer["writes"].append({"path": "openapi.json", "content": json.dumps(OPENAPI),
                             "tool": "Write"})
    return answer


class OrchestratorTest(unittest.TestCase):
    def setUp(self):
        self.t = helpers.TempEnv(workspace=WS).__enter__()
        self.addCleanup(self.t.__exit__, None, None, None)
        loops = os.path.join(self.t.root, "loops")
        for loop, required in (("backend-dev", ["requirements"]),
                               ("frontend-dev", ["requirements", "api_spec"])):
            self.t.write_file(os.path.join(loop, "loop.json"), json.dumps({
                "name": loop, "required_inputs": required, "required_tools": [],
                "validator": STUB_NAME, "requires_openapi_path": False}), base=loops)
        self.t.write_file(os.path.join("shared", "devloops", "validators", STUB_NAME + ".py"),
                          ORCH_STUB, base=loops)
        self.prd = self.t.write_file("prd.md", "# PRD\n\n- FR-1 list items\n- FR-2 create items\n")
        self.target_root = os.path.join(self.t.base, "app")
        self.backend_target = os.path.join(self.target_root, "backend")
        self.frontend_target = os.path.join(self.target_root, "frontend")
        self.scenario()

    # --- helpers -----------------------------------------------------------------------------------

    def scenario(self, **overrides):
        steps = {"plan": [{"structured_output": backend_plan()},
                          {"structured_output": frontend_plan()}],
                 "implement": [backend_m01(), implemented("M02-T01"), implemented("M01-T01")],
                 "fix": implemented("M01-T01")}
        steps.update(overrides)
        self.t.write_scenario({"steps": steps})

    def orchestrate(self, *extra, env=None):
        code, out, err = self.t.run_cli(
            ["orchestrate", "--workspace", WS, "--requirements", self.prd, "--target-root",
             self.target_root, *extra], extra_env=env)
        self.last_output = out + err
        return code

    def approve(self, loop):
        code, out, err = self.t.run_cli(["approve", loop, "--workspace", WS])
        self.assertEqual(code, 0, out + err)

    def loop_path(self, loop, *parts):
        return os.path.join(self.t.workspace_dir, loop, *parts)

    def run_state(self, loop):
        return state.read_json(self.loop_path(loop, "state", "run.json"))

    def orch_state(self):
        return state.read_json(os.path.join(self.t.workspace_dir, "orchestrator", "state.json"))

    def steps_called(self):
        return [c["step"] for c in self.t.fake_calls()]

    def to_completion(self):
        self.assertEqual(self.orchestrate(), 10, self.last_output)   # backend plan
        self.approve("backend-dev")
        self.assertEqual(self.orchestrate(), 10, self.last_output)   # backend done, frontend plan
        self.approve("frontend-dev")
        self.assertEqual(self.orchestrate(), 0, self.last_output)

    # --- tests ---------------------------------------------------------------------------------------

    def test_backend_awaiting_approval_pauses_before_the_frontend(self):
        self.assertEqual(self.orchestrate(), 10, self.last_output)
        self.assertEqual(self.run_state("backend-dev")["status"], "awaiting-approval")
        self.assertFalse(os.path.exists(self.loop_path("frontend-dev", "state")))
        orch = self.orch_state()
        self.assertEqual(orch["status"], "paused")
        self.assertEqual([(s["loop"], s["status"]) for s in orch["steps"]],
                         [("backend-dev", "awaiting-approval")])
        self.assertEqual(self.steps_called(), ["plan"])

    def test_backend_stopped_on_failure_stops_with_its_exit_code(self):
        self.assertEqual(self.orchestrate(), 10, self.last_output)
        self.approve("backend-dev")
        self.assertEqual(self.orchestrate(env={"DEVLOOPS_STUB": "fail"}), 20, self.last_output)
        self.assertEqual(self.run_state("backend-dev")["status"], "stopped-on-failure")
        self.assertFalse(os.path.exists(self.loop_path("frontend-dev", "state")))
        orch = self.orch_state()
        self.assertEqual(orch["status"], "stopped")
        step = orch["steps"][-1]
        self.assertEqual((step["loop"], step["status"]), ("backend-dev", "stopped-on-failure"))
        self.assertEqual(step["reason"], "trials-exhausted")
        self.assertTrue(step["ended_at"])

    def test_completed_backend_hands_its_contract_and_runtime_to_the_frontend(self):
        self.to_completion()
        self.assertEqual(self.run_state("backend-dev")["status"], "completed")
        self.assertEqual(self.run_state("frontend-dev")["status"], "completed")

        artifact = self.loop_path("backend-dev", "outputs", "openapi.json")
        fe = self.run_state("frontend-dev")
        self.assertEqual(os.path.realpath(fe["inputs"]["api_spec"]["path"]),
                         os.path.realpath(artifact))
        self.assertEqual(fe["inputs"]["api_spec"]["sha256"], inputs.sha256_file(artifact))

        runtime = backend_plan()["runtime"]
        backend_cfg = fe["effective_config"]["backend"]
        self.assertEqual(backend_cfg["start_command"], runtime["start_command"])
        self.assertEqual(backend_cfg["ready_url"], runtime["ready_url"])
        self.assertEqual(os.path.realpath(backend_cfg["cwd"]),
                         os.path.realpath(self.backend_target))

        # The default targets under --target-root.
        ws = state.read_json(os.path.join(self.t.workspace_dir, "workspace.json"))
        self.assertEqual(os.path.realpath(ws["targets"]["backend-dev"]),
                         os.path.realpath(self.backend_target))
        self.assertEqual(os.path.realpath(ws["targets"]["frontend-dev"]),
                         os.path.realpath(self.frontend_target))

        orch = self.orch_state()
        self.assertEqual(orch["status"], "completed")
        # Resuming a completed backend leaves its step alone: it ended before the frontend began.
        backend_step, frontend_step = orch["steps"]
        self.assertLessEqual(backend_step["ended_at"], frontend_step["started_at"])
        self.assertEqual([(s["loop"], s["status"]) for s in orch["steps"]][-2:],
                         [("backend-dev", "completed"), ("frontend-dev", "completed")])
        handoff = orch["handoff"]
        self.assertEqual(os.path.realpath(handoff["api_spec"]["path"]), os.path.realpath(artifact))
        self.assertEqual(handoff["api_spec"]["sha256"], inputs.sha256_file(artifact))
        self.assertEqual(handoff["backend_runtime"]["start_command"], runtime["start_command"])
        self.assertEqual(handoff["backend_runtime"]["base_url"], runtime["base_url"])
        self.assertEqual(handoff["backend_runtime"]["ready_url"], runtime["ready_url"])
        self.assertEqual(os.path.realpath(handoff["backend_runtime"]["cwd"]),
                         os.path.realpath(self.backend_target))

    def test_accept_suggested_runs_both_loops_without_pausing(self):
        backend = backend_plan()
        backend["open_questions"] = [{"id": "OQ1", "question": "Which port?", "context": "c",
                                      "affects": ["M01"], "suggested_answer": "8765",
                                      "suggestion_reason": "the plan's runtime uses it"}]
        self.scenario(plan=[{"structured_output": backend}, {"structured_output": frontend_plan()}])
        self.assertEqual(self.orchestrate("--accept-suggested"), 0, self.last_output)
        self.assertEqual(self.orch_state()["status"], "completed")
        for loop in ("backend-dev", "frontend-dev"):
            rs = self.run_state(loop)
            self.assertEqual((rs["status"], rs["approval"]["action"]), ("completed", "auto-approve"))
            self.assertEqual(rs["effective_config"]["questions"], "accept-suggested")
        self.assertEqual(self.run_state("backend-dev")["approval"]["accepted_suggestions"], ["OQ1"])

    def test_rerunning_resumes_each_loop_from_its_own_state(self):
        self.to_completion()
        # Each loop planned once and each milestone was implemented once: nothing restarted.
        self.assertEqual(self.steps_called(), ["plan", "implement", "implement", "plan",
                                               "implement"])
        # A completed orchestration run again changes nothing and calls nothing.
        self.assertEqual(self.orchestrate(), 0, self.last_output)
        self.assertEqual(len(self.t.fake_calls()), 5)

    def test_one_full_dashboard_when_the_loop_it_ran_ends_final(self):
        directory = os.path.join(self.t.root, ".devloops", "dashboards", WS)

        def count():
            return len(os.listdir(directory)) if os.path.isdir(directory) else 0
        self.assertEqual(self.orchestrate(), 10, self.last_output)
        self.approve("backend-dev")
        self.assertEqual(self.orchestrate(), 10, self.last_output)
        self.assertEqual(count(), 0)  # the backend completed, but the frontend paused (FR-039)
        self.approve("frontend-dev")
        self.assertEqual(self.orchestrate(), 0, self.last_output)
        self.assertEqual(count(), 1)
        self.assertIn("full dashboard: ", self.last_output)
        self.assertEqual(self.orchestrate(), 0, self.last_output)
        self.assertEqual(count(), 1)  # nothing ran: no new full dashboard

    def test_resuming_with_no_flags_starts_the_frontend_from_the_recorded_inputs(self):
        self.assertEqual(self.orchestrate(), 10, self.last_output)
        self.approve("backend-dev")
        code, out, err = self.t.run_cli(["orchestrate", "--workspace", WS])
        self.assertEqual(code, 10, out + err)  # the frontend planned and now awaits approval
        fe = self.run_state("frontend-dev")
        self.assertEqual(fe["status"], "awaiting-approval")
        self.assertEqual(fe["inputs"]["requirements"]["path"], self.prd)
        self.assertEqual(os.path.realpath(fe["target_dir"]), os.path.realpath(self.frontend_target))

    def test_resuming_a_story_run_keeps_the_recorded_story_for_the_frontend(self):
        plan = backend_plan()
        for m in plan["milestones"]:
            for item in m["tasks"] + m["acceptance_criteria"]:
                item["requirement_refs"] = ["FR-1"]
        self.scenario(plan=[{"structured_output": plan}, {"structured_output": frontend_plan()}])
        self.assertEqual(self.orchestrate("--story-id", "FR-1"), 10, self.last_output)
        self.approve("backend-dev")
        self.assertEqual(self.orchestrate(), 10, self.last_output)  # --requirements, no story flag
        req = self.run_state("frontend-dev")["inputs"]["requirements"]
        self.assertEqual((req["mode"], req["story_id"]), ("prd-story", "FR-1"))

    def test_both_loops_run_through_the_same_engine_as_run(self):
        # In-process, so `engine.Engine` can be spied on. The stub validator lives in the temp
        # repo copy, so register it under the package this process imported.
        spec = importlib.util.spec_from_file_location(
            f"devloops.validators.{STUB_NAME}",
            os.path.join(self.t.root, "loops", "shared", "devloops", "validators",
                         STUB_NAME + ".py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules[spec.name] = module
        self.addCleanup(sys.modules.pop, spec.name, None)

        constructed = []
        real = engine.Engine

        class SpyEngine(real):
            def __init__(self, loop_name, *args, **kwargs):
                constructed.append(loop_name)
                super().__init__(loop_name, *args, **kwargs)

        def orchestrate():
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                return cli.main(["orchestrate", "--workspace", WS, "--requirements", self.prd,
                                 "--target-root", self.target_root], kit=self.t.kit(), project=self.t.project())

        def approve(loop):
            with contextlib.redirect_stdout(io.StringIO()):
                return cli.main(["approve", loop, "--workspace", WS], kit=self.t.kit(), project=self.t.project())

        with mock.patch.dict(os.environ, self.t.env, clear=True), \
                mock.patch.object(engine, "Engine", SpyEngine):
            self.assertEqual(orchestrate(), 10)
            self.assertEqual(approve("backend-dev"), 0)
            self.assertEqual(orchestrate(), 10)
            self.assertEqual(approve("frontend-dev"), 0)
            self.assertEqual(orchestrate(), 0)

        self.assertIn("backend-dev", constructed)
        self.assertIn("frontend-dev", constructed)
        self.assertLess(constructed.index("backend-dev"), constructed.index("frontend-dev"))
        self.assertEqual(self.run_state("frontend-dev")["status"], "completed")


if __name__ == "__main__":
    unittest.main()
