"""The driver's pass rule (data-model.md, "ValidationResult")."""
import os
import tempfile
import unittest

import helpers  # noqa: F401
import samples
from devloops.engine import compute_pass


class PassRuleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.trial_dir = os.path.join(self.tmp.name, "trials", "1")
        os.makedirs(os.path.join(self.trial_dir, "evidence"))
        with open(os.path.join(self.trial_dir, "evidence", "shot.png"), "w") as f:
            f.write("png")
        self.outside = os.path.join(self.tmp.name, "outside.txt")
        with open(self.outside, "w") as f:
            f.write("not evidence")
        self.milestone = samples.plan()["milestones"][0]  # one criterion: M01-AC1

    def tearDown(self):
        self.tmp.cleanup()

    def result(self, evidence=("evidence/shot.png",), kind="curl", observed="200 []", **extra):
        vr = samples.validation_result()
        vr.update(kind=kind, **extra)
        vr["criteria"] = [{"criterion_id": "M01-AC1", "passed": True, "observed": observed,
                           "evidence": list(evidence)}]
        return vr

    def check(self, vr):
        return compute_pass(self.milestone, vr, self.trial_dir)

    def test_everything_passes(self):
        self.assertEqual(self.check(self.result()), (True, []))

    def test_missing_criterion_fails(self):
        vr = self.result()
        vr["criteria"] = []
        self.assertEqual(self.check(vr), (False, ["M01-AC1: no result"]))

    def test_missing_evidence_file_fails(self):
        passed, problems = self.check(self.result(evidence=["evidence/none.png"]))
        self.assertFalse(passed)
        self.assertIn("does not exist", problems[0])

    def test_absolute_evidence_path_outside_the_trial_fails(self):
        passed, problems = self.check(self.result(evidence=[self.outside]))
        self.assertFalse(passed)
        self.assertIn("outside the trial directory", problems[0])

    def test_dotdot_evidence_path_fails(self):
        passed, problems = self.check(self.result(evidence=["../../outside.txt"]))
        self.assertFalse(passed)
        self.assertIn("outside the trial directory", problems[0])

    def test_symlink_out_of_the_trial_fails(self):
        os.symlink(self.outside, os.path.join(self.trial_dir, "evidence", "link.txt"))
        passed, problems = self.check(self.result(evidence=["evidence/link.txt"]))
        self.assertFalse(passed)
        self.assertIn("outside the trial directory", problems[0])

    def test_absolute_path_inside_the_trial_is_fine(self):
        path = os.path.join(self.trial_dir, "evidence", "shot.png")
        self.assertEqual(self.check(self.result(evidence=[path])), (True, []))

    def test_playwright_needs_observation_and_evidence(self):
        self.assertFalse(self.check(self.result(kind="playwright", observed=" "))[0])
        self.assertFalse(self.check(self.result(kind="playwright", evidence=[]))[0])
        self.assertTrue(self.check(self.result(kind="curl", evidence=[]))[0])

    def test_contract_boundary_and_unit_tests(self):
        self.assertFalse(self.check(self.result(
            contract={"passed": False, "unmatched_operations": ["GET /x"]}))[0])
        self.assertFalse(self.check(self.result(
            boundary={"passed": False, "violations": ["/repo/loops/x"]}))[0])
        self.assertFalse(self.check(self.result(unit_tests={"enabled": True, "exit_code": 1}))[0])
        self.assertFalse(self.check(self.result(unit_tests={"enabled": True}))[0])
        self.assertTrue(self.check(self.result(unit_tests={"enabled": True, "exit_code": 0}))[0])


if __name__ == "__main__":
    unittest.main()
