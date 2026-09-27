"""A full `backend-dev` flow through `bin/devloops`, with fake Claude (T030).

Unlike `test_engine_core.py` (a stub validator registered under a throwaway `loop.json`), this
drives the real `backend-dev` loop end to end: `loops/backend-dev/{loop.json,Loop-instructions.md,
task.md}` (T031-T033), `loops/shared/prompts/steps/author-checks.md` (T034), and
`loops/shared/devloops/validators/curl.py` (T035/T036) against the fixture server (T028). None of
those exist yet, so this test fails until then, which is expected (the tests for a story are
written first and must fail before its implementation tasks).
"""
import json
import os
import socket
import sys
import unittest

import helpers
import samples
from devloops import state

WS = "backend"
FIXTURE_SERVER = os.path.join(helpers.FIXTURES_DIR, "http_app.py")

# What each milestone alone should have exercised. Deliberately excludes `/health`: it is only the
# runtime's `ready_url`, not a documented operation, so it never needs a check of its own.
M01_OPENAPI = {
    "openapi": "3.0.3", "info": {"title": "items", "version": "1.0.0"},
    "paths": {"/items": {"get": {"responses": {"200": {"description": "the items"}}}}},
}

# M02's implementation "documents" one operation it never wrote a check for.
M02_OPENAPI_WITH_UNVERIFIED_OP = {
    "openapi": "3.0.3", "info": {"title": "items", "version": "1.0.0"},
    "paths": {
        "/items": {
            "get": {"responses": {"200": {"description": "the items"}}},
            "post": {"responses": {"201": {"description": "created"}}},
        },
        "/items/{id}": {
            "delete": {"parameters": [{"name": "id", "in": "path", "required": True,
                                       "schema": {"type": "string"}}],
                      "responses": {"204": {"description": "removed"}}},
        },
    },
}


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def implemented(task_id, openapi_doc):
    return {"structured_output": {
        "tasks": [{"task_id": task_id, "status": "implemented", "note": "done"}],
        "assumptions": [], "needs_input": [], "files_changed": ["openapi.json"]},
        "writes": [{"path": "app.py", "content": f"# {task_id}\n", "tool": "Write"},
                   {"path": "openapi.json", "content": json.dumps(openapi_doc), "tool": "Write"}]}


