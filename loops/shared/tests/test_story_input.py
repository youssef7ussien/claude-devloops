"""Single-story input: `--story-file` and `--story-id` (T058; FR-010, FR-010a, FR-010b, D-6).

Written before T059-T062 (the CLI options, the story modes in `inputs.py`, the story-scope plan
rules, and the story-scope context block), so most of this module fails until then.
"""
import os
import unittest

import helpers
import samples
from devloops import inputs, plan as plan_mod, state
from stub_loop import StubLoopMixin, implemented

STORIES = os.path.join(helpers.FIXTURES_DIR, "stories")
PRD = os.path.join(STORIES, "prd.md")
SINGLE_STORY = os.path.join(STORIES, "single-story.md")
BACKEND = {"name": "backend-dev", "requires_openapi_path": False}


def story_plan(story_id, stray_ref=None):
    """A valid plan for `story_id`; with `stray_ref`, task M02-T01 cites only that ref instead."""
    plan = samples.plan()
    plan["requirements_inventory"] = [{"ref": story_id, "summary": "The selected story"}]
    for m in plan["milestones"]:
        for item in m["tasks"] + m["acceptance_criteria"]:
            item["requirement_refs"] = [story_id]
    if stray_ref:
        plan["requirements_inventory"].append({"ref": stray_ref, "summary": "Another story"})
        plan["milestones"][1]["tasks"][0]["requirement_refs"] = [stray_ref]
    return plan


class StoryInputTest(StubLoopMixin, unittest.TestCase):
    def start(self, requirements, *story_args):
        return self.cli("run", "--requirements", requirements, "--backend-target",
                        self.t.target_dir, *story_args)

    def workspace_json(self):
        return state.read_json(os.path.join(self.t.workspace_dir, "workspace.json"))

    def recorded_mode(self):
        req = self.run_state()["inputs"]["requirements"]
        ws_req = self.workspace_json()["requirements"]
        self.assertEqual((ws_req["mode"], ws_req.get("story_id")),
                         (req["mode"], req.get("story_id")))
        return req["mode"], req.get("story_id")

    def test_prd_mode_is_the_default(self):
        self.assertEqual(self.first_run(), 10, self.last_output)
        self.assertEqual(self.recorded_mode(), ("prd", None))

    def test_story_file_mode(self):
        self.scenario({"plan": {"structured_output": story_plan("US-7")}})
        self.assertEqual(self.start(SINGLE_STORY, "--story-file"), 10, self.last_output)
        self.assertEqual(self.recorded_mode(), ("story-file", None))

    def test_prd_story_mode_records_the_story_id(self):
        self.scenario({"plan": {"structured_output": story_plan("US-2")}})
        self.assertEqual(self.start(PRD, "--story-id", "US-2"), 10, self.last_output)
        self.assertEqual(self.recorded_mode(), ("prd-story", "US-2"))

    def test_unknown_story_id_is_an_input_error_naming_it(self):
        self.assertEqual(self.start(PRD, "--story-id", "US-9"), 30, self.last_output)
        self.assertIn("US-9", self.last_output)
        stops = self.events("stopped")
        self.assertTrue(stops and "story-not-found" in stops[-1]["message"], stops)
        self.assertIn("US-9", stops[-1]["message"])
        self.assertEqual(self.steps_called(), [])  # stopped before any Claude call
        # The workspace is not bound to the bad selection, so a corrected run can reuse it.
        self.assertIsNone(self.workspace_json()["requirements"])

    def test_story_id_match_is_literal_and_case_sensitive(self):
        self.assertEqual(self.start(PRD, "--story-id", "us-2"), 30, self.last_output)
        self.assertIn("us-2", self.last_output)

    def test_story_id_must_match_a_whole_id(self):
        prd = self.t.write_file("ten.md", "# PRD\n\n### US-10: List\n\n### US-11: Create\n")
        self.assertEqual(self.start(prd, "--story-id", "US-1"), 30, self.last_output)
        self.assertIn("US-1", self.last_output)
        self.assertEqual(self.steps_called(), [])
        # Markdown and punctuation around the ID still count as an occurrence.
        for text in ("### **US-10**: List\n", "- (US-10) list\n", "US-10\n"):
            with self.subTest(text=text):
                self.assertTrue(inputs._occurs_as_id("US-10", text))
        self.assertFalse(inputs._occurs_as_id("US-1", "US-1a and XUS-1 and US-1_b"))

    def test_story_id_and_story_file_are_mutually_exclusive(self):
        self.assertEqual(self.start(PRD, "--story-id", "US-2", "--story-file"), 2,
                         self.last_output)
        self.assertEqual(self.steps_called(), [])
        self.assertFalse(os.path.exists(os.path.join(self.loop_dir, "state", "run.json")))

    def test_a_different_story_on_resume_is_a_usage_error_that_changes_nothing(self):
        self.scenario({"plan": {"structured_output": story_plan("US-2")}})
        self.assertEqual(self.start(PRD, "--story-id", "US-2"), 10, self.last_output)
        before = self.snapshot_state()
        for story_args in (["--story-id", "US-1"], ["--story-id", "US-22"], ["--story-file"]):
            self.assertEqual(self.start(PRD, *story_args), 2, self.last_output)
            self.assertIn("story_id=US-2", self.last_output)
            self.assertEqual(self.snapshot_state(), before, story_args)  # still resumable
        self.assertEqual(self.run_state()["status"], "awaiting-approval")
        self.assertEqual(self.steps_called(), ["plan"])

    def test_resuming_without_the_story_flags_keeps_the_recorded_story(self):
        self.scenario({"plan": {"structured_output": story_plan("US-2")}})
        self.assertEqual(self.start(PRD, "--story-id", "US-2"), 10, self.last_output)
        self.assertEqual(self.start(PRD), 10, self.last_output)  # --requirements alone
        self.assertEqual(self.start(PRD, "--story-id", "US-2"), 10, self.last_output)
        self.assertEqual(self.run_state()["status"], "awaiting-approval")
        self.assertEqual(self.recorded_mode(), ("prd-story", "US-2"))

    def test_changed_requirements_on_resume_are_still_an_input_change(self):
        with open(PRD, encoding="utf-8") as f:
            prd = self.t.write_file("story-prd.md", f.read())
        self.scenario({"plan": {"structured_output": story_plan("US-2")}})
        self.assertEqual(self.start(prd, "--story-id", "US-2"), 10, self.last_output)
        with open(prd, "a", encoding="utf-8") as f:
            f.write("\n- A late rule.\n")
        self.assertEqual(self.start(prd, "--story-id", "US-2"), 30, self.last_output)
        self.assertEqual(self.run_state()["status_reason"]["code"], "input-changed")

    def test_an_empty_story_id_is_a_usage_error(self):
        for story_id in ("", "  "):
            self.assertEqual(self.start(PRD, "--story-id", story_id), 2, self.last_output)
            self.assertIn("--story-id is empty", self.last_output)
        self.assertEqual(self.steps_called(), [])
        self.assertIsNone(self.workspace_json()["requirements"])

    def test_a_plan_outside_the_story_is_an_invalid_planning_trial(self):
        self.scenario({"plan": [{"structured_output": story_plan("US-2", stray_ref="US-1")},
                                {"structured_output": story_plan("US-2")}]})
        self.assertEqual(self.start(PRD, "--story-id", "US-2"), 10, self.last_output)
        trials = self.run_state()["planning"]["trials"]
        self.assertEqual([(t["n"], t["status"]) for t in trials], [(1, "failed"), (2, "passed")])
        self.assertEqual(trials[0]["failure"]["reason"], "invalid-output")
        self.assertIn("M02-T01", trials[0]["failure"]["detail"])
        self.assertIn("US-2", trials[0]["failure"]["detail"])
        # The second planning call is told why the first one was rejected.
        retry_context = self.context_of(self.calls("plan")[1])
        self.assertEqual(retry_context["previous_attempt"]["reason"], "invalid-output")

    def test_plan_and_implement_prompts_carry_the_story_scope(self):
        self.scenario({"plan": {"structured_output": story_plan("US-2")},
                       "implement": [implemented("M01-T01"), implemented("M02-T01")]})
        self.assertEqual(self.start(PRD, "--story-id", "US-2"), 10, self.last_output)
        prompt = self.calls("plan")[0]["prompt"]
        scope = self.context_of(self.calls("plan")[0])["story_scope"]
        self.assertEqual(scope["story_id"], "US-2")
        self.assertIn("Plan and implement only story `US-2`", scope["rule"])
        self.assertIn("Other PRD sections are context only", scope["rule"])
        self.assertIn("never implement the other story", scope["rule"])
        self.assertIn("## Single-story scope", prompt)  # the matching common.md section

        self.assertEqual(self.cli("approve", "--no-continue"), 0, self.last_output)
        self.assertEqual(self.cli("run"), 0, self.last_output)
        implement = self.context_of(self.calls("implement")[0])
        self.assertEqual(implement["story_scope"]["story_id"], "US-2")

    def test_prd_mode_has_no_story_scope(self):
        self.assertEqual(self.first_run(), 10, self.last_output)
        self.assertNotIn("story_scope", self.context_of(self.calls("plan")[0]))


