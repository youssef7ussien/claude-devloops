"""`workspaces/<ws>/dashboard.html`: the summary page, written when a command pauses, stops, or
ends, from state only (002 FR-038)."""
import json
import os
import re
import unittest

import helpers  # noqa: F401
import samples
from devloops import dashboard, ui, workspace
from stub_loop import StubLoopMixin, WS, implemented, service_error


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
        self.assertIn("devloops approve", page)  # the next action
        [(tone, text)] = [i for i in dashboard.attention(self.data()) if "is <span" in i[1]]
        self.assertEqual(tone, "warning")
        self.assertIn('<a href="#backend-dev"><strong>backend-dev</strong></a>', text)
        for text in ("M01", "List items", "M02", "Create items", "Items are kept in memory"):
            self.assertIn(text, page)

    def test_a_completed_run_shows_results_evidence_and_statistics(self):
        self.approved()
        self.assertEqual(self.cli("run"), 0, self.last_output)
        page = self.page()
        self.assertIn("Completed", page)
        self.assertIn("2 / 2", page)                              # milestones achieved
        self.assertIn("M01-AC1", page)
        self.assertIn("M02-AC1", page)
        # Files are named, not linked: the live dashboard opens them, and the page says how.
        self.assertIn('<code title="backend-dev/state/milestones/M01/trials/1/evidence/stub.txt">'
                      'stub.txt</code>', page)
        self.assertNotRegex(page, r'href="backend-dev/')
        self.assertIn("Files and conversations: <code>devloops dashboard --daemon --workspace us3"
                      "</code>", page)
        for view in ("overview", "backend-dev", "calls", "questions", "events"):
            self.assertIn(f'<section class="view" id="{view}"', page)
        self.assertNotIn('id="files"', page)
        self.assertNotIn('class="call-src"', page)  # no conversations
        self.assertIn("Trial timeline", page)
        self.assertIn("Cost by milestone", page)

        self.assertIn("Nothing needs attention.", page)
        stats = self.data()["loops"]["backend-dev"]["stats"]
        self.assertEqual((stats["milestones"], stats["achieved"], stats["trials"],
                          stats["first_try"], stats["calls"]), (2, 2, 2, 2, 3))

    def test_cost_by_model_when_calls_ran_on_more_than_one(self):
        self.approved()
        self.assertEqual(self.cli("run"), 0, self.last_output)
        self.assertNotIn("Cost by model", self.page())  # one model: nothing to split

        records = [{"seq": 1, "step": "plan", "model": "opus", "cost_usd": 0.5},
                   {"seq": 2, "step": "implement", "model": "sonnet", "cost_usd": 0.25},
                   {"seq": 3, "step": "fix", "model": "sonnet", "cost_usd": 0.25},
                   {"seq": 4, "step": "fix", "model": None, "cost_usd": 0.1},  # no --model
                   {"seq": 5, "step": "fix", "cost_usd": 0.05}]  # recorded before `model`
        view = dashboard.calls_view({"loops": {"backend-dev": {"invocations": records}}})
        self.assertIn("Cost by model: opus $0.50 (1 call(s)) · sonnet $0.50 (2 call(s)) · "
                      "(Claude Code default) $0.10 (1 call(s)) · (not recorded) $0.05 (1 call(s))",
                      view)
        # The full dashboard groups by the model the transcript names, like its Model column.
        view = dashboard.calls_view({"loops": {"backend-dev": {"invocations": records}}},
                                    call_ids=lambda loop, r: f"c{r['seq']}",
                                    models={("backend-dev", 1): "claude-opus-5-5"})
        self.assertIn("claude-opus-5-5 $0.50 (1 call(s))", view)

    def test_failed_trials_and_retries_are_counted(self):
        self.approved()
        self.assertEqual(self.cli("run", env={"DEVLOOPS_STUB": "fail"}), 20,
                         self.last_output)
        page = self.page()
        self.assertIn("Stopped on failure", page)
        self.assertIn("devloops retry --milestone M01", page)
        tones = [tone for tone, _ in dashboard.attention(self.data())]
        self.assertEqual(tones[0], "critical")
        self.assertIn('Needs attention <span class="count">', page)
        self.assertEqual(self.cli("retry", "--no-continue", "--milestone", "M01", "--reason",
                                  "try again"), 0, self.last_output)
        self.assertEqual(self.cli("run"), 0, self.last_output)
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
        # Nothing is loaded from the network: one inline script, no external sources. The only
        # outside link is the project's own, which navigates and loads nothing.
        self.assertEqual(len(re.findall(r"<script", page)), 1)
        project = f'href="{ui.PROJECT_URL}"'
        self.assertEqual(page.count(project), 1)
        self.assertNotRegex(page.replace(project, ""), r'(src|href)="(https?:)?//')
        self.assertNotIn("<link", page)

    def test_a_voided_trial_and_its_rerun_keep_their_own_calls(self):
        # A service error voids trial 1; the next run reuses the number (and the trial folder).
        self.approved()
        self.scenario({"implement": [service_error(429), implemented("M01-T01"),
                                     implemented("M02-T01")]})
        self.assertEqual(self.cli("run"), 50, self.last_output)
        self.assertEqual(self.cli("run"), 0, self.last_output)
        [m1] = [m for m in self.data()["loops"]["backend-dev"]["milestones"] if m["id"] == "M01"]
        void, passed = m1["trials"]
        self.assertEqual((void["n"], void["status"], passed["n"], passed["status"]),
                         (1, "void", 1, "passed"))
        records = {r["session_id"]: r for r in self.data()["loops"]["backend-dev"]["invocations"]}
        self.assertEqual(len(void["sessions"]), 1)
        self.assertTrue(passed["sessions"])
        self.assertFalse(set(void["sessions"]) & set(passed["sessions"]))
        self.assertLess(max(records[s]["seq"] for s in void["sessions"]),
                        min(records[s]["seq"] for s in passed["sessions"]))
        self.assertIsNone(void["validation"])          # the folder holds the re-run's files
        self.assertTrue(passed["validation"]["passed"])
        notes = [text for tone, text in dashboard.attention(self.data()) if tone == "info"]
        self.assertEqual(notes, ['<a href="#ms-backend-dev-M01">backend-dev M01</a> passed after '
                                 '1 voided trial(s) (rate-limited)'])

    def test_written_when_the_command_ends_not_during_it(self):
        self.approved()
        self.scenario({"implement": [dict(implemented("M01-T01"), sleep_seconds=3),
                                     implemented("M02-T01")]})
        page_path = os.path.join(self.t.workspace_dir, "dashboard.html")
        os.remove(page_path)
        proc = self.start_cli("run")
        self.wait_for_call("implement")
        self.assertFalse(os.path.exists(page_path))
        self.assertEqual(proc.wait(timeout=60), 0)
        done = self.page()
        self.assertIn("Completed", done)
        self.assertNotIn("data-refresh", done)
        self.assertNotIn('class="btn live"', done)  # it never reloads itself
        self.assertEqual(self.data()["running"], [])

    def test_dashboard_light_off_stops_the_automatic_writes(self):
        self.t.make_project(self.t.root, {"workspaces_dir": "workspaces",
                                          "config": {"dashboard": {"light": False}}})
        self.assertEqual(self.first_run(), 10, self.last_output)
        page_path = os.path.join(self.t.workspace_dir, "dashboard.html")
        self.assertFalse(os.path.exists(page_path))
        self.assertNotIn("dashboard: ", self.last_output)
        self.assertIn("files and conversations: devloops dashboard --daemon", self.last_output)

    def test_a_dashboard_failure_never_changes_the_run_outcome(self):
        # A directory where the page should go makes the write fail.
        os.makedirs(os.path.join(self.t.workspace_dir, "dashboard.html"))
        self.assertEqual(self.first_run(), 10, self.last_output)
        self.assertIn("could not write the dashboard", self.last_output)
        self.assertEqual(self.run_state()["status"], "awaiting-approval")


if __name__ == "__main__":
    unittest.main()
