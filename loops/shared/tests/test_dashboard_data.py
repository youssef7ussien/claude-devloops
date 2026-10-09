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


if __name__ == "__main__":
    unittest.main()
