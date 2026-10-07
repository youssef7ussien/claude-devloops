"""A spec-kit feature as the requirements (002 US5: FR-023 to FR-026; research P-16)."""
import json
import os
import shutil
import unittest

import helpers
from devloops import plan as plan_mod
from devloops import inputs, speckit, state
from stub_loop import StubLoopMixin, implemented

FIXTURE = os.path.join(helpers.FIXTURES_DIR, "speckit")
FEATURE = os.path.join("specs", "001-sample")


def task(tid, title, refs, speckit_tasks=None):
    out = {"id": tid, "title": title, "description": title, "requirement_refs": refs}
    if speckit_tasks is not None:
        out["speckit_tasks"] = speckit_tasks
    return out


def milestone(mid, phase, tasks, refs, depends_on=()):
    return {"id": mid, "title": f"Milestone {mid}", "goal": "goal", "depends_on": list(depends_on),
            "speckit_phase": phase, "tasks": tasks,
            "acceptance_criteria": [{"id": f"{mid}-AC1", "text": "observable", "requirement_refs":
                                     refs}]}


def speckit_plan(story=None):
    """A plan of the fixture feature: the whole feature, or only `story` (US2)."""
    if story:
        refs = [story]
        milestones = [
            milestone("M01", 2, [task("M01-T01", "Note store", refs, ["T002"])], refs),
            milestone("M02", 4, [task("M02-T01", "POST /notes", refs, ["T005", "T006"])], refs,
                      ["M01"]),
        ]
        inventory = [{"ref": story, "summary": "Add a note"}]
    else:
        refs = ["US1", "US2"]
        milestones = [
            milestone("M01", 1, [task("M01-T01", "Skeleton and store", refs, ["T001", "T002"])],
                      refs),
            milestone("M02", 3, [task("M02-T01", "GET /notes", ["US1"], ["T003", "T004"])],
                      ["US1"], ["M01"]),
            milestone("M03", 4, [task("M03-T01", "POST /notes", ["US2"], ["T005", "T006"]),
                                 task("M03-T02", "Health endpoint", ["US2"])], ["US2"], ["M02"]),
        ]
        inventory = [{"ref": "US1", "summary": "List notes"},
                     {"ref": "US2", "summary": "Add a note"}]
    return {
        "requirements_inventory": inventory,
        "stack": {"summary": "Python stdlib", "source": "requirements", "conflicts": []},
        "runtime": {"start_command": "python3 app.py", "cwd": ".",
                    "base_url": "http://127.0.0.1:8765", "ready_url": "http://127.0.0.1:8765/"},
        "milestones": milestones,
        "speckit_omitted": [{"id": "T007", "reason": "frontend task"}],
        "open_questions": [], "assumptions": [],
    }


def phases():
    with open(os.path.join(FIXTURE, FEATURE, "tasks.md"), encoding="utf-8") as f:
        return speckit.parse_tasks(f.read())


