"""The dashboard's view data (dashboard.py; specs/005-dashboard-redesign data-model): tokens and
cost at every level, adding up from the recorded calls (SC-004)."""
import json
import os
import unittest

import helpers  # noqa: F401
from devloops import dashboard, state, workspace
from stub_loop import StubLoopMixin, WS, implemented, service_error


def record(seq, step="implement", tokens=(10, 2, 3, 5), cost=0.5, start=None, end=None):
    r = {"seq": seq, "step": step, "cost_usd": cost}
    if tokens is not None:
        r["tokens"] = dict(zip(dashboard.TOKEN_KEYS, tokens))
    if start:
        r["started_at"], r["ended_at"] = start, end
    return r


class TotalsTest(unittest.TestCase):
    def test_sums_and_partial(self):
        t = dashboard.totals([record(1), record(2, tokens=(1, 1, 1, 1), cost=0.25)])
        self.assertEqual(t["calls"], 2)
        self.assertAlmostEqual(t["cost"], 0.75)
        self.assertEqual(t["tokens"], {"input": 11, "output": 3, "cache_creation": 4,
                                       "cache_read": 6, "total": 24})
        self.assertFalse(t["partial"])
        self.assertTrue(dashboard.totals([record(1), record(2, tokens=None)])["partial"])
        self.assertTrue(dashboard.totals([record(1, cost=None)])["partial"])
        empty = dashboard.totals([])
        self.assertEqual((empty["calls"], empty["cost"], empty["tokens"]["total"], empty["partial"],
                          empty["seconds"]), (0, 0, 0, False, None))

    def test_seconds_span_the_records(self):
        t = dashboard.totals([record(1, start="2026-01-01T00:00:00Z", end="2026-01-01T00:00:10Z"),
                              record(2, start="2026-01-01T00:01:00Z", end="2026-01-01T00:01:30Z")])
        self.assertEqual(t["seconds"], 90)
        self.assertIsNone(dashboard.totals([record(1)])["seconds"])

    def test_add(self):
        a = dashboard.totals([record(1, start="2026-01-01T00:00:00Z", end="2026-01-01T00:00:10Z")])
        b = dashboard.totals([record(2, tokens=None)])
        s = dashboard.add(a, b)
        self.assertEqual((s["calls"], s["tokens"]["total"], s["partial"], s["seconds"]),
                         (2, 20, True, 10))
        self.assertAlmostEqual(s["cost"], 1.0)
        self.assertIsNone(dashboard.add()["seconds"])
        self.assertEqual(dashboard.add(a, a)["seconds"], 20)

    def test_loop_extras(self):
        t = dashboard.totals([record(1, tokens=(10, 5, 10, 30), cost=3.0)])
        extras = dashboard.loop_extras(t, 2)
        self.assertAlmostEqual(extras["cache_hit_rate"], 30 / 50)
        self.assertAlmostEqual(extras["cost_per_achieved"], 1.5)
        none = dashboard.loop_extras(dashboard.totals([record(1, tokens=(0, 5, 0, 0))]), 0)
        self.assertEqual(none, {"cache_hit_rate": None, "cost_per_achieved": None})


