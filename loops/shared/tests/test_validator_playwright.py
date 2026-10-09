"""Direct tests of the Playwright validator (T038, research R-10/R-12).

These exercise `devloops.validators.playwright.validate(ctx)` on its own, with a `ctx` built the
same way `engine._adapter_context` builds one. The frontend runtime is a real
`python3 -m http.server` serving a static page; the backend, when one is configured, is the
fixture API server. Fake Claude answers `validate-ui` in stream-json with Playwright `tool_use`
events (the page's requests in a `browser_network_requests` result) and the structured
`criteria[]`. The pass/fail verdict is the
engine's own `compute_pass`, the same rule a real trial uses. The validator does not exist until
T045; until then this module fails to import, which is expected (the tests for a story are
written first and must fail before its implementation tasks).
"""
import json
import os
import socket
import sys
import types
import unittest

import helpers
import samples
from devloops import schema
from devloops.claude import ClaudeRunner
from devloops.engine import compute_pass
from devloops.redact import Redactor
from devloops.runtime import Runtime
from devloops.validators import playwright

FIXTURE_SERVER = os.path.join(helpers.FIXTURES_DIR, "http_app.py")
PLAYWRIGHT_TOOLS = ["mcp__playwright__browser_navigate", "mcp__playwright__browser_snapshot"]

API_SPEC = {
    "openapi": "3.0.3", "info": {"title": "items", "version": "1.0.0"},
    "paths": {"/items": {"get": {"responses": {"200": {"description": "the items"}}}}},
}