class ParserTest(unittest.TestCase):
    def test_phases_and_tasks(self):
        found = phases()
        self.assertEqual([(p["n"], [t["id"] for t in p["tasks"]]) for p in found],
                         [(1, ["T001"]), (2, ["T002"]), (3, ["T003", "T004"]),
                          (4, ["T005", "T006", "T007"])])
        tasks = speckit.tasks_by_id(found)
        self.assertEqual(tasks["T001"]["story"], None)
        self.assertEqual(tasks["T004"]["story"], "US1")
        self.assertTrue(tasks["T004"]["parallel"])
        self.assertFalse(tasks["T003"]["parallel"])
        self.assertTrue(tasks["T006"]["done"])
        self.assertFalse(tasks["T005"]["done"])
        self.assertEqual(tasks["T004"]["text"], "Add a test for listing notes in api/test_app.py")
        self.assertEqual(found[2]["title"], "User Story 1 - List notes (Priority: P1)")

    def test_decimal_phases(self):
        found = speckit.parse_tasks("## Phase 3.1: Setup\n- [ ] T001 a\n"
                                    "## Phase 3.2: Tests\n- [ ] T002 b\n"
                                    "## Phase 3.10: Polish\n- [ ] T003 c\n")
        self.assertEqual([p["n"] for p in found], ["3.1", "3.2", "3.10"])
        plan = speckit_plan()
        plan["milestones"][0]["tasks"][0]["speckit_tasks"] = ["T001"]
        plan["milestones"][1]["tasks"][0]["speckit_tasks"] = ["T002"]
        plan["milestones"][2]["tasks"][0]["speckit_tasks"] = ["T003"]
        plan["speckit_omitted"] = []
        for m, phase in zip(plan["milestones"], ("3.1", "3.2", "3.10")):
            m["speckit_phase"] = phase
        self.assertEqual(plan_mod.validate_plan(plan, {}), [])
        self.assertEqual(plan_mod.validate_speckit(plan, found), [])
        plan["milestones"][1]["speckit_phase"] = "3.10"
        plan["milestones"][2]["speckit_phase"] = "3.2"
        self.assertTrue(any("phases' order" in e
                            for e in plan_mod.validate_speckit(plan, found)))

    def test_stories(self):
        with open(os.path.join(FIXTURE, FEATURE, "spec.md"), encoding="utf-8") as f:
            found = speckit.stories(f.read())
        self.assertEqual(list(found), ["US1", "US2"])
        self.assertEqual(found["US2"], "User Story 2 - Add a note (Priority: P2)")


class CoverageTest(unittest.TestCase):
    """`plan.validate_speckit` (FR-023a, FR-023d)."""

    def check(self, plan, story=None):
        self.assertEqual(plan_mod.validate_plan(plan, {}, "prd-story" if story else "prd", story),
                         [])
        return plan_mod.validate_speckit(plan, phases(), story)

    def test_a_complete_plan_is_valid(self):
        self.assertEqual(self.check(speckit_plan()), [])

    def test_an_in_scope_task_left_out_silently_is_invalid(self):
        plan = speckit_plan()
        plan["speckit_omitted"] = []
        errors = self.check(plan)
        self.assertEqual(len(errors), 1)
        self.assertIn("T007", errors[0])

    def test_an_unknown_task_is_invalid(self):
        plan = speckit_plan()
        plan["milestones"][0]["tasks"][0]["speckit_tasks"].append("T099")
        self.assertTrue(any("T099" in e for e in self.check(plan)))
        plan = speckit_plan()
        plan["speckit_omitted"].append({"id": "T098", "reason": "x"})
        self.assertTrue(any("T098" in e for e in self.check(plan)))

    def test_milestones_out_of_phase_order_are_invalid(self):
        plan = speckit_plan()
        plan["milestones"][1]["speckit_phase"] = 4
        plan["milestones"][2]["speckit_phase"] = 3
        self.assertTrue(any("phases' order" in e for e in self.check(plan)))
        plan["milestones"][2]["speckit_phase"] = 9
        self.assertTrue(any("not a phase" in e for e in self.check(plan)))

    def test_story_mode_scope(self):
        self.assertEqual(self.check(speckit_plan("US2"), "US2"), [])
        # Without the needed foundational task, T002 is simply not in scope.
        plan = speckit_plan("US2")
        plan["milestones"][0]["tasks"][0]["speckit_tasks"] = []
        self.assertEqual(self.check(plan, "US2"), [])
        # US2's own tasks must be accounted for; another story's tasks may not be referenced.
        plan = speckit_plan("US2")
        plan["speckit_omitted"] = []
        self.assertTrue(any("T007" in e for e in self.check(plan, "US2")))
        plan = speckit_plan("US2")
        plan["milestones"][1]["tasks"][0]["speckit_tasks"].append("T003")
        self.assertTrue(any("T003 belongs to US1" in e for e in self.check(plan, "US2")))


