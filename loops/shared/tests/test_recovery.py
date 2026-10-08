"""Interrupted trials, stopped runs, and `retry` grants (T048; FR-030a, FR-061, FR-063, SC-003).

Written before T051 (interrupted trials) and T056 (`retry`), so most of this module fails until
then. The refusal tests also check the message, so an unknown `retry` command (argparse's own
exit 2) cannot pass them by accident.
"""
import signal
import unittest

from devloops import schema
from stub_loop import StubLoopMixin, implemented

FAIL = {"DEVLOOPS_STUB": "fail"}


class InterruptedTrialTest(StubLoopMixin, unittest.TestCase):
    def interrupt_during_implement(self, sig, *resume_flags):
        """Interrupt the driver mid-call on M02, then run again; return the new run's M02 state."""
        self.approved()
        self.scenario({"implement": [implemented("M01-T01"),
                                     dict(implemented("M02-T01"), sleep_seconds=60)],
                       "fix": implemented("M02-T01")})
        driver = self.start_cli("run")
        call = self.wait_for_call("implement", count=2)  # M01 is achieved; M02 is mid-call
        self.addCleanup(self.kill_fake, call)
        driver.send_signal(sig)
        driver.communicate(timeout=30)
        self.kill_fake(call)
        self.assertEqual(self.trial("M02", 1)["status"], "in-progress")  # nothing closed it

        self.assertEqual(self.cli("run", *resume_flags), 0, self.last_output)
        return self.run_state()

    def assert_recovered(self, rs):
        m2 = rs["milestones"]["M02"]
        self.assertEqual([(t["n"], t["status"]) for t in m2["trials"]],
                         [(1, "failed"), (2, "passed")])
        interrupted = self.trial("M02", 1)
        self.assertEqual(interrupted["status"], "failed")
        self.assertEqual(interrupted["failure"]["reason"], "interrupted")
        self.assertIsNotNone(interrupted["ended_at"])
        self.assertEqual(m2["trials"][0]["reason"], "interrupted")
        # M01 was achieved before the interruption and is not run again.
        self.assertEqual(rs["milestones"]["M01"]["status"], "achieved")
        self.assertEqual(self.steps_called(), ["plan", "implement", "implement", "fix"])
        started = [e for e in self.events("trial-started") if e.get("milestone") == "M02"]
        self.assertEqual([e.get("trial") for e in started], [1, 2])
        # The new trial is a fix of the interrupted one, for the milestone's open tasks only.
        context = self.context_of(self.calls("fix")[0])
        self.assertEqual((context["milestone"]["id"], context["trial"]), ("M02", 2))
        self.assertEqual([t["id"] for t in context["milestone"]["tasks"]], ["M02-T01"])
        self.assertEqual(context["previous_failure"]["reason"], "interrupted")

    def test_sigint_mid_trial_fails_it_as_interrupted_and_the_next_trial_starts(self):
        self.assert_recovered(self.interrupt_during_implement(signal.SIGINT))

    def test_a_killed_driver_is_recovered_after_clearing_its_stale_lock(self):
        # SIGKILL leaves the lock behind; --force-unlock clears it (FR-065), then recovery runs.
        self.assert_recovered(self.interrupt_during_implement(signal.SIGKILL, "--force-unlock"))


class StoppedRunTest(StubLoopMixin, unittest.TestCase):
    def exhausted(self):
        self.approved()
        self.assertEqual(self.cli("run", env=FAIL), 20, self.last_output)

    def test_run_on_a_stopped_run_without_a_grant_changes_nothing(self):
        self.exhausted()
        before, calls = self.snapshot_state(), len(self.t.fake_calls())
        self.assertEqual(self.cli("run"), 20, self.last_output)
        self.assertEqual(len(self.t.fake_calls()), calls)
        self.assertEqual(self.snapshot_state(), before)

    def test_retry_records_a_grant_and_the_reason_reaches_the_fix_prompt(self):
        self.exhausted()
        reason = "the fixture needs port 8765 free; it is now"
        self.assertEqual(self.cli("retry", "--no-continue", "--milestone", "M01", "--reason", reason),
                         0, self.last_output)
        rs = self.run_state()
        self.assertEqual(rs["status"], "implementing")
        self.assertIsNone(rs["status_reason"])
        grant = rs["grants"][-1]
        self.assertEqual(grant["milestone_id"], "M01")
        self.assertEqual(grant["reason"], reason)
        self.assertEqual(grant["extra_trials"], 3)  # default: max_trials
        self.assertEqual(grant["answers_sha256"], self.answers_sha256())
        self.assertEqual(schema.validate(rs, "run-state.schema.json"), [])
        self.assertTrue(grant["granted_at"])
        self.assertEqual(rs["milestones"]["M01"]["status"], "in-progress")
        self.assertEqual(rs["milestones"]["M01"]["tasks"], {"M01-T01": "pending"})
        self.assertEqual(len([e for e in self.events("retry-granted")
                              if reason in e["message"]]), 1)

        self.assertEqual(self.cli("run"), 0, self.last_output)
        fix = self.calls("fix")[-1]
        context = self.context_of(fix)
        self.assertEqual(context["trial"], 4)  # counting continues after the 3 failed trials
        self.assertEqual(context["developer_guidance"], [reason])
        self.assertEqual(self.run_state()["status"], "completed")

    def test_retry_trials_option_sets_the_extra_trials(self):
        self.exhausted()
        self.assertEqual(self.cli("retry", "--no-continue", "--milestone", "M01", "--reason", "x",
                                  "--trials", "1"), 0, self.last_output)
        self.assertEqual(self.run_state()["grants"][-1]["extra_trials"], 1)
        self.assertEqual(self.cli("run", env=FAIL), 20, self.last_output)
        self.assertEqual(len(self.run_state()["milestones"]["M01"]["trials"]), 4)  # 3 + 1

    def assert_refused(self, *expected_in_message):
        before = self.snapshot_state()
        self.assertEqual(self.cli("retry", "--no-continue", "--milestone", "M01", "--reason", "x"),
                         2, self.last_output)
        self.assertNotIn("invalid choice", self.last_output)  # refused by retry, not argparse
        for text in expected_in_message:
            self.assertIn(text, self.last_output)
        self.assertEqual(self.snapshot_state(), before)

    def test_retry_is_refused_in_any_other_status(self):
        self.assertEqual(self.first_run(), 10, self.last_output)
        # The command finds no loop stopped on failure (003 FR-009).
        self.assert_refused("no loop is stopped on failure", "(run: paused)")
        self.assertEqual(self.cli("approve", "--no-continue"), 0, self.last_output)
        self.assert_refused("no loop is stopped on failure")
        self.assertEqual(self.cli("run"), 0, self.last_output)
        self.assert_refused("no loop is stopped on failure", "(run: completed)")

    def test_retry_of_a_milestone_that_did_not_fail_is_refused(self):
        self.exhausted()
        before = self.snapshot_state()
        self.assertEqual(self.cli("retry", "--no-continue", "--milestone", "M02", "--reason", "x"),
                         2, self.last_output)
        self.assertIn("M02", self.last_output)
        self.assertEqual(self.snapshot_state(), before)

    def test_retry_after_planning_trials_exhausted_is_refused_as_final(self):
        self.scenario({"plan": {"structured_output": {"milestones": []}}})
        self.assertEqual(self.first_run("--max-trials", "1"), 20, self.last_output)
        self.assertEqual(self.run_state()["status_reason"]["code"], "planning-trials-exhausted")
        self.assert_refused("new workspace")


if __name__ == "__main__":
    unittest.main()
