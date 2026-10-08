"""Prompt overrides in `.devloops/prompts/` (002 US7: FR-030 to FR-032; research P-8). backend-dev
uses the stub validator, so no application is needed."""
import hashlib
import json
import os
import unittest

import helpers
import samples
from devloops import prompts, schema, state
from stub_loop import STUB, implemented

OVERRIDES = os.path.join(".devloops", "prompts")


class PromptOverridesTest(unittest.TestCase):
    def setUp(self):
        self.t = helpers.TempEnv().__enter__()
        self.addCleanup(self.t.__exit__, None, None, None)
        loops = os.path.join(self.t.root, "loops")
        self.t.write_file(os.path.join("backend-dev", "loop.json"), json.dumps({
            "name": "backend-dev", "required_inputs": ["requirements"], "required_tools": [],
            "validator": "stub", "requires_openapi_path": False}), base=loops)
        self.t.write_file(os.path.join("shared", "devloops", "validators", "stub.py"), STUB,
                          base=loops)
        self.t.write_file("docs/prd.md", "# PRD\n\n- FR-1 list items\n- FR-2 create items\n",
                          base=self.t.root)
        self.t.make_project(self.t.root, {"targets": {"backend-dev": "backend"},
                                          "requirements": {"path": "docs/prd.md"}})
        self.t.write_scenario({"steps": {"plan": {"structured_output": samples.plan()},
                                         "implement": [implemented("M01-T01"),
                                                       implemented("M02-T01")]}})
        self.state_dir = os.path.join(self.t.root, ".devloops", "workspaces", "main",
                                      "backend-dev", "state")

    def cli(self, *args):
        code, out, err = helpers.run_cli(list(args), env=self.t.env, root=self.t.root)
        self.output = out + err
        return code, out

    def override(self, part, text):
        return self.t.write_file(os.path.join(OVERRIDES, part), text, base=self.t.root)

    def records(self):
        with open(os.path.join(self.state_dir, "invocations.jsonl"), encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def prompt(self, name):
        with open(os.path.join(self.state_dir, "prompts", name), encoding="utf-8") as f:
            return f.read()

    def events(self, type):
        with open(os.path.join(self.state_dir, "events.jsonl"), encoding="utf-8") as f:
            return [e for e in map(json.loads, f) if e["type"] == type]

    def status(self):
        code, out = self.cli("status", "backend-dev", "--json")
        self.assertEqual(code, 0, self.output)
        return json.loads(out)

    def by_part(self, sources):
        return {s["part"]: s for s in sources}

    # --- composing (FR-030, FR-031) ---

    def test_a_step_override_is_used_and_recorded(self):
        text = "PROJECT PLAN RULES: use the existing logger.\n"
        self.override("steps/plan.md", text)
        self.assertEqual(self.cli("run")[0], 10, self.output)
        self.assertIn("PROJECT PLAN RULES", self.prompt("0001-plan.md"))
        [record] = self.records()
        self.assertEqual(schema.validate(record, "invocation-record.schema.json"), [])
        sources = self.by_part(record["prompt_sources"])
        self.assertEqual(list(sources), ["common.md", "backend-dev/Loop-instructions.md",
                                         "steps/plan.md"])
        self.assertEqual(sources["steps/plan.md"], {
            "part": "steps/plan.md", "source": "override", "path": ".devloops/prompts/steps/plan.md",
            "sha256": hashlib.sha256(text.encode()).hexdigest()})
        self.assertEqual(sources["common.md"]["source"], "packaged")
        self.assertEqual(sources["common.md"]["path"], "shared/prompts/common.md")
        self.assertEqual(sources["backend-dev/Loop-instructions.md"]["source"], "packaged")

    def test_every_overridable_part_applies(self):
        self.override("common.md", "PROJECT COMMON\n")
        self.override("backend-dev/Loop-instructions.md", "PROJECT BACKEND\n")
        self.override("frontend-dev/Loop-instructions.md", "PROJECT FRONTEND\n")
        self.assertEqual(self.cli("run")[0], 10, self.output)
        prompt = self.prompt("0001-plan.md")
        self.assertIn("PROJECT COMMON", prompt)
        self.assertIn("PROJECT BACKEND", prompt)
        self.assertNotIn("PROJECT FRONTEND", prompt)
        sources = self.by_part(self.records()[0]["prompt_sources"])
        self.assertEqual(sources["common.md"]["source"], "override")
        self.assertEqual(sources["backend-dev/Loop-instructions.md"]["source"], "override")
        self.assertEqual(sources["steps/plan.md"]["source"], "packaged")
        self.assertEqual(self.status()["prompt_drift"], [])

    def test_without_overrides_the_packaged_prompts_are_used(self):
        self.assertEqual(self.cli("run")[0], 10, self.output)
        sources = self.records()[0]["prompt_sources"]
        self.assertEqual({s["source"] for s in sources}, {"packaged"})
        with open(os.path.join(self.t.root, "loops", "shared", "prompts", "steps", "plan.md"),
                  "rb") as f:
            self.assertEqual(self.by_part(sources)["steps/plan.md"]["sha256"],
                             hashlib.sha256(f.read()).hexdigest())

    # --- other files ---

    def test_unknown_files_are_ignored_and_reported(self):
        self.override("steps/typo.md", "TYPO RULES\n")
        self.override("README.md", "the installed README\n")
        self.assertEqual(self.cli("run")[0], 10, self.output)
        self.assertNotIn("TYPO RULES", self.prompt("0001-plan.md"))
        [warning] = self.status()["warnings"]
        self.assertIn(".devloops/prompts/steps/typo.md", warning)
        self.assertNotIn(".devloops/prompts/README.md", warning)
        self.cli("status", "backend-dev")
        self.assertIn("devloops: warning: ignored in .devloops/prompts/", self.output)
        self.assertEqual(prompts.ignored(self.t.root), [".devloops/prompts/steps/typo.md"])

    # --- freezing and changes (FR-032) ---

    def test_the_sources_are_frozen_and_changes_reported(self):
        self.override("steps/plan.md", "FIRST\n")
        self.assertEqual(self.cli("run")[0], 10, self.output)
        rs = state.read_json(os.path.join(self.state_dir, "run.json"))
        frozen = self.by_part(rs["prompt_sources"])
        self.assertEqual(frozen["steps/plan.md"]["source"], "override")
        self.assertIn("steps/implement.md", frozen)
        self.assertEqual(schema.validate(rs, "run-state.schema.json"), [])

        self.override("steps/plan.md", "SECOND\n")
        self.override("steps/implement.md", "PROJECT IMPLEMENT\n")
        self.assertEqual(self.status()["prompt_drift"], ["steps/plan.md", "steps/implement.md"])
        self.cli("status", "backend-dev")
        self.assertIn("prompt parts changed since the first run", self.output)
        self.assertEqual(self.events("prompt-sources-changed"), [])  # status is read-only

        self.assertEqual(self.cli("run")[0], 10, self.output)
        [event] = self.events("prompt-sources-changed")
        self.assertIn("steps/plan.md", event["message"])
        self.assertIn("steps/implement.md", event["message"])
        rs = state.read_json(os.path.join(self.state_dir, "run.json"))
        self.assertEqual(self.by_part(rs["prompt_sources"]), frozen)  # still the frozen ones
        self.assertEqual(self.status()["prompt_drift"], ["steps/plan.md", "steps/implement.md"])

        # The calls of a later start use the current override.
        self.assertEqual(self.cli("approve", "--no-continue")[0], 0, self.output)
        self.assertEqual(self.cli("run")[0], 0, self.output)
        implement = [r for r in self.records() if r["step"] == "implement"]
        self.assertTrue(implement)
        self.assertEqual(self.by_part(implement[0]["prompt_sources"])["steps/implement.md"]
                         ["source"], "override")
        self.assertIn("PROJECT IMPLEMENT", self.prompt(os.path.basename(
            implement[0]["prompt_path"])))
        self.assertEqual(self.status()["prompt_drift"], [])  # the run ended

    def test_removing_an_override_is_drift(self):
        path = self.override("steps/plan.md", "FIRST\n")
        self.assertEqual(self.cli("run")[0], 10, self.output)
        os.remove(path)
        self.assertEqual(self.status()["prompt_drift"], ["steps/plan.md"])


if __name__ == "__main__":
    unittest.main()
