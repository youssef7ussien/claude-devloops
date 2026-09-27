"""Direct tests of the curl validator (T029, research R-8) against the fixture server (T028).

These exercise `devloops.validators.curl.validate(ctx)` on its own, with a `ctx` built the same
way `engine._adapter_context` builds one, but without going through the full CLI/engine (that
full-flow coverage is `test_backend_loop.py`, T030). The validator does not exist until T035; until
then this module fails to import, which is expected (the tests for a story are written first and
must fail before its implementation tasks).
"""
import json
import os
import socket
import sys
import types
import unittest
from unittest import mock

import helpers
import samples
from devloops import schema, state
from devloops.claude import CallFailed, ClaudeRunner
from devloops.redact import Redactor
from devloops.validators import curl

FIXTURE_SERVER = os.path.join(helpers.FIXTURES_DIR, "http_app.py")

# Declares exactly the operations `valid_checks()` exercises (POST /items, GET /items/{id},
# GET /health), so the "everything passes" tests never trip the full-document coverage rule
# (T036) -- that rule is exercised at the full-flow level, in `test_backend_loop.py` (T030).
TARGET_OPENAPI = {
    "openapi": "3.0.3", "info": {"title": "items", "version": "1.0.0"},
    "paths": {
        "/items": {"post": {"responses": {"201": {"description": "created"}}}},
        "/items/{id}": {"get": {
            "parameters": [{"name": "id", "in": "path", "required": True,
                           "schema": {"type": "string"}}],
            "responses": {"200": {"description": "the item"}}}},
        "/health": {"get": {"responses": {"200": {"description": "service status"}}}},
    },
}

MILESTONE = {
    "id": "M01",
    "title": "Manage items",
    "goal": "Clients can create an item, fetch it back, and check service health",
    "depends_on": [],
    "tasks": [{"id": "M01-T01", "title": "Items API", "description": "Implement /items and /health",
               "requirement_refs": ["FR-1"]}],
    "acceptance_criteria": [
        {"id": "M01-AC1", "text": "POST /items creates an item, then GET /items/{id} returns it",
         "requirement_refs": ["FR-1"]},
        {"id": "M01-AC2", "text": "GET /health reports status ok", "requirement_refs": ["FR-1"]},
    ],
}


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def valid_checks():
    """Covers both acceptance criteria; C2 chains off C1's capture, in the path; C3 chains it
    into a request body, to exercise `${var}` substitution in both places."""
    return {
        "milestone_id": "M01",
        "checks": [
            {"id": "C1", "criteria": ["M01-AC1"],
             "request": {"method": "POST", "path": "/items",
                         "headers": {"Content-Type": "application/json"},
                         "body": {"name": "Widget"}},
             "expect": {"status": 201, "json_equals": {"name": "Widget"}},
             "capture": {"item_id": "id"}},
            {"id": "C2", "criteria": ["M01-AC1"],
             "request": {"method": "GET", "path": "/items/${item_id}"},
             "expect": {"status": 200, "json_equals": {"name": "Widget"}}},
            {"id": "C3", "criteria": ["M01-AC1"],
             "request": {"method": "POST", "path": "/items",
                         "headers": {"Content-Type": "application/json"},
                         "body": {"name": "Linked", "ref": "${item_id}"}},
             "expect": {"status": 201}},
            {"id": "C4", "criteria": ["M01-AC2"],
             "request": {"method": "GET", "path": "/health"},
             "expect": {"status": 200, "body_contains": ["ok"],
                        "json_equals": {"status": "ok", "info.service": "items-fixture"}}},
        ],
    }


