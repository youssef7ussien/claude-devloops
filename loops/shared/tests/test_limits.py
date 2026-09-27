"""Trial limits, the call time limit, the call cap, and the run lock (T047; FR-005, FR-062, FR-065).

Written before T051-T056 (the tests for a story come first); the time limit and cap wiring is
T054.
"""
import os
import signal
import unittest

from stub_loop import StubLoopMixin, implemented

FAIL = {"DEVLOOPS_STUB": "fail"}


class LimitsTest(StubLoopMixin, unittest.TestCase):
    def test_always_failing_validation_stops_after_exactly_the_default_limit(self):
        self.approved()
        self.assertEqual(self.cli("run", "backend-dev", env=FAIL), 20, self.last_output)
        rs = self.run_state()
        self.assertEqual(rs["status"], "stopped-on-failure")
        self.assertEqual(rs["status_reason"]["code"], "trials-exhausted")
        self.assertEqual(rs["status_reason"]["milestone_id"], "M01")
        m1 = rs["milestones"]["M01"]
        self.assertEqual([t["n"] for t in m1["trials"]], [1, 2, 3])  # default max_trials = 3
        self.assertEqual([t["status"] for t in m1["trials"]], ["failed"] * 3)
        self.assertEqual(m1["status"], "failed")
        self.assertEqual(m1["tasks"], {"M01-T01": "failed"})  # every unachieved task (SC-004)
        self.assertEqual(rs["milestones"]["M02"]["status"], "pending")  # never started
        self.assertEqual(self.steps_called(), ["plan", "implement", "fix", "fix"])

    def test_max_trials_override_sets_the_limit(self):
        self.approved()
        self.assertEqual(self.cli("run", "backend-dev", "--max-trials", "2", env=FAIL), 20,
                         self.last_output)
        m1 = self.run_state()["milestones"]["M01"]
        self.assertEqual([t["n"] for t in m1["trials"]], [1, 2])
        self.assertEqual(self.steps_called(), ["plan", "implement", "fix"])

    def test_a_call_past_the_time_limit_fails_its_trial_with_timeout(self):
        # 30 s is the schema minimum for invocation_timeout_seconds; the fake sleeps past it.
        config = self.config_file({"invocation_timeout_seconds": 30})
        self.approved("--config", config)
        self.scenario({"implement": dict(implemented("M01-T01"), sleep_seconds=120)})
        self.assertEqual(self.cli("run", "backend-dev", "--max-trials", "1"), 20, self.last_output)
        failure = self.trial("M01", 1)["failure"]
        self.assertEqual(failure["reason"], "timeout")  # counted (FR-062)
        self.assertIn("invocation_timeout_seconds=30", failure["detail"])
        self.assertEqual([t["status"] for t in self.run_state()["milestones"]["M01"]["trials"]],
                         ["failed"])

    def test_the_call_cap_stops_the_run(self):
        # plan + implement use both calls; the fix trial the failure asks for would be the third.
        config = self.config_file({"max_invocations_per_run": 2})
        self.approved("--config", config)
        self.assertEqual(self.cli("run", "backend-dev", env=FAIL), 20, self.last_output)
        rs = self.run_state()
        self.assertEqual(rs["status"], "stopped-on-failure")
        self.assertEqual(rs["status_reason"]["code"], "invocation-cap")
        self.assertIn("max_invocations_per_run=2", rs["status_reason"]["message"])
        self.assertEqual(rs["invocation_count"], 2)
        self.assertEqual(self.steps_called(), ["plan", "implement"])

    def test_a_second_concurrent_run_exits_40_naming_the_active_pid(self):
        self.approved()
        self.scenario({"implement": dict(implemented("M01-T01"), sleep_seconds=60)})
        first = self.start_cli("run", "backend-dev")
        call = self.wait_for_call("implement")
        self.addCleanup(self.kill_fake, call)

        self.assertEqual(self.cli("run", "backend-dev"), 40, self.last_output)
        self.assertIn(f"pid {first.pid}", self.last_output)
        self.assertEqual(len(self.calls("implement")), 1)  # the second driver made no call

        first.send_signal(signal.SIGINT)
        first.communicate(timeout=30)
        self.assertFalse(os.path.exists(os.path.join(self.loop_dir, "state", "lock")))


if __name__ == "__main__":
    unittest.main()
