"""`needs_input` stops and the answers fingerprint (T050; FR-051a, FR-055a, research R-20).

Written before T053 (`needs_input`), T055 (answers fingerprinting), and T056 (`retry`), so most of
this module fails until then.
"""
import re
import unittest

import samples
from stub_loop import StubLoopMixin, implemented

QUESTION = "Should listing items be paginated, and with what page size?"
OPEN_QUESTIONS = "outputs/open-questions.md"


class NeedsInputTest(StubLoopMixin, unittest.TestCase):
    def answer(self, qid, text):
        """Write `text` after the `**Answer:**` marker of question `qid`."""
        content = self.read(OPEN_QUESTIONS)
        block = re.search(rf"(?ms)^### {re.escape(qid)}\n.*?(?=^### |\Z)", content)
        self.assertIsNotNone(block, f"{qid} not in open-questions.md:\n{content}")
        answered = re.sub(r"(?m)^\*\*Answer:\*\*.*$", f"**Answer:** {text}", block.group(0),
                          count=1)
        self.write(OPEN_QUESTIONS, content.replace(block.group(0), answered))

    def stopped_on_needs_input(self):
        self.approved()
        self.scenario({"implement": implemented("M01-T01", needs_input=[QUESTION]),
                       "fix": implemented("M01-T01")})
        self.assertEqual(self.cli("run", "backend-dev"), 20, self.last_output)

    def test_needs_input_fails_the_milestone_at_once(self):
        self.stopped_on_needs_input()
        rs = self.run_state()
        self.assertEqual(rs["status"], "stopped-on-failure")
        self.assertEqual(rs["status_reason"]["code"], "needs-input")
        self.assertEqual(rs["status_reason"]["milestone_id"], "M01")
        m1 = rs["milestones"]["M01"]
        self.assertEqual(m1["status"], "failed")
        # Trial 1 of 3, and no further trials: a question is not something a fix can answer.
        self.assertEqual([(t["n"], t["status"], t["reason"]) for t in m1["trials"]],
                         [(1, "failed", "needs-input")])
        self.assertEqual(self.steps_called(), ["plan", "implement"])
        self.assertEqual(self.trial("M01", 1)["needs_input"][0]["question"], QUESTION)
        self.assertTrue(self.events("needs-input"))

        # The question is appended as a new OQ<n> with an empty answer.
        content = self.read(OPEN_QUESTIONS)
        self.assertIn("### OQ1", content)
        self.assertIn(f"**Question:** {QUESTION}", content)
        block = content.split("### OQ1", 1)[1]
        self.assertRegex(block, r"(?m)^\*\*Answer:\*\*\s*$")

    def test_retry_is_refused_until_the_questions_are_answered(self):
        self.stopped_on_needs_input()
        before = self.snapshot_state()
        self.assertEqual(self.cli("retry", "backend-dev", "--milestone", "M01", "--reason", "x"),
                         2, self.last_output)
        self.assertIn("answer OQ1", self.last_output)
        self.assertEqual(self.snapshot_state(), before)  # no grant was recorded

    def test_questions_are_redacted_before_they_are_stored(self):
        secret = "tok-3f9a1c7e5d"
        config = self.config_file({"secrets": {"literals": [secret]}})
        self.approved("--config", config)
        self.scenario({"implement": implemented(
            "M01-T01", needs_input=[f"Is {secret} the production API token?"])})
        self.assertEqual(self.cli("run", "backend-dev"), 20, self.last_output)
        for relpath in ("outputs/open-questions.md", "state/milestones/M01/trials/1/trial.json"):
            self.assertNotIn(secret, self.read(relpath), relpath)
        self.assertIn("the production API token?", self.read(OPEN_QUESTIONS))

    def test_answering_and_retry_resumes_the_milestone(self):
        self.stopped_on_needs_input()
        self.answer("OQ1", "No pagination; return every item.")
        self.assertEqual(self.cli("retry", "backend-dev", "--milestone", "M01", "--reason",
                                  "answered OQ1"), 0, self.last_output)
        self.scenario({"fix": implemented("M01-T01"), "implement": implemented("M02-T01")})
        self.assertEqual(self.cli("run", "backend-dev"), 0, self.last_output)
        rs = self.run_state()
        self.assertEqual(rs["status"], "completed")
        self.assertEqual(rs["milestones"]["M01"]["status"], "achieved")
        # The fix trial sees the answer and the developer's reason.
        context = self.context_of(self.calls("fix")[0])
        self.assertIn("No pagination; return every item.", context["answers"])
        self.assertEqual(context["developer_guidance"], ["answered OQ1"])

    def test_editing_answers_after_approve_is_an_input_change(self):
        self.approved()
        with open(self.path(OPEN_QUESTIONS), "a", encoding="utf-8") as f:
            f.write("\nAn afterthought.\n")
        self.assertEqual(self.cli("run", "backend-dev"), 30, self.last_output)
        reason = self.run_state()["status_reason"]
        self.assertEqual((reason["code"], reason["input"]), ("input-changed", "answers"))
        self.assertEqual(self.steps_called(), ["plan"])  # stopped before any trial

    def test_editing_answers_while_awaiting_approval_is_expected(self):
        plan = samples.plan()
        plan["open_questions"] = [{"id": "OQ1", "question": "Which port?", "context": "runtime",
                                   "affects": ["M01"]}]
        self.scenario({"plan": {"structured_output": plan}})
        self.assertEqual(self.first_run(), 10, self.last_output)

        self.answer("OQ1", "8765")
        self.assertEqual(self.cli("run", "backend-dev"), 10, self.last_output)  # still paused
        self.assertEqual(self.run_state()["status"], "awaiting-approval")
        self.assertEqual(self.cli("replan", "backend-dev"), 10, self.last_output)
        self.answer("OQ1", "8766")
        self.assertEqual(self.cli("approve", "backend-dev"), 0, self.last_output)
        self.assertEqual(self.run_state()["approval"]["answers_sha256"], self.answers_sha256())

    def test_editing_answers_after_a_needs_input_stop_is_recorded_by_the_grant(self):
        self.stopped_on_needs_input()
        approved_hash = self.run_state()["approval"]["answers_sha256"]
        self.answer("OQ1", "Page size 50.")
        new_hash = self.answers_sha256()
        self.assertNotEqual(new_hash, approved_hash)

        self.assertEqual(self.cli("retry", "backend-dev", "--milestone", "M01", "--reason",
                                  "answered"), 0, self.last_output)
        self.assertEqual(self.run_state()["grants"][-1]["answers_sha256"], new_hash)
        # The latest grant's hash is the one compared now, so the run proceeds.
        self.scenario({"fix": implemented("M01-T01"), "implement": implemented("M02-T01")})
        self.assertEqual(self.cli("run", "backend-dev"), 0, self.last_output)
        self.assertEqual(self.run_state()["status"], "completed")


if __name__ == "__main__":
    unittest.main()
