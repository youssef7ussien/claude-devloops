import unittest

import helpers  # noqa: F401
import samples
from devloops.plan import validate_plan

BACKEND = {"requires_openapi_path": True}


class PlanValidationTest(unittest.TestCase):
    def errors(self, plan, loop_def=BACKEND):
        return validate_plan(plan, loop_def, "prd", None)

    def test_valid_plan(self):
        self.assertEqual(self.errors(samples.plan()), [])

    def test_schema_errors_come_first(self):
        plan = samples.plan()
        plan["milestones"][0]["id"] = "Milestone-1"
        self.assertTrue(all(e.startswith("$") for e in self.errors(plan)))

    def test_id_patterns_from_schema(self):
        for mutate in (lambda p: p["milestones"][0]["tasks"][0].update(id="M01-1"),
                       lambda p: p["milestones"][0]["acceptance_criteria"][0].update(id="AC1"),
                       lambda p: p["open_questions"].append(
                           {"id": "Q1", "question": "?", "context": "", "affects": [],
                            "suggested_answer": "", "suggestion_reason": ""})):
            plan = samples.plan()
            mutate(plan)
            self.assertNotEqual(self.errors(plan), [])

    def test_duplicate_ids(self):
        plan = samples.plan()
        plan["milestones"][1]["id"] = "M01"
        plan["milestones"][1]["depends_on"] = []
        for t in plan["milestones"][1]["tasks"]:
            t["id"] = "M01-T01"
        plan["milestones"][1]["acceptance_criteria"][0]["id"] = "M01-AC1"
        errors = self.errors(plan)
        self.assertIn("duplicate milestone id 'M01'", errors)
        self.assertIn("duplicate task id 'M01-T01'", errors)
        self.assertIn("duplicate acceptance criterion id 'M01-AC1'", errors)

    def test_unknown_dependency(self):
        plan = samples.plan()
        plan["milestones"][1]["depends_on"] = ["M09"]
        self.assertEqual(self.errors(plan), ["milestone M02 depends on unknown milestone M09"])

    def test_dependency_order_and_cycles(self):
        plan = samples.plan()
        plan["milestones"].reverse()  # M02 (depends on M01) now comes first
        self.assertEqual(len(self.errors(plan)), 1)
        plan = samples.plan()
        plan["milestones"][0]["depends_on"] = ["M02"]  # cycle M01 <-> M02
        self.assertEqual(len(self.errors(plan)), 1)
        plan = samples.plan()
        plan["milestones"][0]["depends_on"] = ["M01"]  # self-dependency
        self.assertEqual(len(self.errors(plan)), 1)

    def test_every_milestone_needs_tasks_and_criteria(self):
        plan = samples.plan()
        plan["milestones"][0]["tasks"] = []
        plan["milestones"][1]["acceptance_criteria"] = []
        self.assertEqual(len(self.errors(plan)), 2)

    def test_refs_must_be_in_inventory(self):
        plan = samples.plan()
        plan["milestones"][0]["tasks"][0]["requirement_refs"] = ["FR-1", "FR-9"]
        plan["milestones"][1]["acceptance_criteria"][0]["requirement_refs"] = ["NFR-1"]
        self.assertEqual(self.errors(plan), [
            "task M01-T01 cites 'FR-9', which is not in requirements_inventory",
            "acceptance criterion M02-AC1 cites 'NFR-1', which is not in requirements_inventory",
        ])

    def test_items_must_sit_under_their_milestone(self):
        plan = samples.plan()
        plan["milestones"][1]["tasks"][0]["id"] = "M01-T02"
        self.assertEqual(self.errors(plan), ["task M01-T02 is listed under milestone M02"])

    def test_stack_conflicts_need_an_open_question(self):
        plan = samples.plan()
        plan["stack"]["conflicts"] = ["PRD says Go, the code is Python"]
        self.assertEqual(len(self.errors(plan)), 1)
        plan["open_questions"] = [{"id": "OQ1", "question": "Which stack?", "context": "conflict",
                                   "affects": ["M01"], "suggested_answer": "Keep Python.",
                                   "suggestion_reason": "the code already uses it"}]
        self.assertEqual(self.errors(plan), [])

    def test_openapi_path_required_only_when_the_loop_says_so(self):
        plan = samples.plan()
        del plan["runtime"]["openapi_path"]
        self.assertEqual(self.errors(plan), ["runtime.openapi_path is required for this loop"])
        self.assertEqual(self.errors(plan, loop_def={}), [])


if __name__ == "__main__":
    unittest.main()
