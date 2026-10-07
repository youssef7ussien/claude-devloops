"""Suggested answers to open questions, and `questions: accept-suggested`.

Claude suggests an answer to every question it raises. An empty answer accepts the suggestion when
the developer approves (or retries after a needs-input stop); under `questions: accept-suggested`
the run accepts the suggestions itself instead of pausing, and flags them for review.
"""
import os
import re
import unittest

import helpers  # noqa: F401 - puts the package on sys.path
import samples
from devloops import render
from stub_loop import StubLoopMixin, implemented

OPEN_QUESTIONS = "outputs/open-questions.md"
QUESTION = "Should listing items be paginated, and with what page size?"
SUGGESTION = "No pagination; return every item."


def steps(plan, **more):
    """A scenario whose plan is `plan` and whose milestones pass."""
    return dict({"plan": {"structured_output": plan},
                 "implement": [implemented("M01-T01"), implemented("M02-T01")]}, **more)


def plan_with(*questions):
    """A sample plan whose open questions are `(id, suggested_answer)` pairs."""
    plan = samples.plan()
    plan["open_questions"] = [
        {"id": qid, "question": f"Question {qid}?", "context": "c", "affects": ["M01"],
         "suggested_answer": suggested, "suggestion_reason": f"reason {qid}" if suggested else ""}
        for qid, suggested in questions]
    return plan


