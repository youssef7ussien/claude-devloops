import json
import os
import time
import unittest

import helpers
import samples
from devloops import claude, schema, state
from devloops.redact import Redactor

IMPLEMENTED = {"tasks": [{"task_id": "M01-T01", "status": "implemented", "note": ""}],
               "assumptions": [], "needs_input": [], "files_changed": ["app.py"]}
UI_RESULT = {"criteria": [{"criterion_id": "M01-AC1", "passed": True, "observed": "list shown",
                           "evidence": ["evidence/s.png"]}],
             "network_requests": [{"method": "GET", "url": "http://127.0.0.1:8765/items"}]}


class ClaudeRunnerTest(unittest.TestCase):
    def setUp(self):
        self.t = helpers.TempEnv().__enter__()
        self.addCleanup(self.t.__exit__, None, None, None)
        prompts = os.path.join(self.t.root, "loops", "shared", "prompts")
        self.t.write_file("common.md", "COMMON RULES\n", base=prompts)
        for step in claude.STEPS:
            self.t.write_file(os.path.join("steps", f"{step}.md"), f"STEP {step}\n", base=prompts)
        self.t.write_file("Loop-instructions.md", "LOOP BACKEND\n",
                          base=os.path.join(self.t.root, "loops", "backend-dev"))
        self.loop_dir = os.path.join(self.t.workspace_dir, "backend-dev")
        self.config = samples.config()
        self.run_state = {"invocation_count": 0}

    def runner(self, secrets=None):
        config = dict(self.config, secrets=secrets or {"env": [], "literals": []})
        return claude.ClaudeRunner(self.t.root, "backend-dev", self.loop_dir, config,
                                   Redactor(config), self.run_state, env=self.t.env)

    def call(self, step, answer, runner=None, **kw):
        self.t.write_scenario({"steps": {step: answer}})
        kw.setdefault("target_dir", self.t.target_dir)
        return (runner or self.runner()).call(step, kw.pop("context", {"milestone": "M01"}), **kw)

    def last_argv(self):
        return self.t.fake_calls()[-1]["argv"]

    def flag_values(self, argv, flag):
        i = argv.index(flag) + 1
        values = []
        while i < len(argv) and not argv[i].startswith("--"):
            values.append(argv[i])
            i += 1
        return values

    # --- prompt ---

    def test_prompt_composition_and_saved_copy(self):
        out = self.call("plan", {"structured_output": samples.plan()},
                        context={"requirements_path": "/r/prd.md"})
        prompt = self.t.fake_calls()[-1]["prompt"]
        self.assertTrue(prompt.startswith("<!-- step: plan -->\n"))
        order = [prompt.index(s) for s in ("COMMON RULES", "LOOP BACKEND", "STEP plan", "## Context")]
        self.assertEqual(order, sorted(order))
        self.assertIn('"requirements_path": "/r/prd.md"', prompt)
        self.assertEqual(out.record["prompt_path"], os.path.join("state", "prompts", "0001-plan.md"))
        with open(os.path.join(self.loop_dir, out.record["prompt_path"])) as f:
            self.assertEqual(f.read(), prompt)

    def test_prompt_is_redacted_before_it_is_saved_or_sent(self):
        runner = self.runner({"env": [], "literals": ["s3cr3t"]})
        out = self.call("plan", {"structured_output": samples.plan()}, runner=runner,
                        context={"note": "token s3cr3t"})
        prompt = self.t.fake_calls()[-1]["prompt"]
        self.assertNotIn("s3cr3t", prompt)
        self.assertIn("token ***", prompt)
        self.assertTrue(out.record["redacted"])

    def test_large_prompt_goes_through_stdin(self):
        out = self.call("plan", {"structured_output": samples.plan()},
                        context={"blob": "x" * 150_000})
        self.assertTrue(out.ok)
        argv = self.last_argv()
        self.assertEqual(argv[0], "-p")
        self.assertEqual(argv[1], "--session-id")
        self.assertIn("x" * 1000, self.t.fake_calls()[-1]["prompt"])

    # --- argv per step ---

    def test_read_only_steps(self):
        for step, answer in (("plan", samples.plan()), ("replan", samples.plan()),
                             ("author-checks", samples.checks())):
            with self.subTest(step=step):
                self.call(step, {"structured_output": answer})
                argv = self.last_argv()
                self.assertEqual(self.flag_values(argv, "--allowedTools"), ["Read", "Glob", "Grep"])
                self.assertEqual(self.flag_values(argv, "--disallowedTools"),
                                 ["Edit", "Write", "MultiEdit", "NotebookEdit", "Bash"])
                self.assertNotIn("--permission-mode", argv)
                self.assertEqual(self.flag_values(argv, "--output-format"), ["json"])
                self.assertEqual(self.t.fake_calls()[-1]["allowed_roots"], "")

    def test_json_schema_matches_the_step(self):
        self.call("plan", {"structured_output": samples.plan()})
        sent = json.loads(self.flag_values(self.last_argv(), "--json-schema")[0])
        full = schema.load("plan.schema.json")
        # Claude Code rejects the draft 2020-12 `$schema` marker, so it is not sent (T076).
        self.assertNotIn("$schema", sent)
        self.assertNotIn("$id", sent)
        self.assertEqual(sent, {k: v for k, v in full.items() if k not in ("$schema", "$id")})
        self.call("implement", {"structured_output": IMPLEMENTED})
        self.assertEqual(json.loads(self.flag_values(self.last_argv(), "--json-schema")[0]),
                         claude.IMPLEMENT_RESULT_SCHEMA)

    def test_implement_and_fix_steps(self):
        self.config["implement_tools"] = ["Read", "Edit", "Bash"]
        for step in ("implement", "fix"):
            with self.subTest(step=step):
                self.call(step, {"structured_output": IMPLEMENTED})
                argv = self.last_argv()
                self.assertEqual(self.flag_values(argv, "--allowedTools"), ["Read", "Edit", "Bash"])
                self.assertEqual(self.flag_values(argv, "--permission-mode"), ["acceptEdits"])
                self.assertNotIn("--disallowedTools", argv)
                self.assertEqual(self.t.fake_calls()[-1]["allowed_roots"], self.t.target_dir)
                self.assertEqual(self.t.fake_calls()[-1]["cwd"], self.t.target_dir)

    def test_common_flags(self):
        self.config.update(model="claude-sonnet-5", max_budget_usd_per_invocation=0.5)
        out = self.call("implement", {"structured_output": IMPLEMENTED})
        argv = self.last_argv()
        self.assertEqual(self.flag_values(argv, "--session-id"), [out.record["session_id"]])
        self.assertIn("--strict-mcp-config", argv)
        self.assertEqual(self.flag_values(argv, "--model"), ["claude-sonnet-5"])
        self.assertEqual(self.flag_values(argv, "--max-budget-usd"), ["0.5"])
        with open(self.flag_values(argv, "--settings")[0]) as f:
            settings = json.load(f)
        hook = settings["hooks"]["PreToolUse"][0]
        self.assertEqual(hook["matcher"], "Edit|Write|MultiEdit|NotebookEdit")
        self.assertTrue(hook["hooks"][0]["command"].endswith(
            os.path.join("loops", "shared", "hooks", "guard_writes.py")))

    def test_add_dirs_are_passed_resolved_and_deduplicated(self):
        inputs_dir = os.path.join(self.t.base, "inputs")
        os.makedirs(inputs_dir)
        self.call("plan", {"structured_output": samples.plan()},
                  add_dirs=[inputs_dir, inputs_dir + "/", os.path.join(self.t.base, "missing")])
        self.assertEqual(self.flag_values(self.last_argv(), "--add-dir"), [inputs_dir])

    def test_optional_flags_are_omitted_by_default(self):
        self.call("plan", {"structured_output": samples.plan()})
        argv = self.last_argv()
        for flag in ("--model", "--max-budget-usd", "--mcp-config", "--verbose", "--add-dir"):
            self.assertNotIn(flag, argv)

    def test_validate_ui_streams_and_counts_tool_uses(self):
        trial_dir = os.path.join(self.loop_dir, "state", "milestones", "M01", "trials", "1")
        mcp = self.t.write_file("mcp.json", json.dumps({"mcpServers": {}}))
        out = self.call("validate-ui", {"structured_output": UI_RESULT, "tool_uses": [
            "mcp__playwright__browser_navigate", "mcp__playwright__browser_snapshot",
            "mcp__playwright__browser_snapshot"]}, trial_dir=trial_dir, mcp_config_path=mcp,
            milestone_id="M01", trial=1)
        argv = self.last_argv()
        self.assertEqual(self.flag_values(argv, "--output-format"), ["stream-json"])
        self.assertIn("--verbose", argv)
        self.assertEqual(self.flag_values(argv, "--allowedTools"), ["Read", "mcp__playwright__*"])
        self.assertIn("Bash", self.flag_values(argv, "--disallowedTools"))
        self.assertEqual(self.flag_values(argv, "--mcp-config"), [mcp])
        self.assertTrue(out.ok, out.failure_detail)
        self.assertEqual(out.structured_output, UI_RESULT)
        self.assertEqual(out.tool_uses["mcp__playwright__browser_snapshot"], 2)
        events = state.read_jsonl(os.path.join(trial_dir, "stream.jsonl"))
        self.assertEqual(events[-1]["type"], "result")

    # --- records ---

    def test_record_is_valid_and_maps_tokens(self):
        out = self.call("implement", {"structured_output": IMPLEMENTED, "total_cost_usd": 0.25,
                                      "usage": {"input_tokens": 10, "cache_read_input_tokens": None}},
                        milestone_id="M01", trial=1)
        records = state.read_jsonl(os.path.join(self.loop_dir, "state", "invocations.jsonl"))
        self.assertEqual(records, [out.record])
        self.assertEqual(schema.validate(out.record, "invocation-record.schema.json"), [])
        self.assertEqual(out.record["tokens"], {"input": 10, "output": 300, "cache_creation": 0,
                                                "cache_read": None})
        self.assertEqual((out.record["cost_usd"], out.record["milestone_id"], out.record["trial"]),
                         (0.25, "M01", 1))
        self.assertEqual(out.record["failure_class"], "none")

    def test_missing_usage_gives_null_tokens(self):
        out = self.call("implement", {"structured_output": IMPLEMENTED, "usage": None})
        self.assertEqual(out.record["tokens"], {"input": None, "output": None,
                                                "cache_creation": None, "cache_read": None})

    def test_invocation_count_is_persisted_and_used_as_seq(self):
        self.call("plan", {"exit_code": 1, "no_result": True})
        self.call("plan", {"structured_output": samples.plan()})
        self.assertEqual(state.read_json(os.path.join(self.loop_dir, "state", "run.json")),
                         {"invocation_count": 2})
        seqs = [r["seq"] for r in state.read_jsonl(os.path.join(self.loop_dir, "state",
                                                                "invocations.jsonl"))]
        self.assertEqual(seqs, [1, 2])
        self.assertTrue(os.path.exists(os.path.join(self.loop_dir, "state", "prompts",
                                                    "0002-plan.md")))

    def test_count_is_written_before_the_call(self):
        # The fake sleeps; while it runs, run.json already holds the new count.
        self.t.write_scenario({"steps": {"plan": {"structured_output": samples.plan(),
                                                  "sleep_seconds": 1}}})
        import threading
        seen = {}

        def peek():
            time.sleep(0.5)
            seen["run"] = state.read_json(os.path.join(self.loop_dir, "state", "run.json"))
        thread = threading.Thread(target=peek)
        thread.start()
        self.runner().call("plan", {}, target_dir=self.t.target_dir)
        thread.join()
        self.assertEqual(seen["run"], {"invocation_count": 1})

    # --- classification ---

    def assert_failure(self, out, cls, reason):
        self.assertFalse(out.ok)
        self.assertEqual((out.failure_class, out.failure_reason), (cls, reason))
        self.assertEqual(out.record["failure_class"], cls)

    def test_service_failures_by_api_status(self):
        for status, reason in ((429, "rate-limited"), (401, "auth-failed"), (403, "auth-failed"),
                               (500, "service-unavailable"), (529, "service-unavailable")):
            with self.subTest(status=status):
                out = self.call("implement", {"api_error_status": status})
                self.assert_failure(out, "service", reason)
                self.assertEqual(out.record["api_error_status"], status)

    def test_service_failures_by_stderr_without_result(self):
        for stderr, reason in (("Error: connect ECONNREFUSED 1.2.3.4:443", "service-unavailable"),
                               ("Invalid API key · Please run /login", "auth-failed"),
                               ("API Error: 429 rate_limit_error", "rate-limited")):
            with self.subTest(stderr=stderr):
                out = self.call("implement", {"no_result": True, "exit_code": 1, "stderr": stderr})
                self.assert_failure(out, "service", reason)
                self.assertTrue(out.record["is_error"])

    def test_unknown_errors_are_work_failures(self):
        self.assert_failure(self.call("implement", {"no_result": True, "exit_code": 1,
                                                    "stderr": "Segmentation fault at 0x500"}),
                            "work", "claude-error")
        self.assert_failure(self.call("implement", {"is_error": True}), "work", "claude-error")
        self.assert_failure(self.call("implement", {"subtype": "error_max_budget_usd",
                                                    "structured_output": IMPLEMENTED}),
                            "work", "claude-error")
        self.assert_failure(self.call("implement", {"api_error_status": 400}), "work",
                            "claude-error")

    def test_stderr_is_ignored_when_a_result_exists(self):
        out = self.call("implement", {"is_error": True, "exit_code": 1,
                                      "stderr": "connect ECONNREFUSED"})
        self.assert_failure(out, "work", "claude-error")

    def test_invalid_or_missing_structured_output(self):
        out = self.call("implement", {"structured_output": {"tasks": []}})
        self.assert_failure(out, "work", "invalid-output")
        self.assertIn("missing required property", out.failure_detail)
        self.assert_failure(self.call("implement", {}), "work", "invalid-output")

    def test_timeout_kills_the_process_group(self):
        self.config["invocation_timeout_seconds"] = 1
        started = time.monotonic()
        out = self.call("implement", {"sleep_seconds": 30, "structured_output": IMPLEMENTED})
        self.assertLess(time.monotonic() - started, 15)
        self.assert_failure(out, "work", "timeout")
        self.assertTrue(out.record["timed_out"])

    # --- boundary brackets and the guard hook ---

    def test_snapshot_brackets_the_call(self):
        marker = os.path.join(self.t.target_dir, "made-by-claude.txt")
        calls = []
        out = self.call("implement", {"structured_output": IMPLEMENTED,
                                      "writes": [{"path": "made-by-claude.txt", "content": "x"}]},
                        snapshot=lambda: calls.append(os.path.exists(marker)) or len(calls))
        self.assertEqual(calls, [False, True])
        self.assertEqual((out.snapshot_before, out.snapshot_after), (1, 2))

    def test_guard_hook_confines_edits_to_the_target(self):
        inside = os.path.join(self.t.target_dir, "src", "app.py")
        outside = os.path.join(self.t.base, "outside.py")
        out = self.call("implement", {"structured_output": IMPLEMENTED, "writes": [
            {"path": inside, "content": "ok", "tool": "Edit"},
            {"path": outside, "content": "bad", "tool": "Write"}]})
        self.assertTrue(os.path.exists(inside))
        self.assertFalse(os.path.exists(outside))
        self.assertEqual([d["tool_name"] for d in out.record["permission_denials"]], ["Write"])

    def test_guard_hook_blocks_every_edit_in_read_only_steps(self):
        inside = os.path.join(self.t.target_dir, "x.py")
        out = self.call("plan", {"structured_output": samples.plan(), "writes": [
            {"path": inside, "content": "x", "tool": "Edit"}]})
        self.assertFalse(os.path.exists(inside))
        self.assertEqual(len(out.record["permission_denials"]), 1)


class ClassifyTest(unittest.TestCase):
    def test_api_status(self):
        self.assertIsNone(claude.classify_api_status(None))
        self.assertIsNone(claude.classify_api_status(404))
        self.assertEqual(claude.classify_api_status(503), "service-unavailable")

    def test_stderr_patterns(self):
        self.assertEqual(claude.classify_stderr("getaddrinfo ENOTFOUND api.anthropic.com"),
                         "service-unavailable")
        self.assertEqual(claude.classify_stderr("OAuth token has expired"), "auth-failed")
        self.assertIsNone(claude.classify_stderr("TypeError: x is undefined (line 401)"))
        self.assertIsNone(claude.classify_stderr(""))


if __name__ == "__main__":
    unittest.main()