class LevelsTest(StubLoopMixin, unittest.TestCase):
    def data(self):
        return dashboard.collect(workspace.open_workspace(WS, self.t.project(), self.t.kit(),
                                                         create=False))

    def assert_sum(self, level, records, what):
        expected = dashboard.totals(records)
        for key in ("calls", "tokens", "partial"):
            self.assertEqual(level[key], expected[key], f"{what}: {key}")
        self.assertAlmostEqual(level["cost"], expected["cost"], msg=what)

    def check_levels(self, data):
        for loop, d in data["loops"].items():
            by_seq = {r["seq"]: r for r in d["invocations"]}
            self.assert_sum(d["totals"], d["invocations"], loop)
            self.assert_sum(d["planning_totals"],
                            [r for r in d["invocations"] if r.get("milestone_id") is None],
                            f"{loop} planning")
            for name, step in d["by_step"].items():
                self.assert_sum(step["totals"], [r for r in d["invocations"]
                                                 if (r.get("step") or "?") == name], name)
            for m in d["milestones"]:
                self.assert_sum(m["totals"], [r for r in d["invocations"]
                                              if r.get("milestone_id") == m["id"]], m["id"])
                trial_totals = [t["totals"] for t in m["trials"]]
                summed = dashboard.add(*trial_totals)
                self.assertEqual((summed["calls"], summed["tokens"]),
                                 (m["totals"]["calls"], m["totals"]["tokens"]), m["id"])
                for t in m["trials"]:
                    seqs = [seq for s in t["steps"] for seq in s["calls"]]
                    self.assertEqual(seqs, sorted(seqs))
                    self.assert_sum(t["totals"], [by_seq[s] for s in seqs],
                                    f"{m['id']} trial {t['n']}")
                    for s in t["steps"]:
                        self.assert_sum(s["totals"], [by_seq[q] for q in s["calls"]],
                                        f"{m['id']} trial {t['n']} {s['step']}")
            achieved = d["stats"]["achieved"]
            self.assertEqual(d["extras"], dashboard.loop_extras(d["totals"], achieved))
        usage = data["totals"]["usage"]
        self.assertEqual(usage["calls"], data["totals"]["calls"])
        self.assertEqual(usage["tokens"]["total"], data["totals"]["tokens"])
        return data

    def test_a_completed_run(self):
        self.approved()
        self.assertEqual(self.cli("run"), 0, self.last_output)
        d = self.check_levels(self.data())["loops"]["backend-dev"]
        self.assertGreater(d["totals"]["tokens"]["total"], 0)
        self.assertFalse(d["totals"]["partial"])
        self.assertIsNotNone(d["extras"]["cache_hit_rate"])
        self.assertAlmostEqual(d["extras"]["cost_per_achieved"], d["totals"]["cost"] / 2)

    def test_a_voided_trial_and_its_rerun_keep_their_own_totals(self):
        self.approved()
        self.scenario({"implement": [service_error(429), implemented("M01-T01"),
                                     implemented("M02-T01")]})
        self.assertEqual(self.cli("run"), 50, self.last_output)
        self.assertEqual(self.cli("run"), 0, self.last_output)
        data = self.check_levels(self.data())
        [m1] = [m for m in data["loops"]["backend-dev"]["milestones"] if m["id"] == "M01"]
        void, passed = m1["trials"]
        self.assertEqual((void["key"], passed["key"]), ("1.1", "1"))
        self.assertEqual(void["totals"]["calls"], 1)
        self.assertGreaterEqual(passed["totals"]["calls"], 1)

    def test_a_call_without_tokens_makes_every_level_above_it_partial(self):
        self.approved()
        self.assertEqual(self.cli("run"), 0, self.last_output)
        path = self.path(os.path.join("state", "invocations.jsonl"))
        records = state.read_jsonl(path)
        target = next(r for r in records if r.get("milestone_id") == "M01")
        del target["tokens"]
        with open(path, "w", encoding="utf-8") as f:
            f.write("".join(json.dumps(r) + "\n" for r in records))
        d = self.check_levels(self.data())["loops"]["backend-dev"]
        [m1] = [m for m in d["milestones"] if m["id"] == "M01"]
        trial = next(t for t in m1["trials"]
                     if target["seq"] in [q for s in t["steps"] for q in s["calls"]])
        self.assertTrue(trial["totals"]["partial"])
        self.assertTrue(m1["totals"]["partial"])
        self.assertTrue(d["totals"]["partial"])
        self.assertFalse(d["planning_totals"]["partial"])
        [m2] = [m for m in d["milestones"] if m["id"] == "M02"]
        self.assertFalse(m2["totals"]["partial"])


def question(text, answer="", suggested="", source=""):
    return {"question": text, "context": "", "affects": "", "suggested": suggested,
            "reason": "because" if suggested else "", "source": source, "answer": answer}


def trial(n, status, key=None, reason=None, criteria=None):
    return {"key": key or str(n), "n": n, "attempt": 1, "kind": "implement", "status": status,
            "reason": reason, "detail": None, "started_at": None, "ended_at": None,
            "seconds": None, "totals": dashboard.totals([]),
            "validation": {"criteria": criteria} if criteria is not None else None}