class SuggestedAnswersTest(StubLoopMixin, unittest.TestCase):
    def questions(self):
        return render.parse_questions(self.read(OPEN_QUESTIONS))

    def answer(self, qid, text):
        content = self.read(OPEN_QUESTIONS)
        block = re.search(rf"(?ms)^### {re.escape(qid)}\n.*?(?=^### |\Z)", content).group(0)
        self.write(OPEN_QUESTIONS, content.replace(
            block, re.sub(r"(?m)^\*\*Answer:\*\*.*$", f"**Answer:** {text}", block, count=1)))

    def dashboard(self):
        with open(os.path.join(self.t.workspace_dir, "dashboard.html"), encoding="utf-8") as f:
            return f.read()

    # --- the developer reviews -------------------------------------------------------------------

    def test_the_suggestion_is_written_beside_an_empty_answer(self):
        self.scenario(steps(plan_with(("OQ1", "Port 8765."))))
        self.assertEqual(self.first_run(), 10, self.last_output)
        content = self.read(OPEN_QUESTIONS)
        self.assertIn("**Suggested answer:** Port 8765.\n**Why:** reason OQ1\n\n**Answer:**\n",
                      content)
        self.assertIn("Suggested, not accepted yet", self.dashboard())

    def test_approve_accepts_the_suggestions_left_empty(self):
        self.scenario(steps(plan_with(("OQ1", "Port 8765."),
                                                               ("OQ2", "Use SQLite."))))
        self.assertEqual(self.first_run(), 10, self.last_output)
        self.answer("OQ2", "Use PostgreSQL.")
        self.assertEqual(self.cli("approve", "--no-continue", "backend-dev"), 0, self.last_output)

        qs = self.questions()
        self.assertEqual(qs["OQ1"]["answer"], "Port 8765.")
        self.assertEqual(qs["OQ1"]["source"], "suggested answer, accepted by `devloops approve`")
        self.assertEqual((qs["OQ2"]["answer"], qs["OQ2"]["source"]), ("Use PostgreSQL.", ""))
        rs = self.run_state()
        self.assertEqual(rs["approval"]["accepted_suggestions"], ["OQ1"])
        self.assertEqual(rs["approval"]["answers_sha256"], self.answers_sha256())
        self.assertEqual(rs["answers_sha256"], self.answers_sha256())
        self.assertIn("suggested answer(s) accepted for OQ1", self.events("approved")[-1]["message"])

        # The answers file the run fingerprinted is the one implementation reads.
        self.assertEqual(self.cli("run", "backend-dev"), 0, self.last_output)
        context = self.context_of(self.calls("implement")[0])
        self.assertIn("**Answer:** Port 8765.", context["answers"])
        self.assertIn("Use PostgreSQL.", context["answers"])
        report = self.read("outputs/final-report.md")
        self.assertIn("## Suggested answers accepted", report)
        self.assertIn("**OQ1** Question OQ1? **Answer:** Port 8765.", report)
        self.assertNotIn("**OQ2**", report.split("## Suggested answers accepted")[1])

    def test_retry_accepts_the_suggestion_of_a_needs_input_question(self):
        self.approved()
        self.scenario({"implement": implemented("M01-T01", needs_input=[QUESTION],
                                                suggested=SUGGESTION)})
        self.assertEqual(self.cli("run", "backend-dev"), 20, self.last_output)
        self.assertIn("an empty answer accepts Claude's suggested answer", self.last_output)

        self.assertEqual(self.cli("retry", "--no-continue",
                                  "backend-dev", "--milestone", "M01", "--reason",
                                  "suggestion is fine"), 0, self.last_output)
        q = self.questions()["OQ1"]
        self.assertEqual((q["answer"], q["source"]),
                         (SUGGESTION, "suggested answer, accepted by `devloops retry`"))
        grant = self.run_state()["grants"][-1]
        self.assertEqual(grant["accepted_suggestions"], ["OQ1"])
        self.assertEqual(grant["answers_sha256"], self.answers_sha256())

        self.scenario({"fix": implemented("M01-T01"), "implement": implemented("M02-T01")})
        self.assertEqual(self.cli("run", "backend-dev"), 0, self.last_output)
        self.assertIn(f"**Answer:** {SUGGESTION}", self.context_of(self.calls("fix")[0])["answers"])

    def test_a_written_answer_wins_over_the_suggestion(self):
        self.approved()
        self.scenario({"implement": implemented("M01-T01", needs_input=[QUESTION],
                                                suggested=SUGGESTION)})
        self.assertEqual(self.cli("run", "backend-dev"), 20, self.last_output)
        self.answer("OQ1", "Page size 50.")
        self.assertEqual(self.cli("retry", "--no-continue",
                                  "backend-dev", "--milestone", "M01", "--reason", "x"),
                         0, self.last_output)
        q = self.questions()["OQ1"]
        self.assertEqual((q["answer"], q["source"]), ("Page size 50.", ""))
        self.assertNotIn("accepted_suggestions", self.run_state()["grants"][-1])

    # --- questions: accept-suggested ------------------------------------------------------------

    def test_accept_suggested_approves_the_plan_and_implements(self):
        config = self.config_file({"questions": "accept-suggested"})
        self.scenario(steps(plan_with(("OQ1", "Port 8765."))))
        self.assertEqual(self.first_run("--config", config), 0, self.last_output)

        rs = self.run_state()
        self.assertEqual(rs["status"], "completed")
        self.assertEqual(rs["approval"]["action"], "auto-approve")
        self.assertEqual(rs["approval"]["accepted_suggestions"], ["OQ1"])
        self.assertEqual(self.steps_called(), ["plan", "implement", "implement"])
        self.assertEqual(self.questions()["OQ1"]["source"],
                         "suggested answer, accepted automatically (questions: accept-suggested)")
        self.assertIn("plan approved automatically", self.events("approved")[-1]["message"])
        self.assertIn("## Suggested answers accepted", self.read("outputs/final-report.md"))
        self.assertIn("1 suggested answer(s) accepted automatically", self.dashboard())

    def test_accept_suggested_still_pauses_on_a_question_without_a_suggestion(self):
        self.scenario(steps(plan_with(("OQ1", "Port 8765."),
                                                               ("OQ2", ""))))
        self.assertEqual(self.first_run("--accept-suggested"), 10, self.last_output)
        self.assertIn("OQ2 has no suggested answer", self.last_output)
        rs = self.run_state()
        self.assertEqual((rs["status"], rs["approval"]), ("awaiting-approval", None))
        self.assertEqual(self.questions()["OQ1"]["answer"], "")  # nothing accepted yet

        # Once the developer answers OQ2, the next run approves the rest by itself.
        self.answer("OQ2", "Use SQLite.")
        self.assertEqual(self.cli("run", "backend-dev", "--accept-suggested"), 0,
                         self.last_output)
        self.assertEqual(self.run_state()["approval"]["accepted_suggestions"], ["OQ1"])

    def test_replan_pauses_even_under_accept_suggested(self):
        self.scenario(steps(plan_with(("OQ1", "Port 8765."), ("OQ2", "")),
                            replan={"structured_output": plan_with(("OQ1", "Port 8765."))}))
        self.assertEqual(self.first_run("--accept-suggested"), 10, self.last_output)
        self.assertEqual(self.cli("replan", "--no-continue", "backend-dev"), 10, self.last_output)
        rs = self.run_state()
        self.assertEqual((rs["status"], rs["approval"]), ("awaiting-approval", None))
        self.assertNotIn("implement", self.steps_called())
        # The next `run` approves the reviewed plan by itself.
        self.assertEqual(self.cli("run", "backend-dev"), 0, self.last_output)
        self.assertEqual(self.run_state()["approval"]["action"], "auto-approve")

    def test_accept_suggested_given_at_the_approval_pause(self):
        self.scenario(steps(plan_with(("OQ1", "Port 8765."))))
        self.assertEqual(self.first_run(), 10, self.last_output)
        self.assertEqual(self.cli("run", "backend-dev"), 10, self.last_output)  # still asks
        self.assertEqual(self.cli("run", "backend-dev", "--accept-suggested"), 0,
                         self.last_output)
        self.assertEqual(self.run_state()["status"], "completed")
        self.assertTrue(self.events("config-override"))

    def test_accept_suggested_answers_a_needs_input_question_and_continues(self):
        self.scenario({"plan": {"structured_output": samples.plan()},
                       "implement": [implemented("M01-T01", needs_input=[QUESTION],
                                                 suggested=SUGGESTION),
                                     implemented("M02-T01")],
                       "fix": implemented("M01-T01")})
        self.assertEqual(self.first_run("--accept-suggested"), 0, self.last_output)

        rs = self.run_state()
        self.assertEqual(rs["status"], "completed")
        # The trial that asked was built on its suggestion and validated as it was: it passed.
        self.assertEqual([(t["n"], t["status"], t["reason"]) for t in rs["milestones"]["M01"]["trials"]],
                         [(1, "passed", None)])
        self.assertEqual(self.steps_called(), ["plan", "implement", "implement"])
        self.assertEqual(self.trial("M01", 1)["needs_input"][0]["question"], QUESTION)
        [auto] = rs["auto_answers"]
        self.assertEqual((auto["milestone_id"], auto["trial"], auto["question_ids"]),
                         ("M01", 1, ["OQ1"]))
        self.assertEqual(rs["answers_sha256"], self.answers_sha256())
        self.assertEqual(auto["answers_sha256"], self.answers_sha256())
        self.assertIn("is validated now", self.events("answers-accepted")[0]["message"])
        self.assertIn("after M01 trial 1", self.questions()["OQ1"]["source"])

    def test_an_auto_answered_trial_that_fails_validation_hands_the_answer_to_the_fix(self):
        config = self.config_file({"max_trials": 2, "questions": "accept-suggested"})
        self.scenario({"plan": {"structured_output": samples.plan()},
                       "implement": implemented("M01-T01", needs_input=[QUESTION],
                                                suggested=SUGGESTION),
                       "fix": implemented("M01-T01")})
        self.assertEqual(self.first_run("--config", config, env={"DEVLOOPS_STUB": "fail"}), 20,
                         self.last_output)
        rs = self.run_state()
        self.assertEqual(rs["status_reason"]["code"], "trials-exhausted")
        self.assertIn("accepted automatically for OQ1", rs["status_reason"]["message"])
        self.assertEqual([(t["n"], t["reason"]) for t in rs["milestones"]["M01"]["trials"]],
                         [(1, "validation-failed"), (2, "validation-failed")])
        self.assertIn(f"**Answer:** {SUGGESTION}", self.context_of(self.calls("fix")[0])["answers"])

    def test_accepted_answers_are_the_recorded_fingerprint(self):
        """Resuming after an automatic answer compares against the answered file, not the
        approval's older one."""
        self.scenario({"plan": {"structured_output": samples.plan()},
                       "implement": [implemented("M01-T01", needs_input=[QUESTION],
                                                 suggested=SUGGESTION),
                                     {"exit_code": 1, "api_error_status": 529,
                                      "result": "overloaded"}]})
        self.assertEqual(self.first_run("--accept-suggested"), 50, self.last_output)
        self.scenario({"implement": implemented("M02-T01")})
        self.assertEqual(self.cli("run", "backend-dev"), 0, self.last_output)
        self.assertEqual(self.run_state()["status"], "completed")

    def test_accept_suggested_on_the_last_trial_still_validates_it(self):
        """The trial is validated as built on the suggestion, so its last trial can pass."""
        config = self.config_file({"max_trials": 1, "questions": "accept-suggested"})
        self.scenario({"plan": {"structured_output": samples.plan()},
                       "implement": [implemented("M01-T01", needs_input=[QUESTION],
                                                 suggested=SUGGESTION),
                                     implemented("M02-T01")]})
        self.assertEqual(self.first_run("--config", config), 0, self.last_output)
        rs = self.run_state()
        self.assertEqual(rs["milestones"]["M01"]["status"], "achieved")
        self.assertEqual(rs["auto_answers"][0]["question_ids"], ["OQ1"])
        self.assertEqual(self.questions()["OQ1"]["answer"], SUGGESTION)

    def test_under_ask_a_question_still_stops_at_once_for_retry(self):
        self.approved()
        self.scenario({"implement": implemented("M01-T01", needs_input=[QUESTION],
                                                suggested=SUGGESTION)})
        self.assertEqual(self.cli("run", "backend-dev"), 20, self.last_output)
        rs = self.run_state()
        self.assertEqual(rs["status_reason"]["code"], "needs-input")
        self.assertNotIn("auto_answers", rs)
        self.assertIsNone(self.trial("M01", 1)["validation"])   # not validated
        self.assertEqual(self.cli("retry", "--no-continue",
                                  "backend-dev", "--milestone", "M01", "--reason", "ok"),
                         0, self.last_output)
        self.assertEqual(self.run_state()["grants"][-1]["accepted_suggestions"], ["OQ1"])

    def test_accept_suggested_without_a_suggestion_stops_as_before(self):
        self.approved()
        self.scenario({"implement": implemented("M01-T01", needs_input=[QUESTION])})
        self.assertEqual(self.cli("run", "backend-dev", "--accept-suggested"), 20,
                         self.last_output)
        reason = self.run_state()["status_reason"]
        self.assertEqual(reason["code"], "needs-input")
        self.assertNotIn("auto_answers", self.run_state())


