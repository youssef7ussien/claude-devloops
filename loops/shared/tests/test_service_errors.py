"""Service failures void the trial and stop resumably; work failures count (T049; FR-067, R-19).

Written before T052 (the service-error path), so this module fails until then.
"""
import unittest

import samples
from devloops import schema
from stub_loop import StubLoopMixin, implemented, service_error


class ServiceErrorTest(StubLoopMixin, unittest.TestCase):
    def stopped_during_implement(self, status):
        self.approved()
        self.scenario({"implement": [service_error(status), implemented("M01-T01"),
                                     implemented("M02-T01")]})
        self.assertEqual(self.cli("run"), 50, self.last_output)
        return self.run_state()

    def test_a_429_voids_the_trial_and_stops_as_a_service_error(self):
        rs = self.stopped_during_implement(429)
        self.assertEqual(rs["status"], "stopped-on-service-error")
        self.assertEqual(rs["status_reason"]["code"], "rate-limited")
        self.assertEqual(rs["resume_status"], "implementing")
        m1 = rs["milestones"]["M01"]
        self.assertEqual([(t["n"], t["status"]) for t in m1["trials"]], [(1, "void")])
        self.assertEqual(m1["trials"][0]["reason"], "rate-limited")
        trial = self.trial("M01", 1)
        self.assertEqual(trial["status"], "void")
        self.assertEqual(trial["failure"]["reason"], "rate-limited")
        self.assertTrue(self.events("service-error"))
        self.assertTrue(self.events("trial-voided"))
        self.assertEqual(schema.validate(rs, "run-state.schema.json"), [])

    def test_the_next_run_resumes_with_the_same_trial_number(self):
        self.stopped_during_implement(429)
        self.assertEqual(self.cli("run"), 0, self.last_output)
        rs = self.run_state()
        self.assertEqual(rs["status"], "completed")
        self.assertIsNone(rs["resume_status"])
        m1 = rs["milestones"]["M01"]
        # The void attempt is kept for the record, but its number is reused and it never counts.
        self.assertEqual([(t["n"], t["status"]) for t in m1["trials"]],
                         [(1, "void"), (1, "passed")])
        self.assertEqual(self.trial("M01", 1)["status"], "passed")
        # Both attempts were `implement` (trial 1), never a `fix` (trial 2).
        self.assertEqual(self.steps_called(), ["plan", "implement", "implement", "implement"])
        self.assertEqual([self.context_of(c)["trial"] for c in self.calls("implement")[:2]],
                         [1, 1])

    def test_401_is_auth_failed(self):
        rs = self.stopped_during_implement(401)
        self.assertEqual(rs["status_reason"]["code"], "auth-failed")
        self.assertEqual(rs["milestones"]["M01"]["trials"][0]["status"], "void")

    def test_a_service_error_while_planning_resumes_planning(self):
        self.scenario({"plan": [service_error(503), {"structured_output": samples.plan()}]})
        self.assertEqual(self.first_run(), 50, self.last_output)
        rs = self.run_state()
        self.assertEqual(rs["status_reason"]["code"], "service-unavailable")
        self.assertEqual(rs["resume_status"], "planning")
        self.assertEqual([t["status"] for t in rs["planning"]["trials"]], ["void"])

        self.assertEqual(self.cli("run"), 10, self.last_output)
        trials = self.run_state()["planning"]["trials"]
        self.assertEqual([(t["n"], t["status"]) for t in trials], [(1, "void"), (1, "passed")])

    def test_is_error_without_an_api_status_is_a_counted_work_failure(self):
        self.approved()
        self.scenario({"implement": {"is_error": True, "result": "something went wrong"}})
        self.assertEqual(self.cli("run", "--max-trials", "1"), 20,
                         self.last_output)
        rs = self.run_state()
        self.assertEqual(rs["status"], "stopped-on-failure")
        self.assertEqual(rs["status_reason"]["code"], "trials-exhausted")
        self.assertEqual([t["status"] for t in rs["milestones"]["M01"]["trials"]], ["failed"])
        self.assertEqual(self.trial("M01", 1)["failure"]["reason"], "claude-error")


if __name__ == "__main__":
    unittest.main()