class BackendLoopTest(unittest.TestCase):
    def setUp(self):
        self.t = helpers.TempEnv(workspace=WS).__enter__()
        self.addCleanup(self.t.__exit__, None, None, None)
        self.port = free_port()
        self.prd = self.t.write_file("prd.md", "# PRD\n\n- FR-1 list items\n- FR-2 create items\n")
        self.loop_dir = os.path.join(self.t.workspace_dir, "backend-dev")

    def plan(self):
        plan = samples.plan()  # M01 "List items" (GET /items), M02 "Create items" (POST /items)
        plan["runtime"] = {
            "start_command": f"{sys.executable} {FIXTURE_SERVER} {self.port}",
            "cwd": ".",
            "base_url": f"http://127.0.0.1:{self.port}",
            "ready_url": f"http://127.0.0.1:{self.port}/health",
            "openapi_path": "openapi.json",
        }
        return plan

    def m01_checks(self):
        return {"milestone_id": "M01", "checks": [
            {"id": "C1", "criteria": ["M01-AC1"], "request": {"method": "GET", "path": "/items"},
             "expect": {"status": 200, "body_contains": ["[]"]}}]}

    def m02_checks(self):
        return {"milestone_id": "M02", "checks": [
            {"id": "C1", "criteria": ["M02-AC1"],
             "request": {"method": "POST", "path": "/items",
                         "headers": {"Content-Type": "application/json"},
                         "body": {"name": "Widget"}},
             "expect": {"status": 201, "json_equals": {"name": "Widget"}}}]}

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

    def published_openapi(self):
        path = os.path.join(self.loop_dir, "outputs", "openapi.json")
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    # --- publication is gated on achievement, and never outruns the checks -------------------

    def test_openapi_published_after_m01_and_never_updated_with_an_unverified_operation(self):
        self.scenario({"plan": {"structured_output": self.plan()},
                      "author-checks": [{"structured_output": self.m01_checks()},
                                        {"structured_output": self.m02_checks()}]})
        self.assertEqual(self.first_run(), 10, self.last_output)
        self.assertIsNone(self.published_openapi())  # nothing published while awaiting approval
        self.assertEqual(self.cli("approve", "backend-dev"), 0, self.last_output)

        self.scenario({"implement": [implemented("M01-T01", M01_OPENAPI),
                                     implemented("M02-T01", M02_OPENAPI_WITH_UNVERIFIED_OP)],
                      "author-checks": [{"structured_output": self.m01_checks()},
                                        {"structured_output": self.m02_checks()}]})
        self.assertEqual(self.cli("run", "backend-dev", "--max-trials", "1"), 20, self.last_output)

        # Each milestone's checks are frozen before its implementation starts (FR-069).
        steps = [c["step"] for c in self.t.fake_calls() if c["step"] != "plan"]
        self.assertEqual(steps, ["author-checks", "implement", "author-checks", "implement"])

        rs = self.run_state()
        self.assertEqual(rs["milestones"]["M01"]["status"], "achieved")
        self.assertEqual(rs["milestones"]["M02"]["status"], "failed")
        failure = rs["status_reason"]
        self.assertEqual(failure["code"], "trials-exhausted")
        self.assertEqual(failure["milestone_id"], "M02")

        # M01's document was published as soon as it was achieved...
        self.assertEqual(self.published_openapi(), M01_OPENAPI)
        artifact = rs["openapi_artifact"]
        self.assertTrue(artifact["path"].endswith("openapi.json"), artifact)
        self.assertEqual(len(artifact["sha256"]), 64)
        # ...and never overwritten by M02's document, which names an operation
        # (DELETE /items/{id}) that no check -- from M02 or from the achieved M01 -- exercises.
        m02_trial = state.read_json(os.path.join(self.loop_dir, "state", "milestones", "M02",
                                                  "trials", "1", "validation.json"))
        self.assertFalse(m02_trial["passed"])
        self.assertFalse(m02_trial["contract"]["passed"])
        self.assertIn("DELETE /items/{id}", " ".join(m02_trial["contract"]["unmatched_operations"]))

    # --- input and tool errors, independent of the validator ----------------------------------

    def test_plan_missing_runtime_openapi_path_is_rejected(self):
        bad_plan = self.plan()
        del bad_plan["runtime"]["openapi_path"]
        self.scenario({"plan": {"structured_output": bad_plan}})
        self.assertEqual(self.first_run("--max-trials", "1"), 20, self.last_output)
        rs = self.run_state()
        self.assertEqual(rs["status"], "stopped-on-failure")
        self.assertEqual(rs["status_reason"]["code"], "planning-trials-exhausted")
        self.assertIn("openapi_path", " ".join(
            t["failure"]["detail"] for t in rs["planning"]["trials"]))

    def test_missing_curl_tool_exits_30(self):
        # PATH has just enough to run fake_claude.py's `#!/usr/bin/env python3` shebang -- no curl.
        bin_dir = os.path.join(self.t.base, "bin-without-curl")
        os.makedirs(bin_dir)
        os.symlink(sys.executable, os.path.join(bin_dir, "python3"))
        env = dict(self.t.env, PATH=bin_dir)
        self.scenario({"plan": {"structured_output": self.plan()}})
        self.assertEqual(self.first_run(env=env), 30, self.last_output)
        self.assertIn("curl", self.last_output)
        self.assertIsNone(self.run_state())  # a preflight failure records no run (T025)
        self.assertEqual(self.t.fake_calls(), [])


if __name__ == "__main__":
    unittest.main()
