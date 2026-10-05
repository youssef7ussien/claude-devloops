"""`workspaces/<ws>/dashboard.html`: written after every command, from state only."""
import json
import os
import re
import unittest

import helpers  # noqa: F401
import samples
from devloops import dashboard, workspace
from stub_loop import StubLoopMixin, WS, implemented


class DashboardTest(StubLoopMixin, unittest.TestCase):
    def page(self):
        with open(os.path.join(self.t.workspace_dir, "dashboard.html"), encoding="utf-8") as f:
            return f.read()

    def data(self):
        return dashboard.collect(workspace.open_workspace(WS, self.t.project(), self.t.kit(),
                                                         create=False))

    def test_written_at_the_approval_pause(self):
        self.assertEqual(self.first_run(), 10, self.last_output)
        self.assertIn("dashboard: ", self.last_output)
        page = self.page()
        self.assertIn("Awaiting approval", page)
        self.assertIn("devloops approve backend-dev", page)  # the next action
        for text in ("M01", "List items", "M02", "Create items", "Items are kept in memory"):
            self.assertIn(text, page)

    def test_a_completed_run_shows_results_evidence_and_statistics(self):
        self.approved()
        self.assertEqual(self.cli("run", "backend-dev"), 0, self.last_output)
        page = self.page()
        self.assertIn("Completed", page)
        self.assertIn("2 / 2", page)                              # milestones achieved
        self.assertIn("M01-AC1", page)
        self.assertIn("M02-AC1", page)
        # Evidence links are relative to the workspace, so they open from disk.
        self.assertIn('href="backend-dev/state/milestones/M01/trials/1/evidence/stub.txt"', page)
        self.assertIn("Trial timeline", page)
        self.assertIn("Cost by milestone", page)

        stats = self.data()["loops"]["backend-dev"]["stats"]
        self.assertEqual((stats["milestones"], stats["achieved"], stats["trials"],
                          stats["first_try"], stats["calls"]), (2, 2, 2, 2, 3))

    def test_failed_trials_and_retries_are_counted(self):
        self.approved()
        self.assertEqual(self.cli("run", "backend-dev", env={"DEVLOOPS_STUB": "fail"}), 20,
                         self.last_output)
        page = self.page()
        self.assertIn("Stopped on failure", page)
        self.assertIn("devloops retry backend-dev --milestone M01", page)
        self.assertEqual(self.cli("retry", "backend-dev", "--milestone", "M01", "--reason",
                                  "try again"), 0, self.last_output)
        self.assertEqual(self.cli("run", "backend-dev"), 0, self.last_output)
        page = self.page()
        self.assertIn("try again", page)                          # the retry's reason
        loop = self.data()["loops"]["backend-dev"]
        m01 = loop["milestones"][0]
        self.assertEqual([t["status"] for t in m01["trials"]], ["failed"] * 3 + ["passed"])
        self.assertEqual(loop["stats"]["first_try"], 1)            # only M02 passed on trial 1

    def test_the_page_is_self_contained_and_escapes_model_text(self):
        plan = samples.plan()
        plan["milestones"][0]["title"] = "<script>alert('x')</script>"
        self.scenario({"plan": {"structured_output": plan},
                       "implement": [implemented("M01-T01"), implemented("M02-T01")]})
        self.assertEqual(self.first_run(), 10, self.last_output)
        page = self.page()
        self.assertNotIn("<script>alert", page)
        self.assertIn("&lt;script&gt;alert", page)
        # Nothing is loaded from the network: one inline script, no external sources.
        self.assertEqual(len(re.findall(r"<script", page)), 1)
        self.assertNotRegex(page, r'(src|href)="(https?:)?//')
        self.assertNotIn("<link", page)

    def test_the_dashboard_command(self):
        self.assertEqual(self.first_run(), 10, self.last_output)
        os.remove(os.path.join(self.t.workspace_dir, "dashboard.html"))
        self.assertEqual(self.cli("dashboard", "--json"), 0, self.last_output)
        self.assertEqual(json.loads(self.last_output)["dashboard"],
                         os.path.join(self.t.workspace_dir, "dashboard.html"))
        self.assertIn("Awaiting approval", self.page())
        code, out, err = self.t.run_cli(["dashboard", "--workspace", "no-such-ws"])
        self.assertEqual(code, 2, out + err)

    def test_a_dashboard_failure_never_changes_the_run_outcome(self):
        # A directory where the page should go makes the write fail.
        os.makedirs(os.path.join(self.t.workspace_dir, "dashboard.html"))
        self.assertEqual(self.first_run(), 10, self.last_output)
        self.assertIn("could not write the dashboard", self.last_output)
        self.assertEqual(self.run_state()["status"], "awaiting-approval")


if __name__ == "__main__":
    unittest.main()
