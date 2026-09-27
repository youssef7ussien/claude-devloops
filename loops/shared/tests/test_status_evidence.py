"""`status` lists evidence files over 1 MB as a review hint (T074; research R-21, FR-070)."""
import json
import os
import unittest

from stub_loop import StubLoopMixin, WS

MB = 1024 * 1024


class LargeEvidenceTest(StubLoopMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.approved()
        self.assertEqual(self.cli("run", "backend-dev"), 0, self.last_output)
        evidence = self.path(os.path.join("state", "milestones", "M01", "trials", "1",
                                          "evidence"))
        self.big = self.sized(os.path.join(evidence, "trace.har"), 2 * MB)
        self.sized(os.path.join(evidence, "at-the-limit.png"), MB)             # not over 1 MB
        self.sized(self.path(os.path.join("state", "not-evidence.log")), 3 * MB)  # not evidence

    def sized(self, path, size):
        with open(path, "wb") as f:
            f.write(b"x" * size)
        return path

    def status(self, *args):
        code, out, err = self.t.run_cli(["status", *args, "--workspace", WS])
        self.assertEqual(code, 0, out + err)
        return out

    def test_text_status_lists_only_large_evidence(self):
        out = self.status()
        self.assertIn("evidence files over 1 MB", out)
        self.assertIn(f"backend-dev/state/milestones/M01/trials/1/evidence/trace.har "
                      f"({2 * MB} bytes)", out)
        self.assertNotIn("at-the-limit.png", out)
        self.assertNotIn("not-evidence.log", out)

    def test_json_status_includes_the_list(self):
        for args in ((), ("backend-dev",)):
            obj = json.loads(self.status(*args, "--json"))
            self.assertEqual(obj["large_evidence"], [
                {"path": os.path.relpath(self.big, self.t.workspace_dir), "bytes": 2 * MB}])
        self.assertEqual(json.loads(self.status("frontend-dev", "--json"))["large_evidence"], [])

    def test_no_hint_without_large_evidence(self):
        os.remove(self.big)
        self.assertNotIn("evidence files over 1 MB", self.status())


if __name__ == "__main__":
    unittest.main()
