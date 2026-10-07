"""A full `frontend-dev` flow through `bin/devloops`, with fake Claude (T039).

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

    def first_run(self, *extra, api_spec=True):
        args = ["run", "frontend-dev", "--requirements", self.prd, "--target",
                self.t.frontend_target_dir, "--config", self.config]
        if api_spec:
            args += ["--api-spec", api_spec if isinstance(api_spec, str) else self.api_spec]
        return self.cli(*args, *extra)

    def run_state(self):
        return state.read_json(os.path.join(self.loop_dir, "state", "run.json"))

    # --- input errors (exit 30) ------------------------------------------------------------------

    def test_missing_api_spec_is_a_missing_input(self):
        self.scenario({"plan": {"structured_output": self.plan()}})
        self.assertEqual(self.first_run(api_spec=False), 30, self.last_output)
        self.assertIn("--api-spec", self.last_output)
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
        self.assertEqual(self.cli("approve", "--no-continue", "frontend-dev"), 0, self.last_output)
        self.assertEqual(self.cli("run", "frontend-dev"), 30, self.last_output)
        reason = self.run_state()["status_reason"]
        self.assertEqual(reason["code"], "input-changed")
        self.assertEqual(reason["input"], "api-spec")

    # --- the full flow -----------------------------------------------------------------------------

    def test_ui_url_is_recorded_and_the_milestone_is_achieved(self):
        self.scenario({"plan": {"structured_output": self.plan()}})
        self.assertEqual(self.first_run(), 10, self.last_output)
        self.assertEqual(self.cli("approve", "--no-continue", "frontend-dev"), 0, self.last_output)

        self.scenario({
            "implement": {"structured_output": {
                "tasks": [{"task_id": "M01-T01", "status": "implemented", "note": "done"}],
                "assumptions": [], "needs_input": [], "files_changed": ["index.html"]},
                "writes": [{"path": "index.html", "content": "<h1>Items</h1>\n",
                            "tool": "Write"}]},
            "validate-ui": {
                "structured_output": {
                    "criteria": [{"criterion_id": "M01-AC1", "passed": True,
                                  "steps": ["navigate to the UI URL", "snapshot the page"],
                                  "observed": "heading 'Items' is visible",
                                  "evidence": ["evidence/home.png"]}],
                    "network_requests": [{"method": "GET", "url": self.ui_url + "/",
                                          "status": 200}]},
                "tool_uses": PLAYWRIGHT_TOOLS,
                "writes": [{"path": os.path.join(self.evidence_dir(), "home.png"),
                            "content": "PNG"}]},
        })
        self.assertEqual(self.cli("run", "frontend-dev"), 0, self.last_output)

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


if __name__ == "__main__":
    unittest.main()
