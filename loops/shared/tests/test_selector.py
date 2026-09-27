import unittest

import helpers  # noqa: F401
import samples
from devloops import selector


def run_state(max_trials=3, cap=60, count=0):
    plan = samples.plan()
    return {
        "effective_config": {"max_trials": max_trials, "max_invocations_per_run": cap},
        "invocation_count": count,
        "grants": [],
        "milestones": {m["id"]: {"status": "pending",
                                 "tasks": {t["id"]: "pending" for t in m["tasks"]},
                                 "trials": []} for m in plan["milestones"]},
    }, plan


def trials(*statuses):
    return [{"n": i + 1, "status": s} for i, s in enumerate(statuses)]


class SelectorTest(unittest.TestCase):
    def test_first_milestone_first_trial(self):
        rs, plan = run_state()
        self.assertEqual(selector.next_unit(rs, plan), ("trial", "M01", 1))

    def test_achieved_milestones_are_skipped(self):
        rs, plan = run_state()
        rs["milestones"]["M01"]["status"] = "achieved"
        self.assertEqual(selector.next_unit(rs, plan), ("trial", "M02", 1))

    def test_stored_order_is_used(self):
        rs, plan = run_state()
        plan["milestones"].reverse()
        self.assertEqual(selector.next_unit(rs, plan), ("trial", "M02", 1))

    def test_complete(self):
        rs, plan = run_state()
        for ms in rs["milestones"].values():
            ms["status"] = "achieved"
        self.assertEqual(selector.next_unit(rs, plan), "complete")

    def test_next_trial_number_skips_void_trials(self):
        rs, plan = run_state()
        rs["milestones"]["M01"]["trials"] = trials("failed", "void", "void")
        self.assertEqual(selector.next_unit(rs, plan), ("trial", "M01", 2))

    def test_in_progress_trials_count(self):
        rs, plan = run_state()
        rs["milestones"]["M01"]["trials"] = trials("failed", "in-progress")
        self.assertEqual(selector.next_unit(rs, plan), ("trial", "M01", 3))

    def test_failed_milestone_stops(self):
        rs, plan = run_state()
        rs["milestones"]["M01"]["status"] = "failed"
        self.assertEqual(selector.next_unit(rs, plan), ("stop", "trials-exhausted", "M01"))

    def test_budget_used_up_marks_failed_and_stops(self):
        rs, plan = run_state(max_trials=2)
        ms = rs["milestones"]["M01"]
        ms["trials"] = trials("failed", "failed")
        ms["tasks"]["M01-T01"] = "implemented"
        self.assertEqual(selector.next_unit(rs, plan), ("stop", "trials-exhausted", "M01"))
        self.assertEqual(ms["status"], "failed")
        self.assertEqual(ms["tasks"], {"M01-T01": "failed"})
        self.assertEqual(rs["milestones"]["M02"]["status"], "pending")

    def test_grants_extend_the_budget_for_their_milestone_only(self):
        rs, plan = run_state(max_trials=2)
        rs["milestones"]["M01"]["trials"] = trials("failed", "failed")
        rs["grants"] = [{"milestone_id": "M01", "extra_trials": 2},
                        {"milestone_id": "M02", "extra_trials": 5}]
        self.assertEqual(selector.next_unit(rs, plan), ("trial", "M01", 3))
        self.assertEqual(selector.trial_limit(rs, "M01"), 4)

    def test_invocation_cap(self):
        rs, plan = run_state(cap=5, count=5)
        self.assertEqual(selector.next_unit(rs, plan), ("stop", "invocation-cap", "M01"))

    def test_cap_does_not_block_completion(self):
        rs, plan = run_state(cap=5, count=5)
        for ms in rs["milestones"].values():
            ms["status"] = "achieved"
        self.assertEqual(selector.next_unit(rs, plan), "complete")


if __name__ == "__main__":
    unittest.main()
