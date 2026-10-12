"""A full `frontend-dev` flow, run alone through `engine.Engine`, with fake Claude (T039).

The CLI runs frontend-dev only after backend-dev (003 FR-006); the loop itself stays runnable
alone once its inputs exist, so these tests drive the engine directly (003 research R-11,
`helpers.run_frontend_engine`) and give it the API spec the backend's handoff would.

This drives the real `frontend-dev` loop end to end: `loops/frontend-dev/{loop.json,
Loop-instructions.md,task.md}` (T040-T042), `loops/shared/prompts/steps/validate-ui.md` (T043),
the API-spec input handling (T044), and `loops/shared/devloops/validators/playwright.py` (T045).
The frontend runtime is `python3 -m http.server` serving the `index.html` that fake `implement`
writes. None of those exist yet, so this test fails until then, which is expected (the tests for a
story are written first and must fail before its implementation tasks).
"""
import json
import os
import socket
import sys
import unittest

import helpers
import samples
from devloops import state

WS = "frontend"
PLAYWRIGHT_TOOLS = ["mcp__playwright__browser_navigate", "mcp__playwright__browser_snapshot"]

API_SPEC = {
    "openapi": "3.0.3", "info": {"title": "items", "version": "1.0.0"},
    "paths": {"/items": {"get": {"responses": {"200": {"description": "the items"}}}}},
}


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FrontendLoopTest(unittest.TestCase):
    def setUp(self):
        self.t = helpers.TempEnv(workspace=WS).__enter__()
        self.addCleanup(self.t.__exit__, None, None, None)
        self.port = free_port()
        self.ui_url = f"http://127.0.0.1:{self.port}"
        self.prd = self.t.write_file("prd.md", "# PRD\n\n- FR-1 show the items page\n")
        self.api_spec = self.t.write_file(os.path.join("contract", "openapi.json"),
                                          json.dumps(API_SPEC))
        # The Playwright MCP server is never started by fake Claude; preflight only needs its
        # command on PATH (FR-013b).
        self.config = self.t.write_file("config.json", json.dumps(
            {"playwright": {"mcp_command": [sys.executable, "-c", "pass"]}}))
        self.loop_dir = os.path.join(self.t.workspace_dir, "frontend-dev")

    def plan(self):
        plan = samples.plan()
        plan["requirements_inventory"] = [{"ref": "FR-1", "summary": "Show the items page"}]
        plan["stack"] = {"summary": "Static HTML", "source": "proposed", "conflicts": []}
        plan["runtime"] = {
            "start_command": f"{sys.executable} -m http.server {self.port} --bind 127.0.0.1",
            "cwd": ".",
            "base_url": self.ui_url,
            "ready_url": self.ui_url + "/",
        }
        plan["milestones"] = [{
            "id": "M01", "title": "Items page", "goal": "Visitors see the items page",
            "depends_on": [],
            "tasks": [{"id": "M01-T01", "title": "Home page", "description": "Render the page",
                       "requirement_refs": ["FR-1"]}],
            "acceptance_criteria": [{"id": "M01-AC1", "text": "The home page shows 'Items'",
                                     "requirement_refs": ["FR-1"]}],
        }]
        plan["assumptions"] = []
        return plan

    def evidence_dir(self, n=1):
        return os.path.join(self.loop_dir, "state", "milestones", "M01", "trials", str(n),
                            "evidence")

    def scenario(self, steps):
        self.t.write_scenario({"steps": steps})

    def cli(self, *args):
        code, out, err = self.t.run_cli([*args, "--workspace", WS])
        self.last_output = out + err
        return code

    def engine(self, action="run", **options):
        code, out, err = helpers.run_frontend_engine(self.t, workspace=WS, action=action,
                                                     **options)
        self.last_output = out + err
        return code

    def first_run(self, api_spec=True):
        return self.engine(requirements=self.prd, target=self.t.frontend_target_dir,
                           config=self.config,
                           api_spec=(api_spec if isinstance(api_spec, str) else self.api_spec)
                           if api_spec else None)

    def run_state(self):
        return state.read_json(os.path.join(self.loop_dir, "state", "run.json"))

    # --- input errors (exit 30) ------------------------------------------------------------------

    def test_a_missing_tool_on_resume_changes_nothing(self):
        """Run alone (no orchestrator check first), a resume that finds Claude Code missing exits
        30 and records nothing: the run stays resumable, not `stopped-on-input-error`."""
        self.scenario({"plan": {"structured_output": self.plan()}})
        self.assertEqual(self.first_run(), 10, self.last_output)
        code, out, err = helpers.run_frontend_engine(
            self.t, workspace=WS, extra_env={"DEVLOOPS_CLAUDE_BIN": "/nonexistent/claude"})
        self.assertEqual(code, 30, out + err)
        self.assertIn("nothing was changed", out + err)
        rs = self.run_state()
        self.assertEqual(rs["status"], "awaiting-approval")
        self.assertIsNone(rs.get("status_reason"))
        self.assertEqual(self.engine(), 10, self.last_output)  # Claude Code back: it resumes

    def test_missing_api_spec_is_a_missing_input(self):
        self.scenario({"plan": {"structured_output": self.plan()}})
        self.assertEqual(self.first_run(api_spec=False), 30, self.last_output)
        self.assertIn("requires an API spec", self.last_output)
        self.assertEqual([c for c in self.t.fake_calls() if c["step"]], [])  # nothing planned

    def test_a_json_file_that_is_not_openapi_is_an_invalid_api_spec(self):
        not_openapi = self.t.write_file("not-openapi.json", json.dumps({"swagger": "2.0"}))
        self.scenario({"plan": {"structured_output": self.plan()}})
        self.assertEqual(self.first_run(api_spec=not_openapi), 30, self.last_output)
        self.assertIn("openapi", self.last_output)
        self.assertEqual([c for c in self.t.fake_calls() if c["step"]], [])

    def test_the_api_spec_edited_after_planning_is_an_input_change(self):
        self.scenario({"plan": {"structured_output": self.plan()}})
        self.assertEqual(self.first_run(), 10, self.last_output)
        # The spec was frozen into the workspace and fingerprinted at planning (FR-051a).
        with open(os.path.join(self.loop_dir, "state", "api-spec.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), API_SPEC)
        self.assertEqual(self.run_state()["inputs"]["api_spec"]["path"], self.api_spec)

        edited = dict(API_SPEC, info={"title": "items", "version": "1.0.1"})
        self.t.write_file(os.path.join("contract", "openapi.json"), json.dumps(edited))
        self.assertEqual(self.cli("approve", "--no-continue"), 0, self.last_output)
        self.assertEqual(self.engine(), 30, self.last_output)
        reason = self.run_state()["status_reason"]
        self.assertEqual(reason["code"], "input-changed")
        self.assertEqual(reason["input"], "api-spec")

    # --- the full flow -----------------------------------------------------------------------------

    def build_scenario(self, fail_first=False):
        """One implement call that writes the page, and one validate-ui call that passes it;
        with `fail_first`, the first validation fails and a fix trial passes."""
        built = {"structured_output": {
            "tasks": [{"task_id": "M01-T01", "status": "implemented", "note": "done"}],
            "assumptions": [], "needs_input": [], "files_changed": ["index.html"]},
            "writes": [{"path": "index.html", "content": "<h1>Items</h1>\n", "tool": "Write"}]}

        def validation(n, passed):
            return {
                "structured_output": {
                    "criteria": [{"criterion_id": "M01-AC1", "passed": passed,
                                  "steps": ["navigate to the UI URL", "snapshot the page"],
                                  "observed": "heading 'Items' is visible",
                                  "evidence": ["evidence/home.png"]}]},
                "tool_uses": PLAYWRIGHT_TOOLS + [helpers.network_log(
                    [{"method": "GET", "url": self.ui_url + "/", "status": 200}])],
                "writes": [{"path": os.path.join(self.evidence_dir(n), "home.png"),
                            "content": "PNG"}]}

        steps = {"implement": built, "validate-ui": validation(1, True)}
        if fail_first:
            steps.update({"fix": built, "validate-ui": [validation(1, False), validation(2, True)]})
        self.scenario(steps)

    def context_of(self, call):
        """The driver context block of a fake-Claude call's prompt."""
        return json.loads(call["prompt"].split("```json\n", 1)[1].rsplit("\n```", 1)[0])

    def test_ui_url_is_recorded_and_the_milestone_is_achieved(self):
        self.scenario({"plan": {"structured_output": self.plan()}})
        self.assertEqual(self.first_run(), 10, self.last_output)
        self.assertEqual(self.cli("approve", "--no-continue"), 0, self.last_output)

        self.build_scenario()
        self.assertEqual(self.engine(), 0, self.last_output)

        rs = self.run_state()
        self.assertEqual(rs["status"], "completed")
        self.assertEqual(rs["milestones"]["M01"]["status"], "achieved")
        self.assertEqual(rs["ui_url"], self.ui_url)
        with open(os.path.join(self.loop_dir, "outputs", "ui-url.txt"), encoding="utf-8") as f:
            self.assertEqual(f.read().strip(), self.ui_url)

        trial_dir = os.path.dirname(self.evidence_dir())
        validation = state.read_json(os.path.join(trial_dir, "validation.json"))
        self.assertEqual(validation["kind"], "playwright")
        self.assertTrue(validation["passed"])
        self.assertEqual(validation["contract"], {"passed": True, "unmatched_operations": []})
        self.assertEqual([c["criterion_id"] for c in validation["criteria"]], ["M01-AC1"])
        self.assertTrue(os.path.exists(os.path.join(trial_dir, "stream.jsonl")))

        # implement was told about the contract: the frozen spec and the documented-only rule.
        implement = next(c for c in self.t.fake_calls() if c["step"] == "implement")
        self.assertIn('"frontend"', implement["prompt"])
        self.assertIn(self.api_spec, implement["prompt"])

    # --- the design (spec 007) ---------------------------------------------------------------------

    def test_a_plan_without_a_design_is_rejected(self):
        """FR-002: the frontend's plan must carry a design brief."""
        plan = self.plan()
        del plan["design"]
        self.scenario({"plan": [{"structured_output": plan}] * 3})
        self.assertEqual(self.first_run(), 20, self.last_output)
        trials = self.run_state()["planning"]["trials"]
        self.assertIn("design is required for this loop", trials[0]["failure"]["detail"])

    def test_the_design_and_its_references_reach_every_call(self):
        """FR-010, FR-012: the plan and replan steps get the references; implement and fix get
        the brief and the references. The calls read copies made at the first start (research
        R-4): never the folder around the original, and not an edit made later."""
        brand = self.t.write_file(os.path.join("design", "brand.md"), "# Brand\n",
                                  base=self.t.root)
        with open(self.config, encoding="utf-8") as f:
            cfg = json.load(f)
        cfg["design"] = {"references": [os.path.join("design", "brand.md")]}
        self.t.write_file("config.json", json.dumps(cfg))
        self.scenario({"plan": {"structured_output": self.plan()}})
        self.assertEqual(self.first_run(), 10, self.last_output)
        self.t.write_file(os.path.join("design", "brand.md"), "# Edited\n", base=self.t.root)
        self.scenario({"replan": {"structured_output": self.plan()}})
        self.assertEqual(self.cli("replan", "--no-continue"), 10, self.last_output)
        self.assertEqual(self.cli("approve", "--no-continue"), 0, self.last_output)
        self.build_scenario(fail_first=True)
        self.assertEqual(self.engine(), 0, self.last_output)

        folder = os.path.join(self.loop_dir, "state", "design-references")
        copy = os.path.join(folder, "1-brand.md")
        with open(copy, encoding="utf-8") as f:
            self.assertEqual(f.read(), "# Brand\n")
        calls = {c["step"]: c for c in self.t.fake_calls() if c["step"]}
        self.assertEqual(sorted(calls), ["fix", "implement", "plan", "replan", "validate-ui"])
        for step in ("plan", "replan"):  # FR-002: told, not only rejected
            self.assertIs(self.context_of(calls[step])["requires_design"], True, step)
        for step in ("plan", "replan", "implement", "fix"):
            context = self.context_of(calls[step])
            self.assertEqual(context["design_references"], [copy], step)
            if step in ("implement", "fix"):
                self.assertEqual(context["design"], self.plan()["design"], step)
            add_dirs = calls[step]["argv"][calls[step]["argv"].index("--add-dir") + 1:]
            self.assertIn(os.path.realpath(folder), add_dirs, step)
            self.assertNotIn(os.path.realpath(os.path.dirname(brand)), add_dirs, step)

    def test_a_missing_design_reference_stops_the_first_start(self):
        """FR-011: before any call, with missing-input."""
        with open(self.config, encoding="utf-8") as f:
            cfg = json.load(f)
        cfg["design"] = {"references": ["design/missing.png"]}
        self.t.write_file("config.json", json.dumps(cfg))
        self.scenario({"plan": {"structured_output": self.plan()}})
        self.assertEqual(self.first_run(), 30, self.last_output)
        self.assertIn("design/missing.png does not exist", self.last_output)
        self.assertEqual([c for c in self.t.fake_calls() if c["step"]], [])

    def test_a_reference_that_cannot_be_copied_stops_cleanly(self):
        """FR-011: a folder that holds the workspace (it would be copied into itself), or a file
        that cannot be read, stops with missing-input rather than a traceback."""
        with open(self.config, encoding="utf-8") as f:
            cfg = json.load(f)
        self.scenario({"plan": {"structured_output": self.plan()}})
        cfg["design"] = {"references": ["."]}
        self.t.write_file("config.json", json.dumps(cfg))
        self.assertEqual(self.first_run(), 30, self.last_output)
        self.assertIn("holds the workspace", self.last_output)
        if os.geteuid() == 0:
            return  # root reads any file
        secret = self.t.write_file(os.path.join("design", "locked.md"), "x", base=self.t.root)
        os.chmod(secret, 0)
        self.addCleanup(os.chmod, secret, 0o644)
        cfg["design"] = {"references": ["design"]}
        self.t.write_file("config.json", json.dumps(cfg))
        self.assertEqual(self.first_run(), 30, self.last_output)
        self.assertIn("cannot copy", self.last_output)
        self.assertNotIn("Traceback", self.last_output)
        self.assertEqual([c for c in self.t.fake_calls() if c["step"]], [])


if __name__ == "__main__":
    unittest.main()