class QuestionsFileTest(unittest.TestCase):
    QUESTIONS = [{"id": "OQ1", "question": "Which DB?", "context": "c", "affects": ["M01"],
                  "suggested_answer": "SQLite.\n**Note:** keep it in the target.",
                  "suggestion_reason": "no server"}]

    def test_a_bold_label_inside_a_suggestion_stays_part_of_it(self):
        text = render.render_open_questions("backend-dev", "ws", self.QUESTIONS)
        q = render.parse_questions(text)["OQ1"]
        self.assertEqual(q["suggested"], "SQLite.\n**Note:** keep it in the target.")
        accepted, _ = render.accept_suggestions(text, "by test")
        self.assertEqual(render.parse_questions(accepted)["OQ1"]["answer"], q["suggested"])

    def test_a_rewritten_accepted_suggestion_is_the_developers(self):
        text, _ = render.accept_suggestions(
            render.render_open_questions("backend-dev", "ws", self.QUESTIONS), "by test")
        q = render.parse_questions(text)["OQ1"]
        self.assertEqual(render.effective_answer(q)[1], "accepted")
        q["answer"] = "PostgreSQL."
        self.assertEqual(render.effective_answer(q), ("PostgreSQL.", "developer"))


if __name__ == "__main__":
    unittest.main()
