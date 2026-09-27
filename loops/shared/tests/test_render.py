"""Golden-file tests for the Markdown views. Set DEVLOOPS_REGEN_GOLDEN=1 to rewrite the goldens."""
import os
import tempfile
import unittest

import helpers
import samples
from devloops import render, state

GOLDEN_DIR = os.path.join(helpers.FIXTURES_DIR, "golden")
REGEN = os.environ.get("DEVLOOPS_REGEN_GOLDEN") == "1"

TEMPLATE = """# Task: backend-dev

Workspace {{workspace}}; mode {{mode}}; story {{story_id}}.
Requirements: {{requirements_path}} (sha256 {{requirements_sha256}})
Target: {{target_dir}}; API spec: {{api_spec_path}}

{{effective_config}}
"""


def t(minute):
    return f"2026-09-27T10:{minute:02d}:00.000Z"


def invocation(seq, step, mid, trial, cache_read=0):
    rec = samples.invocation_record()
    rec.update(seq=seq, step=step, milestone_id=mid, trial=trial,
               session_id=f"0000000{seq}-0000-4000-8000-000000000000",
               prompt_path=f"state/prompts/{seq:04d}-{step}.md")
    rec["tokens"] = {"input": 100 * seq, "output": 10 * seq, "cache_creation": 1,
                     "cache_read": cache_read}
    return rec


def build_state(loop_dir):
    plan = samples.plan()
    plan["stack"]["conflicts"] = ["The requirements mention a database; none is configured"]
    plan["open_questions"] = [{"id": "OQ1", "question": "Which database?",
                               "context": "Stack conflict", "affects": ["M02"]}]
    run = samples.run_state()
    run.update(
        status="stopped-on-failure",
        status_reason={"code": "trials-exhausted", "milestone_id": "M02",
                       "message": "milestone M02 failed after 2 of 2 trial(s)"},
        inputs={"requirements": {"path": "/work/prd.md", "sha256": "ab" * 32, "mode": "prd",
                                 "story_id": None}, "api_spec": None},
        target_dir="/work/target",
        effective_config={"max_trials": 2, "max_invocations_per_run": 60},
        invocation_count=4,
        planning={"status": "done", "trials": [
            {"n": 1, "kind": "plan", "status": "passed", "failure": None, "started_at": t(0),
             "ended_at": t(1)}]},
        milestones={
            "M01": {"status": "achieved", "tasks": {"M01-T01": "achieved"},
                    "trials": [{"n": 1, "status": "passed", "reason": None, "started_at": t(2),
                                "ended_at": t(4)}],
                    "started_at": t(2), "ended_at": t(4)},
            "M02": {"status": "failed", "tasks": {"M02-T01": "failed"},
                    "trials": [{"n": 1, "status": "failed", "reason": "validation-failed",
                                "started_at": t(5), "ended_at": t(6)},
                               {"n": 2, "status": "failed", "reason": "timeout",
                                "started_at": t(7), "ended_at": t(8)}],
                    "started_at": t(5), "ended_at": t(8)},
        })
    state.write_json_atomic(os.path.join(loop_dir, "state", "run.json"), run)
    state.write_json_atomic(os.path.join(loop_dir, "state", "plan.json"), plan)
    trial_docs = {
        ("M01", 1): {"kind": "implement", "status": "passed", "failure": None,
                     "validation": "validation.json",
                     "assumptions": [{"text": "IDs are integers", "affects": ["M01-T01"]}]},
        ("M02", 1): {"kind": "implement", "status": "failed", "validation": "validation.json",
                     "failure": {"reason": "validation-failed", "detail": "M02-AC1: failed"},
                     "assumptions": []},
        ("M02", 2): {"kind": "fix", "status": "failed",
                     "failure": {"reason": "timeout", "detail": "no result"}, "assumptions": []},
    }
    for (mid, n), doc in trial_docs.items():
        summary = next(x for x in run["milestones"][mid]["trials"] if x["n"] == n)
        doc.update(n=n, started_at=summary["started_at"], ended_at=summary["ended_at"])
        state.write_json_atomic(os.path.join(loop_dir, "state", "milestones", mid, "trials", str(n),
                                             "trial.json"), doc)
    vr = samples.validation_result()
    state.write_json_atomic(os.path.join(loop_dir, "state", "milestones", "M01", "trials", "1",
                                         "validation.json"), vr)
    for rec in (invocation(1, "plan", None, 1), invocation(2, "implement", "M01", 1),
                invocation(3, "implement", "M02", 1), invocation(4, "fix", "M02", 2, None)):
        state.append_jsonl(os.path.join(loop_dir, "state", "invocations.jsonl"), rec)
    for event in ({"at": t(1), "type": "plan-stored", "message": "2 milestone(s)"},
                  {"at": t(4), "type": "milestone-achieved", "message": "M01 List items",
                   "milestone": "M01"},
                  {"at": t(8), "type": "validation-failed", "message": "trial 2 failed: timeout",
                   "milestone": "M02", "trial": 2}):
        state.append_jsonl(os.path.join(loop_dir, "state", "events.jsonl"),
                           dict(event, loop="backend-dev"))
    return plan


class RenderGoldenTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        self.loop_dir = os.path.join(self.repo, "workspaces", "golden", "backend-dev")
        os.makedirs(os.path.join(self.repo, "loops", "backend-dev"))
        with open(os.path.join(self.repo, "loops", "backend-dev", "task.md"), "w") as f:
            f.write(TEMPLATE)
        self.plan = build_state(self.loop_dir)
        render.render_all(self.loop_dir, "backend-dev", "golden", self.repo, final=True,
                          questions=self.plan["open_questions"])

    def tearDown(self):
        self.tmp.cleanup()

    def assert_golden(self, relpath, golden_name):
        with open(os.path.join(self.loop_dir, relpath), encoding="utf-8") as f:
            actual = f.read()
        golden = os.path.join(GOLDEN_DIR, golden_name)
        if REGEN:
            os.makedirs(GOLDEN_DIR, exist_ok=True)
            with open(golden, "w", encoding="utf-8") as f:
                f.write(actual)
        with open(golden, encoding="utf-8") as f:
            self.assertEqual(actual, f.read(), f"{relpath} differs from {golden}")

    def test_views(self):
        for relpath, golden in (
                ("progress.md", "progress.md"),
                ("task.md", "task.md"),
                ("outputs/milestone-01-list-items.md", "milestone-01-list-items.md"),
                ("outputs/milestone-02-create-items.md", "milestone-02-create-items.md"),
                ("outputs/plan-summary.md", "plan-summary.md"),
                ("outputs/open-questions.md", "open-questions.md"),
                ("outputs/final-report.md", "final-report.md")):
            with self.subTest(view=relpath):
                self.assert_golden(relpath, golden)

    def test_views_are_regenerated_not_read_back(self):
        path = os.path.join(self.loop_dir, "outputs", "milestone-01-list-items.md")
        with open(path, "a") as f:
            f.write("hand edit\n")
        render.render_all(self.loop_dir, "backend-dev", "golden", self.repo)
        with open(path) as f:
            self.assertNotIn("hand edit", f.read())

    def test_open_questions_are_not_rewritten_unless_asked(self):
        path = os.path.join(self.loop_dir, "outputs", "open-questions.md")
        with open(path, "a") as f:
            f.write("note\n")
        render.render_all(self.loop_dir, "backend-dev", "golden", self.repo)
        with open(path) as f:
            self.assertTrue(f.read().endswith("note\n"))


class RenderUnitTest(unittest.TestCase):
    def test_slug_and_filename(self):
        self.assertEqual(render.slug("Create & list  Items!"), "create-list-items")
        self.assertEqual(render.slug("???"), "milestone")
        self.assertEqual(render.milestone_filename({"id": "M07", "title": "Log in"}),
                         "milestone-07-log-in.md")

    def test_task_placeholders(self):
        self.assertEqual(render.render_task("{{a}} {{b}} {{unknown}}", {"a": "x", "b": None}),
                         "x none {{unknown}}")

    def test_answers_survive_when_the_question_is_unchanged(self):
        qs = [{"id": "OQ1", "question": "Which DB?", "context": "c", "affects": []},
              {"id": "OQ2", "question": "Auth?", "context": "c", "affects": []}]
        first = render.render_open_questions("backend-dev", "ws", qs)
        answered = first.replace("**Answer:**\n\n### OQ2", "**Answer:** SQLite\nfile based\n\n"
                                 "### OQ2")
        self.assertIn("SQLite", answered)
        qs[1]["question"] = "Which auth?"  # changed question: its old answer must not carry over
        again = render.render_open_questions("backend-dev", "ws", qs,
                                             answered.replace("**Answer:**\n", "**Answer:** none\n"))
        self.assertIn("**Answer:** SQLite\nfile based", again)
        self.assertNotIn("**Answer:** none", again)

    def test_no_questions(self):
        self.assertIn("_No open questions._", render.render_open_questions("x", "ws", []))

    def test_progress_without_a_plan(self):
        text = render.render_progress("backend-dev", "ws", {"status": "planning"}, None, [], [], {})
        self.assertIn("**Status**: planning", text)
        self.assertIn("_No actions yet._", text)


if __name__ == "__main__":
    unittest.main()