MILESTONE = {
    "id": "M01",
    "title": "Item list page",
    "goal": "Visitors see the list of items",
    "depends_on": [],
    "tasks": [{"id": "M01-T01", "title": "Items page", "description": "Render the items",
               "requirement_refs": ["FR-1"]}],
    "acceptance_criteria": [
        {"id": "M01-AC1", "text": "The home page shows the heading 'Items'",
         "requirement_refs": ["FR-1"]},
        {"id": "M01-AC2", "text": "The page lists the items the backend returns",
         "requirement_refs": ["FR-1"]},
    ],
}


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class PlaywrightValidatorTest(unittest.TestCase):
    def setUp(self):
        self.t = helpers.TempEnv().__enter__()
        self.addCleanup(self.t.__exit__, None, None, None)
        # validate-ui.md and frontend-dev/Loop-instructions.md are written by T043/T041; stub
        # them here so this test does not depend on those tasks being done first.
        prompts = os.path.join(self.t.root, "loops", "shared", "prompts")
        self.t.write_file(os.path.join("steps", "validate-ui.md"), "STEP validate-ui\n",
                          base=prompts)
        self.t.write_file("Loop-instructions.md", "LOOP FRONTEND (test)\n",
                          base=os.path.join(self.t.root, "loops", "frontend-dev"))
        self.ui_port, self.api_port = free_port(), free_port()
        self.ui_url = f"http://127.0.0.1:{self.ui_port}"
        self.api_url = f"http://127.0.0.1:{self.api_port}"
        self.loop_dir = os.path.join(self.t.workspace_dir, "frontend-dev")
        self.run_state = {"invocation_count": 0, "ui_url": None}
        self.config = samples.config()
        # Never started: the fake answers without a real MCP server; only the argv is checked.
        self.config["playwright"] = {"mcp_command": ["fake-mcp", "--headless"]}
        self.plan = samples.plan()
        self.plan["runtime"] = {
            "start_command": f"{sys.executable} -m http.server {self.ui_port} --bind 127.0.0.1",
            "cwd": ".",
            "base_url": self.ui_url,
            "ready_url": self.ui_url + "/",
        }
        self.t.write_file("index.html", "<h1>Items</h1>\n", base=self.t.target_dir)
        self.t.write_file(os.path.join("state", "api-spec.json"), json.dumps(API_SPEC),
                          base=self.loop_dir)

    def use_backend(self, how):
        if how == "start":
            self.config["backend"] = {
                "start_command": f"{sys.executable} {FIXTURE_SERVER} {self.api_port}",
                "cwd": ".", "base_url": self.api_url, "ready_url": self.api_url + "/health"}
        elif how == "base_url":
            self.config["backend"] = {"base_url": self.api_url}
        else:
            self.config["backend"] = {}

    @property
    def trial_dir(self):
        return os.path.join(self.loop_dir, "state", "milestones", "M01", "trials", "1")

    @property
    def evidence_dir(self):
        return os.path.join(self.trial_dir, "evidence")

    def ctx(self):
        return types.SimpleNamespace(
            loop="frontend-dev", loop_dir=self.loop_dir, kit=self.t.kit(), workspace=None,
            run_state=self.run_state, plan=self.plan, milestone=MILESTONE, trial=1,
            trial_dir=self.trial_dir, evidence_dir=self.evidence_dir,
            target_dir=self.t.target_dir, config=self.config, runtime=self.plan["runtime"],
            runner=ClaudeRunner(self.t.kit(), "frontend-dev", self.loop_dir, self.config,
                                Redactor(self.config), self.run_state, env=self.t.env),
            redactor=Redactor(self.config), env=self.t.env, api_spec_path=None, input_dirs=[],
            context=None)

    def entry(self, cid, passed=True, observed=None, evidence=None):
        return {"criterion_id": cid, "passed": passed,
                "steps": ["navigate to the home page", "take a snapshot"],
                "observed": f"{cid} observed on the page" if observed is None else observed,
                "evidence": [f"evidence/{cid}.png"] if evidence is None else evidence}

    def answer(self, criteria=None, network=None, tool_uses=None, evidence_files=None):
        """A `validate-ui` answer; screenshots are 'written by the MCP server' into evidence/, and
        `network` is the browser's network log the call read (unless `tool_uses` is given)."""
        criteria = [self.entry("M01-AC1"), self.entry("M01-AC2")] if criteria is None else criteria
        if network is None:
            network = [{"method": "GET", "url": self.ui_url + "/", "status": 200},
                       {"method": "GET", "url": self.api_url + "/items", "status": 200}]
        files = evidence_files if evidence_files is not None else ["M01-AC1.png", "M01-AC2.png"]
        return {"structured_output": {"criteria": criteria},
                "tool_uses": (PLAYWRIGHT_TOOLS + [helpers.network_log(network)]
                              if tool_uses is None else tool_uses),
                "writes": [{"path": os.path.join(self.evidence_dir, f), "content": "PNG"}
                           for f in files]}

    def validate(self, answer):
        self.t.write_scenario({"steps": {"validate-ui": answer}})
        return playwright.validate(self.ctx())

    def verdict(self, result):
        full = dict(result, boundary={"passed": True, "violations": []})
        passed, problems = compute_pass(MILESTONE, full, self.trial_dir)
        self.assertEqual(schema.validate(dict(full, passed=passed),
                                         "validation-result.schema.json"), [])
        return passed, problems

    def ui_context(self):
        """The Context block of the last `validate-ui` prompt."""
        prompt = self.ui_calls()[-1]["prompt"]
        return json.loads(prompt.split("```json\n", 1)[1].split("\n```", 1)[0])

    def ui_calls(self):
        return [c for c in self.t.fake_calls() if c["step"] == "validate-ui"]

    # --- pass ----------------------------------------------------------------------------------

    def test_all_criteria_pass_with_evidence(self):
        self.use_backend("start")
        result = self.validate(self.answer())
        self.assertEqual(result["kind"], "playwright")
        self.assertEqual(result["ui_url"], self.ui_url)
        self.assertEqual(result["contract"], {"passed": True, "unmatched_operations": []})
        passed, problems = self.verdict(result)
        self.assertTrue(passed, problems)
        # The UI URL is recorded as the loop's output (D-2), and the stream is kept.
        self.assertEqual(self.run_state["ui_url"], self.ui_url)
        with open(os.path.join(self.loop_dir, "outputs", "ui-url.txt"), encoding="utf-8") as f:
            self.assertEqual(f.read().strip(), self.ui_url)
        self.assertTrue(os.path.exists(os.path.join(self.trial_dir, "stream.jsonl")))

    def test_an_already_running_backend_is_used_by_base_url(self):
        self.use_backend("base_url")
        # Start the fixture ourselves, as a developer would; the validator must not start one.
        with Runtime(f"{sys.executable} {FIXTURE_SERVER} {self.api_port}", self.t.target_dir,
                     self.api_url + "/health", 30):
            result = self.validate(self.answer())
            context = self.ui_calls()[-1]["prompt"]
        self.assertTrue(self.verdict(result)[0])
        self.assertIn(f'"base_url": "{self.api_url}"', context)

    # --- fail ----------------------------------------------------------------------------------

    def test_a_missing_criterion_fails(self):
        self.use_backend("start")
        passed, problems = self.verdict(self.validate(self.answer(
            criteria=[self.entry("M01-AC1")], evidence_files=["M01-AC1.png"])))
        self.assertFalse(passed)
        self.assertIn("M01-AC2: no result", problems)

    def test_empty_observed_or_evidence_fails(self):
        self.use_backend("start")
        for criteria in ([self.entry("M01-AC1"), self.entry("M01-AC2", observed="  ")],
                         [self.entry("M01-AC1"), self.entry("M01-AC2", evidence=[])]):
            passed, problems = self.verdict(self.validate(self.answer(criteria=criteria)))
            self.assertFalse(passed)
            self.assertTrue(any(p.startswith("M01-AC2: ") for p in problems), problems)

    def test_cited_evidence_that_does_not_exist_fails(self):
        self.use_backend("start")
        passed, problems = self.verdict(self.validate(self.answer(evidence_files=["M01-AC1.png"])))
        self.assertFalse(passed)
        self.assertIn("M01-AC2: evidence evidence/M01-AC2.png does not exist", problems)

    def test_no_playwright_tool_use_fails_every_criterion(self):
        self.use_backend("start")
        result = self.validate(self.answer(tool_uses=["Read"]))
        self.assertTrue(all(not c["passed"] for c in result["criteria"]), result["criteria"])
        self.assertTrue(all("Playwright" in c["observed"] for c in result["criteria"]))
        self.assertFalse(self.verdict(result)[0])

    def test_a_network_request_outside_the_api_spec_fails_the_contract(self):
        self.use_backend("start")
        network = [{"method": "GET", "url": self.api_url + "/items", "status": 200},
                   {"method": "DELETE", "url": self.api_url + "/items/1", "status": 404},
                   {"method": "GET", "url": self.ui_url + "/app.js", "status": 200}]
        result = self.validate(self.answer(network=network))
        self.assertFalse(result["contract"]["passed"])
        self.assertEqual(result["contract"]["unmatched_operations"],
                         [f"DELETE {self.api_url}/items/1"])  # UI-origin assets are not API calls
        self.assertEqual(result["network_requests"], network)
        self.assertFalse(self.verdict(result)[0])

    def test_requests_come_from_the_browsers_network_log(self):
        self.use_backend("start")
        # Two reads of the log (one before a navigation, one at the end): each request once, a
        # pending one (no status) included. The model reports no requests of its own.
        tool_uses = PLAYWRIGHT_TOOLS + [
            helpers.network_log([{"method": "GET", "url": self.ui_url + "/", "status": 200},
                                 {"method": "GET", "url": self.api_url + "/items",
                                  "status": 200}]),
            helpers.network_log([{"method": "GET", "url": self.api_url + "/items", "status": 200},
                                 {"method": "DELETE", "url": self.api_url + "/items/1"}])]
        result = self.validate(self.answer(tool_uses=tool_uses))
        self.assertEqual(result["network_requests"], [
            {"method": "GET", "url": self.ui_url + "/", "status": 200},
            {"method": "GET", "url": self.api_url + "/items", "status": 200},
            {"method": "DELETE", "url": self.api_url + "/items/1"}])
        self.assertEqual(result["contract"]["unmatched_operations"],
                         [f"DELETE {self.api_url}/items/1"])

    def test_a_call_that_never_reads_the_network_log_fails_the_contract(self):
        self.use_backend("start")
        result = self.validate(self.answer(tool_uses=PLAYWRIGHT_TOOLS))
        self.assertEqual(result["network_requests"], [])
        self.assertEqual(result["contract"], {"passed": False, "unmatched_operations": [],
                                              "problem": playwright.NO_NETWORK_LOG})
        passed, problems = self.verdict(result)
        self.assertFalse(passed)
        self.assertIn("contract check failed: " + playwright.NO_NETWORK_LOG, problems)

    def test_a_unit_test_criterion_is_judged_from_the_drivers_run(self):
        self.use_backend("start")
        self.config["unit_tests"] = {"enabled": True,
                                     "command": f"{sys.executable} -c \"print('3 passed')\""}
        criteria = [self.entry("M01-AC1"),
                    self.entry("M01-AC2", observed="unit tests: 3 passed, exit code 0",
                               evidence=["evidence/unit-tests.log"])]
        result = self.validate(self.answer(criteria=criteria, evidence_files=["M01-AC1.png"]))
        # The tests ran before the call, which got their result and the log to cite.
        unit_tests = self.ui_context()["unit_tests"]
        self.assertEqual((unit_tests["ran"], unit_tests["exit_code"]), (True, 0))
        self.assertEqual(unit_tests["evidence"], "evidence/unit-tests.log")
        self.assertEqual(unit_tests["log_file"],
                         os.path.join(self.trial_dir, "evidence", "unit-tests.log"))
        self.assertEqual(result["unit_tests"]["exit_code"], 0)
        passed, problems = self.verdict(result)
        self.assertTrue(passed, problems)

    def test_without_a_unit_test_command_the_call_is_told_none_ran(self):
        self.use_backend("start")
        result = self.validate(self.answer())
        self.assertEqual(self.ui_context()["unit_tests"], {"ran": False})
        self.assertEqual(result["unit_tests"], {"enabled": False})

    def test_a_declared_command_runs_for_the_call_even_when_not_enabled(self):
        self.use_backend("start")
        # The tests fail, but unit_tests.enabled is off: only a criterion about them can fail.
        self.plan["runtime"]["unit_test_command"] = f"{sys.executable} -c \"exit(1)\""
        result = self.validate(self.answer())
        unit_tests = self.ui_context()["unit_tests"]
        self.assertEqual((unit_tests["ran"], unit_tests["enabled"], unit_tests["exit_code"]),
                         (True, False, 1))
        self.assertEqual((result["unit_tests"]["enabled"], result["unit_tests"]["exit_code"]),
                         (False, 1))
        passed, problems = self.verdict(result)
        self.assertTrue(passed, problems)

    def test_unit_tests_run_with_the_runtimes_up(self):
        self.use_backend("start")
        reach = "import sys, urllib.request as u; [u.urlopen(x) for x in sys.argv[1:]]"
        self.config["unit_tests"] = {"enabled": True, "command": (
            f"{sys.executable} -c \"{reach}\" {self.ui_url}/ {self.api_url}/health")}
        result = self.validate(self.answer())
        self.assertEqual(result["unit_tests"]["exit_code"], 0)

    # --- the network log -----------------------------------------------------------------------

    def contract_problem(self, tool_uses):
        return self.validate(self.answer(tool_uses=tool_uses))["contract"].get("problem")

    def test_an_errored_read_of_the_network_log_is_no_read(self):
        self.use_backend("start")
        read = dict(helpers.network_log([]), is_error=True, result="Error: No open tabs")
        self.assertEqual(self.contract_problem(PLAYWRIGHT_TOOLS + [read]),
                         playwright.NO_NETWORK_LOG)

    def test_a_log_line_that_cannot_be_read_fails_the_contract(self):
        self.use_backend("start")
        read = dict(helpers.network_log([]), result=f"- [POST] {self.api_url}/items (201)")
        self.assertIn("1 line(s) of the browser's network log could not be read",
                      self.contract_problem(PLAYWRIGHT_TOOLS + [read]))

    def test_using_the_browser_after_the_last_read_fails_the_contract(self):
        self.use_backend("start")
        read = helpers.network_log([{"method": "GET", "url": self.ui_url + "/", "status": 200}])
        self.assertIn("used the browser (browser_click) after its last read",
                      self.contract_problem(PLAYWRIGHT_TOOLS + [
                          read, "mcp__playwright__browser_click"]))
        # A screenshot or a snapshot sends nothing.
        self.assertIsNone(self.contract_problem(PLAYWRIGHT_TOOLS + [
            read, "mcp__playwright__browser_take_screenshot", "mcp__playwright__browser_snapshot"]))

    def test_each_outcome_of_a_request_is_kept(self):
        self.use_backend("start")
        items = self.api_url + "/items"
        result = self.validate(self.answer(tool_uses=PLAYWRIGHT_TOOLS + [
            helpers.network_log([{"method": "GET", "url": items, "status": 500},
                                 {"method": "POST", "url": items}]),
            helpers.network_log([{"method": "GET", "url": items, "status": 200},
                                 {"method": "POST", "url": items,
                                  "error": "net::ERR_CONNECTION_REFUSED"}])]))
        # Pending in the first read, failed in the second: one request, with its error.
        self.assertEqual(result["network_requests"], [
            {"method": "GET", "url": items, "status": 500},
            {"method": "GET", "url": items, "status": 200},
            {"method": "POST", "url": items, "error": "net::ERR_CONNECTION_REFUSED"}])

    def use_spec(self, spec):
        self.t.write_file(os.path.join("state", "api-spec.json"), json.dumps(spec),
                          base=self.loop_dir)

    def test_api_calls_through_the_ui_origin_proxy_are_checked(self):
        self.use_backend("start")
        self.use_spec(dict(API_SPEC, servers=[{"url": "/api"}]))
        network = [{"method": "GET", "url": self.ui_url + "/", "status": 200},
                   {"method": "GET", "url": self.ui_url + "/assets/main.js", "status": 200},
                   {"method": "GET", "url": self.ui_url + "/api/items", "status": 200},
                   {"method": "GET", "url": self.ui_url + "/api/secret", "status": 200},
                   {"method": "POST", "url": self.ui_url + "/api/items", "status": 201}]
        result = self.validate(self.answer(network=network))
        # The documented call passes (via the spec's `/api` server path), the page and its assets
        # are skipped, and undocumented proxied calls fail the contract (FR-024).
        self.assertEqual(result["contract"]["unmatched_operations"],
                         [f"GET {self.ui_url}/api/secret", f"POST {self.ui_url}/api/items"])

    def test_without_a_backend_the_ui_loading_itself_never_fails_the_contract(self):
        self.use_backend(None)
        self.use_spec({"openapi": "3.0.3", "info": {"title": "t", "version": "1"}, "paths": {
            "/": {"get": {"responses": {"200": {"description": "root"}}}},
            "/{id}": {"get": {"responses": {"200": {"description": "one"}}}}}})
        network = [{"method": "GET", "url": self.ui_url + "/", "status": 200},
                   {"method": "GET", "url": self.ui_url + "/main.js", "status": 200},
                   {"method": "GET", "url": self.ui_url + "/styles.css", "status": 200}]
        result = self.validate(self.answer(network=network))
        self.assertEqual(result["contract"], {"passed": True, "unmatched_operations": []})

        # A proxied write still reached for a backend nothing could answer (FR-039).
        result = self.validate(self.answer(network=network + [
            {"method": "POST", "url": self.ui_url + "/items", "status": 404}]))
        self.assertFalse(result["contract"]["passed"])
        self.assertIn("no backend is configured", result["contract"]["unmatched_operations"][0])

    def test_without_a_backend_backend_dependent_criteria_never_pass(self):
        self.use_backend(None)
        # The model is told there is no backend (context `backend: null`)...
        result = self.validate(self.answer(criteria=[
            self.entry("M01-AC1"),
            self.entry("M01-AC2", passed=False, observed="no backend is configured")]))
        self.assertIn('"backend": null', self.ui_calls()[-1]["prompt"])
        passed, problems = self.verdict(result)
        self.assertFalse(passed)
        self.assertTrue(any(p.startswith("M01-AC2: failed") for p in problems), problems)

        # ...and even a model that claims a pass cannot pass a criterion that used the API.
        result = self.validate(self.answer())
        self.assertFalse(result["contract"]["passed"])
        self.assertTrue(any("no backend is configured" in op
                            for op in result["contract"]["unmatched_operations"]),
                        result["contract"])
        self.assertFalse(self.verdict(result)[0])

    def test_a_failed_validate_ui_call_raises_with_its_reason(self):
        self.use_backend(None)
        self.t.write_scenario({"steps": {"validate-ui": {"is_error": True}}})
        with self.assertRaises(playwright.ValidateUIError) as cm:
            playwright.validate(self.ctx())
        self.assertEqual(cm.exception.reason, "claude-error")

    def test_an_mcp_server_that_did_not_start_is_a_service_error(self):
        self.use_backend(None)
        answer = dict(self.answer(tool_uses=["Read"]),
                      mcp_servers=[{"name": "playwright", "status": "failed"}])
        self.config["playwright"]["headless"] = False
        with self.assertRaises(playwright.ValidateUIError) as cm:
            self.validate(answer)
        self.assertEqual((cm.exception.reason, cm.exception.failure_class),
                         ("service-unavailable", "service"))
        self.assertIn("no display available (playwright.headless is false)", cm.exception.detail)

    def test_a_pending_mcp_server_without_browser_calls_fails_the_trial(self):
        self.use_backend(None)
        answer = dict(self.answer(tool_uses=["Read"]),
                      mcp_servers=[{"name": "playwright", "status": "pending"}])
        result = self.validate(answer)
        self.assertTrue(all(not c["passed"] for c in result["criteria"]), result["criteria"])

    def test_a_connected_mcp_server_is_not_a_service_error(self):
        self.use_backend("start")
        answer = dict(self.answer(), mcp_servers=[{"name": "playwright", "status": "connected"}])
        self.assertTrue(self.verdict(self.validate(answer))[0])

    def test_runtimes_are_stopped_after_validation(self):
        self.use_backend("start")
        self.validate(self.answer())
        for port in (self.ui_port, self.api_port):
            with socket.socket() as s:
                self.assertNotEqual(s.connect_ex(("127.0.0.1", port)), 0, f"port {port} open")

    # --- the call itself -----------------------------------------------------------------------

    def test_the_call_is_restricted_to_read_and_playwright(self):
        self.use_backend(None)
        self.validate(self.answer())
        argv = self.ui_calls()[-1]["argv"]

        def values(flag):
            i = argv.index(flag) + 1
            out = []
            while i < len(argv) and not argv[i].startswith("-"):
                out.append(argv[i])
                i += 1
            return out

        self.assertEqual(values("--allowedTools"), ["Read", "mcp__playwright__*"])
        disallowed = values("--disallowedTools")
        for tool in ("Edit", "Write", "MultiEdit", "NotebookEdit", "Bash"):
            self.assertIn(tool, disallowed)
        self.assertIn("--strict-mcp-config", argv)
        self.assertEqual(values("--output-format"), ["stream-json"])
        mcp_path = values("--mcp-config")[0]
        self.assertEqual(mcp_path, os.path.join(self.trial_dir, "mcp.json"))
        with open(mcp_path, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"mcpServers": {"playwright": {
                "command": "fake-mcp",
                "args": ["--headless", "--output-dir", self.evidence_dir]}}})


if __name__ == "__main__":
    unittest.main()