class StoryScopeRuleTest(unittest.TestCase):
    """`plan.validate_plan` with the story modes (T061)."""

    def test_prd_story_mode_requires_the_story_id_in_every_ref_list(self):
        self.assertEqual(plan_mod.validate_plan(story_plan("US-2"), BACKEND, "prd-story", "US-2"),
                         [])
        errors = plan_mod.validate_plan(story_plan("US-2", stray_ref="US-1"), BACKEND,
                                        "prd-story", "US-2")
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("task M02-T01", errors[0])
        self.assertIn("US-2", errors[0])

    def test_acceptance_criteria_are_checked_too(self):
        plan = story_plan("US-2", stray_ref="US-1")
        plan["milestones"][1]["tasks"][0]["requirement_refs"] = ["US-2"]
        plan["milestones"][0]["acceptance_criteria"][0]["requirement_refs"] = ["US-1"]
        errors = plan_mod.validate_plan(plan, BACKEND, "prd-story", "US-2")
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("acceptance criterion M01-AC1", errors[0])

    def test_citing_the_story_and_a_shared_rule_is_allowed(self):
        plan = story_plan("US-2", stray_ref="RULES")
        plan["milestones"][1]["tasks"][0]["requirement_refs"] = ["US-2", "RULES"]
        self.assertEqual(plan_mod.validate_plan(plan, BACKEND, "prd-story", "US-2"), [])

    def test_prd_mode_has_no_story_rule(self):
        self.assertEqual(plan_mod.validate_plan(samples.plan(), BACKEND, "prd", None), [])


if __name__ == "__main__":
    unittest.main()