class AttentionTest(unittest.TestCase):
    def data(self):
        stopped = {
            "status": "stopped-on-failure",
            "status_reason": {"code": "trials-exhausted", "message": "M02 used its trials",
                              "milestone_id": "M02"},
            "milestones": [
                {"id": "M01", "status": "achieved",
                 "trials": [trial(1, "failed", reason="checks-failed"), trial(2, "passed")]},
                {"id": "M02", "status": "failed",
                 "trials": [trial(1, "failed", criteria=[{"criterion_id": "AC1", "passed": False},
                                                          {"criterion_id": "AC2", "passed": True}])]},
            ],
            "plan": {}, "questions": {
                "OQ1": question("Which port?"),
                "OQ2": question("Which db?", "sqlite", "sqlite", "accepted automatically by run"),
                "OQ3": question("Which cache?", suggested="none")},
            "invocations": [{"seq": 1, "step": "plan", "failure_class": "none"},
                            {"seq": 3, "step": "implement", "failure_class": "timeout"}]}
        interrupted = {"status": "implementing", "milestones": [], "plan": {}, "questions": {},
                       "status_reason": {"code": "interrupted", "message": "Ctrl+C"},
                       "invocations": []}
        return {"loops": {"backend-dev": stopped, "frontend-dev": interrupted},
                "large_evidence": [{"path": "backend-dev/big.log", "bytes": 2 << 20}]}

    def test_every_kind_with_its_route(self):
        items = dashboard.attention_items(self.data(), lambda rel: f"#/files?q={rel}")
        by_kind = {}
        for item in items:
            by_kind.setdefault(item["kind"], []).append(item)
        self.assertEqual(set(by_kind), {"loop", "failing-criteria", "passed-after", "auto-accepted",
                                        "unanswered", "suggested", "failed-call",
                                        "large-evidence"})
        self.assertEqual([i["tone"] for i in items],
                         sorted((i["tone"] for i in items), key=dashboard.TONE_ORDER.get))
        for item in items:
            self.assertTrue(item["route"].startswith("#/"), item)
            self.assertTrue(item["message"], item)
        stopped, interrupted = by_kind["loop"]
        self.assertEqual((stopped["loop"], stopped["tone"], stopped["route"]),
                         ("backend-dev", "critical", "#/loop/backend-dev"))
        self.assertEqual(stopped["action"]["route"], "#/loop/backend-dev/m/M02/t/1")
        self.assertIn("`devloops retry --milestone M02", stopped["action"]["text"])
        self.assertEqual((interrupted["tone"], interrupted["action"]), ("warning", None))
        [failing] = by_kind["failing-criteria"]
        self.assertEqual((failing["criteria"], failing["route"]),
                         (["AC1"], "#/loop/backend-dev/m/M02/t/1"))
        [after] = by_kind["passed-after"]
        self.assertEqual((after["failed"], after["voided"], after["reasons"], after["route"]),
                         (1, 0, ["checks-failed"], "#/loop/backend-dev?m=M01"))
        self.assertEqual(by_kind["unanswered"][0]["questions"], ["OQ1"])
        self.assertEqual(by_kind["auto-accepted"][0]["questions"], ["OQ2"])
        self.assertEqual(by_kind["suggested"][0]["questions"], ["OQ3"])
        self.assertEqual(by_kind["unanswered"][0]["route"], "#/questions")
        [call] = by_kind["failed-call"]
        self.assertEqual((call["call"], call["failure"], call["route"]),
                         (3, "timeout", "#/call/backend-dev/3"))
        [large] = by_kind["large-evidence"]
        self.assertEqual(large["files"][0]["route"], "#/files?q=backend-dev/big.log")

    def test_routes_are_encoded_as_the_app_reads_them(self):
        self.assertEqual(dashboard.route("overview"), "#/")
        self.assertEqual(dashboard.route("trial", loop="b", milestone="M 1", key="1.2"),
                         "#/loop/b/m/M%201/t/1.2")
        self.assertEqual(dashboard.route("loop", {"m": "M01", "x": None}, loop="b"),
                         "#/loop/b?m=M01")


class FakeContext:
    def __init__(self, data):
        self.data, self.workspaces, self.version = data, ["w"], None