class CurlValidatorTest(unittest.TestCase):
    def setUp(self):
        self.t = helpers.TempEnv().__enter__()
        self.addCleanup(self.t.__exit__, None, None, None)
        # author-checks.md and backend-dev/Loop-instructions.md are written by T034/T032; stub
        # them here so this test does not depend on those tasks being done first.
        prompts = os.path.join(self.t.root, "loops", "shared", "prompts")
        self.t.write_file(os.path.join("steps", "author-checks.md"), "STEP author-checks\n",
                          base=prompts)
        self.t.write_file("Loop-instructions.md", "LOOP BACKEND (test)\n",
                          base=os.path.join(self.t.root, "loops", "backend-dev"))
        self.port = free_port()
        self.loop_dir = os.path.join(self.t.workspace_dir, "backend-dev")
        self.run_state = {"invocation_count": 0}
        self.config = samples.config()
        self.plan = samples.plan()
        self.plan["runtime"] = {
            "start_command": f"{sys.executable} {FIXTURE_SERVER} {self.port}",
            "cwd": ".",
            "base_url": f"http://127.0.0.1:{self.port}",
            "ready_url": f"http://127.0.0.1:{self.port}/health",
            "openapi_path": "openapi.json",
        }
        self.t.write_file("openapi.json", json.dumps(TARGET_OPENAPI), base=self.t.target_dir)

    def runner(self):
        return ClaudeRunner(self.t.root, "backend-dev", self.loop_dir, self.config,
                            Redactor(self.config), self.run_state, env=self.t.env)

    def ctx(self, milestone=None, trial=1):
        milestone = milestone or MILESTONE
        trial_dir = os.path.join(self.loop_dir, "state", "milestones", milestone["id"], "trials",
                                 str(trial))
        return types.SimpleNamespace(
            loop="backend-dev", loop_dir=self.loop_dir, repo_root=self.t.root, workspace=None,
            run_state=self.run_state, plan=self.plan, milestone=milestone, trial=trial,
            trial_dir=trial_dir, evidence_dir=os.path.join(trial_dir, "evidence"),
            target_dir=self.t.target_dir, config=self.config, runtime=self.plan["runtime"],
            runner=self.runner(), redactor=Redactor(self.config), env=self.t.env,
            api_spec_path=None, input_dirs=[], context=None)

    def scenario(self, checks_obj):
        self.t.write_scenario({"steps": {"author-checks": {"structured_output": checks_obj}}})

    def author_calls(self):
        return [c for c in self.t.fake_calls() if c["step"] == "author-checks"]

    def checks_path(self, mid="M01"):
        return os.path.join(self.loop_dir, "state", "milestones", mid, "checks.json")

    # --- the happy path, chained checks, evidence, and freezing -------------------------------

    def test_valid_checks_all_pass_with_evidence_and_capture(self):
        self.scenario(valid_checks())
        result = curl.validate(self.ctx(trial=1))
        self.assertEqual(result["kind"], "curl")
        self.assertEqual(schema.validate(dict(result, passed=True, boundary={"passed": True,
                                              "violations": []}), "validation-result.schema.json"),
                         [])
        self.assertTrue(all(c["passed"] for c in result["checks"]), result["checks"])
        self.assertEqual({c["criterion_id"]: c["passed"] for c in result["criteria"]},
                         {"M01-AC1": True, "M01-AC2": True})
        self.assertEqual(result["contract"], {"passed": True, "unmatched_operations": []})

        trial_dir = self.ctx(trial=1).trial_dir
        for check in result["checks"]:
            body_path = os.path.join(trial_dir, check["response"]["body_path"])
            headers_path = os.path.join(trial_dir, check["response"]["headers_path"])
            self.assertTrue(os.path.exists(body_path), body_path)
            self.assertTrue(os.path.exists(headers_path), headers_path)
            self.assertTrue(check["command"].startswith("curl "), check["command"])
        for entry in result["criteria"]:
            for path in entry["evidence"]:
                self.assertTrue(os.path.exists(os.path.join(trial_dir, path)), path)

        with open(os.path.join(trial_dir, "evidence", "C1.body"), encoding="utf-8") as f:
            first_id = json.load(f)["id"]
        with open(os.path.join(trial_dir, "evidence", "C2.body"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"id": first_id, "name": "Widget"})
        with open(os.path.join(trial_dir, "evidence", "C3.body"), encoding="utf-8") as f:
            second = json.load(f)
        self.assertEqual(second["ref"], first_id)  # ${item_id} substituted into the request body

    def test_checks_are_authored_once_then_frozen(self):
        self.scenario(valid_checks())
        curl.validate(self.ctx(trial=1))
        self.assertEqual(len(self.author_calls()), 1)
        frozen = state.read_json(self.checks_path())
        self.assertEqual(frozen, valid_checks())

        # A trial-2 scenario answer that would change the checks is never consulted.
        self.scenario({"milestone_id": "M01", "checks": [
            {"id": "different", "criteria": ["M01-AC1", "M01-AC2"],
             "request": {"method": "GET", "path": "/health"}, "expect": {"status": 200}}]})
        result = curl.validate(self.ctx(trial=2))
        self.assertEqual(len(self.author_calls()), 1)  # not called again
        self.assertEqual([c["check_id"] for c in result["checks"]], ["C1", "C2", "C3", "C4"])
        self.assertEqual(state.read_json(self.checks_path()), frozen)  # unchanged on disk

    # --- failures -------------------------------------------------------------------------------

    def test_a_failing_expectation_fails_only_its_own_check_and_criterion(self):
        checks = valid_checks()
        checks["checks"][3]["expect"]["status"] = 599  # C4: GET /health really returns 200
        self.scenario(checks)
        result = curl.validate(self.ctx(trial=1))
        by_id = {c["check_id"]: c for c in result["checks"]}
        self.assertFalse(by_id["C4"]["passed"])
        self.assertTrue(by_id["C1"]["passed"] and by_id["C2"]["passed"] and by_id["C3"]["passed"])
        self.assertTrue(by_id["C4"]["failures"])
        self.assertIn("599", by_id["C4"]["failures"][0])
        by_criterion = {c["criterion_id"]: c for c in result["criteria"]}
        self.assertFalse(by_criterion["M01-AC2"]["passed"])
        self.assertTrue(by_criterion["M01-AC1"]["passed"])  # unaffected by the unrelated failure

    def test_check_on_an_operation_missing_from_the_openapi_document_fails_the_contract(self):
        checks = valid_checks()
        checks["checks"].append({"id": "C5", "criteria": ["M01-AC2"],
                                 "request": {"method": "DELETE", "path": "/items/1"},
                                 "expect": {"status": 204}})
        self.scenario(checks)
        result = curl.validate(self.ctx(trial=1))
        self.assertFalse(result["contract"]["passed"])
        self.assertTrue(any("DELETE" in op and "items" in op
                            for op in result["contract"]["unmatched_operations"]),
                        result["contract"]["unmatched_operations"])

    def test_missing_criterion_coverage_is_rejected_as_invalid_output(self):
        checks = valid_checks()
        checks["checks"] = [c for c in checks["checks"] if "M01-AC2" not in c["criteria"]]
        self.scenario(checks)
        with self.assertRaises(curl.InvalidChecksError) as cm:
            curl.validate(self.ctx(trial=1))
        self.assertIn("invalid-output", str(cm.exception))
        self.assertIn("M01-AC2", str(cm.exception))
        self.assertIsNone(state.read_json(self.checks_path()))  # nothing frozen on failure

    def test_a_trial_after_failed_authoring_authors_again(self):
        uncovered = valid_checks()
        uncovered["checks"] = [c for c in uncovered["checks"] if "M01-AC2" not in c["criteria"]]
        self.t.write_scenario({"steps": {"author-checks": [{"structured_output": uncovered},
                                                           {"structured_output": valid_checks()}]}})
        with self.assertRaises(curl.InvalidChecksError):
            curl.validate(self.ctx(trial=1))
        result = curl.validate(self.ctx(trial=2))  # used to crash: nothing frozen to load
        self.assertEqual(len(self.author_calls()), 2)
        self.assertTrue(all(c["passed"] for c in result["checks"]), result["checks"])
        self.assertEqual(state.read_json(self.checks_path()), valid_checks())

    def test_prepare_freezes_checks_and_validate_reuses_them(self):
        self.scenario(valid_checks())
        curl.prepare(self.ctx(trial=1))
        self.assertEqual(state.read_json(self.checks_path()), valid_checks())
        curl.validate(self.ctx(trial=1))
        self.assertEqual(len(self.author_calls()), 1)

    def test_duplicate_check_ids_are_rejected(self):
        checks = valid_checks()
        checks["checks"][1]["id"] = "C1"  # a failing C1 could otherwise hide behind a passing one
        self.scenario(checks)
        with self.assertRaises(curl.InvalidChecksError) as cm:
            curl.validate(self.ctx(trial=1))
        self.assertEqual(cm.exception.reason, "invalid-output")
        self.assertIn("repeated: C1", str(cm.exception))
        self.assertIsNone(state.read_json(self.checks_path()))

    def test_check_ids_that_are_not_safe_file_names_are_rejected(self):
        for bad in ("C1/list", "../escape", ""):
            checks = valid_checks()
            checks["checks"][0]["id"] = bad
            self.scenario(checks)
            with self.assertRaises(curl.InvalidChecksError) as cm:
                curl.validate(self.ctx(trial=1))
            self.assertIn(repr(bad), str(cm.exception))
        self.assertFalse(os.path.exists(os.path.join(self.ctx().trial_dir, "escape.body")))

    def test_a_failed_author_checks_call_keeps_its_own_reason(self):
        self.t.write_scenario({"steps": {"author-checks": {"exit_code": 1,
                                                           "api_error_status": 429}}})
        with self.assertRaises(CallFailed) as cm:
            curl.validate(self.ctx(trial=1))
        self.assertNotIsInstance(cm.exception, curl.InvalidChecksError)
        self.assertEqual((cm.exception.reason, cm.exception.failure_class),
                         ("rate-limited", "service"))

    # --- how curl is invoked -------------------------------------------------------------------

    def single_check(self, check):
        milestone = dict(MILESTONE, acceptance_criteria=MILESTONE["acceptance_criteria"][:1])
        self.scenario({"milestone_id": "M01", "checks": [dict(check, id="C1",
                                                                criteria=["M01-AC1"])]})
        result = curl.validate(self.ctx(milestone=milestone, trial=1))
        return result["checks"][0]

    def test_json_body_without_headers_is_sent_as_json(self):
        check = self.single_check({"request": {"method": "POST", "path": "/items",
                                               "body": {"name": "Bare"}},
                                   "expect": {"status": 201, "json_equals": {"name": "Bare"}}})
        self.assertTrue(check["passed"], check["failures"])
        self.assertIn("Content-Type: application/json", check["command"])

    def test_path_without_leading_slash_is_relative_to_base_url(self):
        check = self.single_check({"request": {"method": "GET", "path": "health"},
                                   "expect": {"status": 200}})
        self.assertTrue(check["passed"], check["failures"])

    def test_head_check_does_not_hang(self):
        check = self.single_check({"request": {"method": "HEAD", "path": "/health"},
                                   "expect": {"status": 200}})
        self.assertTrue(check["passed"], check["failures"])

    def test_a_body_that_is_not_utf8_is_evidence_not_a_crash(self):
        check = self.single_check({"request": {"method": "GET", "path": "/binary"},
                                   "expect": {"status": 200, "body_contains": ["PNG"]}})
        self.assertTrue(check["passed"], check["failures"])

    def test_a_hanging_endpoint_fails_its_check_instead_of_blocking(self):
        with mock.patch.object(curl, "CHECK_TIMEOUT_SECONDS", 1):
            check = self.single_check({"request": {"method": "GET", "path": "/slow"},
                                       "expect": {"status": 200}})
        self.assertFalse(check["passed"])
        self.assertTrue(any("curl exited 28" in f for f in check["failures"]), check["failures"])


if __name__ == "__main__":
    unittest.main()