class SpeckitRunTest(StubLoopMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        shutil.copytree(FIXTURE, self.t.root, dirs_exist_ok=True)
        self.feature_dir = os.path.join(self.t.root, FEATURE)
        self.plan_scenario()

    def plan_scenario(self, *plans):
        plans = plans or (speckit_plan(),)
        self.scenario({"plan": [{"structured_output": p} for p in plans],
                       "implement": implemented("M01-T01")})

    def speckit_run(self, *extra):
        return self.cli("run", "backend-dev", "--speckit-feature", *extra, "--target",
                        self.t.target_dir)

    def workspace_json(self):
        return state.read_json(os.path.join(self.t.workspace_dir, "workspace.json"))

    def test_the_active_feature_is_resolved_and_recorded(self):
        self.assertEqual(self.speckit_run(), 10, self.last_output)
        req = self.workspace_json()["requirements"]
        self.assertEqual(req["path"], os.path.join(FEATURE, "spec.md"))
        self.assertEqual(req["mode"], "prd")
        block = req["speckit"]
        self.assertEqual(block["feature_dir"], FEATURE)
        for key, name in (("plan_md", "plan.md"), ("tasks_md", "tasks.md")):
            self.assertEqual(block[key]["path"], os.path.join(FEATURE, name))
            self.assertEqual(block[key]["sha256"], helpers_sha(os.path.join(self.feature_dir,
                                                                            name)))
        self.cli("status", "backend-dev")
        self.assertIn(f"spec-kit feature: {self.feature_dir}", self.last_output)

    def test_the_planning_context_carries_the_phases(self):
        self.assertEqual(self.speckit_run(), 10, self.last_output)
        [call] = self.calls("plan")
        ctx = self.context_of(call)["speckit"]
        self.assertEqual([p["n"] for p in ctx["phases"]], [1, 2, 3, 4])
        self.assertEqual(ctx["plan_md"], os.path.join(self.feature_dir, "plan.md"))
        self.assertIn("rule", ctx)
        self.assertIn("## Spec-kit feature", call["prompt"])

    def test_a_plan_that_skips_a_task_uses_up_a_planning_trial(self):
        bad = speckit_plan()
        bad["speckit_omitted"] = []
        self.plan_scenario(bad, speckit_plan())
        self.assertEqual(self.speckit_run(), 10, self.last_output)
        trials = self.run_state()["planning"]["trials"]
        self.assertEqual([t["status"] for t in trials], ["failed", "passed"])
        self.assertIn("T007", trials[0]["failure"]["detail"])

    def test_the_plan_summary_shows_the_differences(self):
        self.assertEqual(self.speckit_run(), 10, self.last_output)
        summary = self.read(os.path.join("outputs", "plan-summary.md"))
        planned = summary.split("### Planned")[1].split("###")[0]
        for tid in ("T001", "T002", "T003", "T004", "T005", "T006"):
            self.assertIn(f"**{tid}**", planned)
        self.assertIn("**T007** [US2] Add the note form in web/index.html: frontend task",
                      summary)
        no_task = summary.split("### Devloops tasks with no spec-kit task")[1].split("###")[0]
        self.assertIn("**M03-T02** Health endpoint", no_task)
        self.assertIn("**T006** [US2] Refuse an empty text in api/app.py (already marked done "
                      "in tasks.md)", summary)

    def test_story_mode_lists_the_setup_it_needs(self):
        self.plan_scenario(speckit_plan("US2"))
        self.assertEqual(self.speckit_run("--story-id", "US2"), 10, self.last_output)
        self.assertEqual(self.workspace_json()["requirements"]["story_id"], "US2")
        summary = self.read(os.path.join("outputs", "plan-summary.md"))
        needed = summary.split("### Setup and foundational tasks needed by US2")[1].split("###")[0]
        self.assertIn("**T002**", needed)
        self.assertIn("Out of scope (other stories): T003, T004", summary)

    def test_missing_inputs(self):
        os.makedirs(os.path.join(self.t.root, "specs", "002-empty"))
        self.assertEqual(self.cli("run", "backend-dev", "--speckit-feature",
                                  os.path.join(self.t.root, "specs", "002-empty"), "--target",
                                  self.t.target_dir), 30, self.last_output)
        self.assertIn("002-empty has no spec.md", self.last_output)

    def test_an_unknown_story_is_refused(self):
        self.assertEqual(self.speckit_run("--story-id", "US9"), 30, self.last_output)
        self.assertIn("story 'US9' has no matching heading", self.last_output)

    def test_a_tasks_edit_after_planning_stops_the_run(self):
        self.assertEqual(self.speckit_run(), 10, self.last_output)
        with open(os.path.join(self.feature_dir, "tasks.md"), "a") as f:
            f.write("- [ ] T008 [US2] Something new\n")
        self.assertEqual(self.cli("run", "backend-dev"), 30, self.last_output)
        reason = self.run_state()["status_reason"]
        self.assertEqual((reason["code"], reason["input"]), ("input-changed", "tasks"))

    def test_a_tasks_file_that_appears_after_planning_stops_the_run(self):
        tasks = os.path.join(self.feature_dir, "tasks.md")
        os.rename(tasks, tasks + ".later")
        self.plan_scenario(speckit_plan() | {"speckit_omitted": []})
        self.assertEqual(self.speckit_run(), 10, self.last_output)
        self.assertIsNone(self.workspace_json()["requirements"]["speckit"]["tasks_md"])
        os.rename(tasks + ".later", tasks)
        self.assertEqual(self.cli("run", "backend-dev"), 30, self.last_output)
        reason = self.run_state()["status_reason"]
        self.assertEqual((reason["code"], reason["input"]), ("input-changed", "tasks"))
        self.assertIn("absent", reason["message"])

    def test_another_active_feature_on_resume_is_a_mismatch(self):
        self.assertEqual(self.speckit_run(), 10, self.last_output)
        other = os.path.join(self.t.root, "specs", "002-other")
        shutil.copytree(self.feature_dir, other)
        with open(os.path.join(self.t.root, ".specify", "feature.json"), "w") as f:
            json.dump({"feature_directory": "specs/002-other"}, f)
        # A usage error: the run stays resumable without the flag.
        self.assertEqual(self.cli("run", "backend-dev", "--speckit-feature"), 2,
                         self.last_output)
        self.assertIn("omit --speckit-feature", self.last_output)
        self.assertEqual(self.run_state()["status"], "awaiting-approval")
        self.assertEqual(self.cli("run", "backend-dev", "--speckit-feature", "specs/typo"), 2,
                         self.last_output)
        self.assertEqual(self.run_state()["status"], "awaiting-approval")
        self.assertEqual(self.cli("run", "backend-dev"), 10, self.last_output)

    def test_orchestrate_passes_the_feature_to_the_loops(self):
        code = self.cli("orchestrate", "--speckit-feature", "--backend-target",
                        self.t.target_dir, "--frontend-target", self.t.frontend_target_dir)
        self.assertEqual(code, 10, self.last_output)  # the backend planned and awaits approval
        self.assertEqual(self.run_state()["inputs"]["requirements"]["speckit"]["feature_dir"],
                         self.feature_dir)
        self.assertIn("speckit", self.context_of(self.calls("plan")[0]))

    def test_spec_kit_cannot_be_combined_with_a_requirements_file(self):
        self.assertEqual(self.speckit_run("--story-file"), 2, self.last_output)
        code = self.cli("run", "backend-dev", "--speckit-feature", "--requirements", self.prd)
        self.assertEqual(code, 2, self.last_output)

    def test_the_project_configuration_can_name_the_feature(self):
        self.t.make_project(self.t.root, {"workspaces_dir": "workspaces",
                                          "requirements": {"speckit_feature": "active"}})
        self.assertEqual(self.cli("run", "backend-dev", "--target", self.t.target_dir), 10,
                         self.last_output)
        self.assertEqual(self.workspace_json()["requirements"]["speckit"]["feature_dir"], FEATURE)
        # A later start without flags resumes the recorded feature, whatever is active then.
        with open(os.path.join(self.t.root, ".specify", "feature.json"), "w") as f:
            json.dump({"feature_directory": "specs/none"}, f)
        self.assertEqual(self.cli("approve", "--no-continue", "backend-dev"), 0, self.last_output)
        self.assertNotEqual(self.cli("run", "backend-dev"), 30, self.last_output)
        self.cli("status", "backend-dev", "--json")
        self.assertEqual(json.loads(self.last_output)["speckit_feature"], self.feature_dir)


def helpers_sha(path):
    return inputs.sha256_file(path)


if __name__ == "__main__":
    unittest.main()