class BuildersTest(StubLoopMixin, unittest.TestCase):
    def ctx(self):
        ws = workspace.open_workspace(WS, self.t.project(), self.t.kit(), create=False)
        return dashboard.Context(ws, self.t.env, ["other", WS], version="v1")

    def test_a_completed_run(self):
        self.approved()
        self.assertEqual(self.cli("run"), 0, self.last_output)
        ctx = self.ctx()
        s = dashboard.summary(ctx)
        self.assertEqual((s["workspace"], s["version"], s["workspaces"], s["status"], s["running"]),
                         (WS, "v1", ["other", WS], "completed", []))
        [card] = s["loops"]
        self.assertEqual((card["loop"], card["status"], card["milestones"], card["first_try"],
                          card["route"], card["next_action"]),
                         ("backend-dev", "completed", {"total": 2, "achieved": 2}, 2,
                          "#/loop/backend-dev", None))
        self.assertGreater(card["totals"]["tokens"]["total"], 0)
        self.assertEqual(s["totals"]["tokens"], card["totals"]["tokens"])
        self.assertEqual((s["totals"]["achieved"], s["totals"]["milestones"]), (2, 2))
        self.assertEqual(s["attention"], [])
        self.assertEqual(s["counts"]["calls"], card["totals"]["calls"])
        self.assertNotIn("files", s["counts"])
        self.assertEqual([r["label"] for r in s["timeline"]],
                         ["backend-dev · Planning", "backend-dev · M01", "backend-dev · M02"])
        self.assertEqual(s["timeline"][1]["trials"][0]["route"], "#/loop/backend-dev/m/M01/t/1")
        self.assertAlmostEqual(sum(r["totals"]["cost"] for r in s["cost_by_milestone"]),
                               card["totals"]["cost"])
        self.assertAlmostEqual(sum(r["totals"]["cost"] for r in s["by_step"]),
                               card["totals"]["cost"])

        d = dashboard.loop(ctx, "backend-dev")
        self.assertEqual(set(d["totals"]["tokens"]),
                         {"input", "output", "cache_creation", "cache_read", "total"})
        self.assertIsNotNone(d["totals"]["cache_hit_rate"])
        self.assertAlmostEqual(d["totals"]["cost_per_achieved"], d["totals"]["cost"] / 2)
        self.assertTrue(d["planning"]["trials"])
        self.assertIn("calls", d["planning"]["totals"])
        m1 = d["milestones"][0]
        self.assertEqual((m1["id"], m1["status"], m1["trials"][0]["route"], m1["criteria_trial"]),
                         ("M01", "achieved", "#/loop/backend-dev/m/M01/t/1", "1"))
        self.assertTrue(all(c["result"] == "passed" for c in m1["criteria"]), m1["criteria"])
        self.assertEqual(set(d["by_step"]), {"plan", "implement"})
        labels = {o["label"]: o for o in d["outputs"]}
        self.assertEqual(labels["Progress"]["path"], "backend-dev/progress.md")
        self.assertEqual(labels["Progress"]["id"], ctx.file_ref("backend-dev/progress.md")["id"])
        self.assertTrue(ctx.file_ref("no/such.md")["missing"])
        with self.assertRaises(dashboard.NotFound):
            dashboard.loop(ctx, "frontend-dev")

        c = dashboard.calls(ctx)
        records = ctx.data["loops"]["backend-dev"]["invocations"]
        self.assertEqual([(r["loop"], r["seq"]) for r in c["calls"]],
                         [("backend-dev", r["seq"]) for r in records])
        first = c["calls"][0]
        self.assertEqual((first["route"], first["conversation"]),
                         (f"#/call/backend-dev/{first['seq']}", "copied"))
        self.assertEqual(first["totals"], dashboard.totals([records[0]]))
        self.assertEqual(sum(m["calls"] for m in c["by_model"]), len(records))

        f = dashboard.files(ctx)
        self.assertEqual((f["count"], f["trees"][0]["name"]), (ctx.index["count"], "backend-dev"))
        events = dashboard.events(ctx)["events"]
        self.assertTrue(events)
        self.assertEqual([e["at"] for e in events], sorted(e["at"] for e in events))
        self.assertTrue(all(e["loop"] == "backend-dev" for e in events))
        q = dashboard.questions(ctx)
        self.assertEqual((q["questions"], q["grants"]), ([], []))
        self.assertEqual(q["assumptions"][0]["loop"], "backend-dev")

    def test_a_stopped_loop_says_what_to_do(self):
        self.approved()
        self.scenario({"implement": [service_error(429)]})
        self.assertEqual(self.cli("run"), 50, self.last_output)
        s = dashboard.summary(self.ctx())
        [card] = s["loops"]
        self.assertEqual(card["status"], "stopped-on-service-error")
        self.assertIn("`devloops run`", card["next_action"]["text"])
        self.assertEqual(s["attention"][0]["kind"], "loop")

    def test_questions(self):
        loops = {"backend-dev": {
            "plan": {"open_questions": [{"id": "OQ1", "question": "Port?", "context": "the API",
                                         "affects": ["M01"], "suggested_answer": "8080",
                                         "suggestion_reason": "common"}]},
            "questions": {"OQ1": dict(question("Port?", "9090", "8080")),
                          "OQ2": question("Db?")},
            "grants": [{"milestone_id": "M01", "extra_trials": 2}]}}
        q = dashboard.questions(FakeContext({"loops": loops}))
        one, two = q["questions"]
        self.assertEqual((one["id"], one["answer"], one["status"], one["context"], one["affects"]),
                         ("OQ1", "9090", "developer", "the API", ["M01"]))
        self.assertEqual((two["id"], two["status"]), ("OQ2", "none"))
        self.assertEqual(q["grants"], [{"milestone_id": "M01", "extra_trials": 2,
                                        "loop": "backend-dev"}])


if __name__ == "__main__":
    unittest.main()
