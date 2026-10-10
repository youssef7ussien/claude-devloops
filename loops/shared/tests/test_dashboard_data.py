"""The dashboard's view data (dashboard.py; specs/005-dashboard-redesign data-model): tokens and
cost at every level, adding up from the recorded calls (SC-004)."""
import json
import os
import unittest

import helpers
import samples
from devloops import claude, dashboard, schema, state, workspace
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
        plan = self.ctx().data["loops"]["backend-dev"]["plan"]
        self.assertEqual(s["counts"]["assumptions"], len(plan.get("assumptions") or []))
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
        m1 = d["milestones"][0]
        self.assertEqual((m1["id"], m1["status"], m1["trials"][0]["route"], m1["criteria_trial"]),
                         ("M01", "achieved", "#/loop/backend-dev/m/M01/t/1", "1"))
        self.assertTrue(all(c["result"] == "passed" for c in m1["criteria"]), m1["criteria"])
        self.assertEqual([row["step"] for row in d["steps"]], ["plan", "implement"])
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
        self.assertEqual(c["steps"], list(claude.STEPS))  # the step chips' order (FR-020i)

        f = dashboard.files(ctx)
        self.assertEqual((f["count"], f["trees"][0]["name"]), (ctx.index["count"], "backend-dev"))
        events = dashboard.events(ctx)["events"]
        self.assertTrue(events)
        self.assertEqual([e["at"] for e in events], sorted(e["at"] for e in events))
        self.assertTrue(all(e["loop"] == "backend-dev" for e in events))
        q = dashboard.questions(ctx)
        self.assertEqual(q["questions"], [])
        self.assertNotIn("grants", q)  # on the milestone in the loop view (FR-020j)
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

    def test_a_publish_stop_asks_for_a_retry(self):
        d = {"status": "stopped-on-failure", "milestones": [],
             "status_reason": {"code": "publish-failed", "milestone_id": "M02"}}
        action = dashboard.next_action("backend-dev", d)
        self.assertIn("`devloops retry --milestone M02`", action["text"])
        self.assertEqual(action["route"], "#/loop/backend-dev")
        self.assertEqual(dashboard._waiting_for(d), "retry")

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
        self.assertNotIn("grants", q)


PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
       b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01"
       b"\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82")


class TrialTest(StubLoopMixin, unittest.TestCase):
    """`dashboard.trial`: a trial's steps, validation, and why it did not pass (FR-018, FR-019)."""

    def ctx(self):
        ws = workspace.open_workspace(WS, self.t.project(), self.t.kit(), create=False)
        return dashboard.Context(ws, self.t.env)

    def failed_once(self):
        """M01's trial 1 fails validation; the run stops (one trial allowed)."""
        self.approved()
        self.assertEqual(self.cli("run", "--max-trials", "1", env={"DEVLOOPS_STUB": "fail"}), 20,
                         self.last_output)
        return os.path.join(self.loop_dir, "state", "milestones", "M01", "trials", "1")

    def write_validation(self, trial_dir, doc):
        schema.validate(doc, "validation-result.schema.json")
        state.write_json_atomic(os.path.join(trial_dir, "validation.json"), doc)

    def test_every_reason_with_its_evidence(self):
        trial_dir = self.failed_once()
        evidence = os.path.join(trial_dir, "evidence")
        for name, data in (("c1.body", b"{}"), ("c1.headers", b"HTTP/1.1 500"),
                           ("shot.png", PNG)):
            with open(os.path.join(evidence, name), "wb") as f:
                f.write(data)
        with open(os.path.join(trial_dir, "unit-tests.log"), "w") as f:
            f.write("1 failed\n")
        plan = state.read_json(os.path.join(self.loop_dir, "state", "plan.json"))
        [first, *rest] = [c["id"] for c in plan["milestones"][0]["acceptance_criteria"]]
        doc = {
            "kind": "playwright", "passed": False, "ui_url": "http://127.0.0.1:5173/",
            "criteria": [{"criterion_id": first, "passed": False, "steps": ["open /", "add"],
                          "observed": "the list stays empty", "evidence": ["evidence/shot.png"]}],
            "checks": [{"check_id": "c1", "passed": False, "command": "curl -s /items",
                        "response": {"status": 500, "body_path": "evidence/c1.body",
                                     "headers_path": "evidence/c1.headers"},
                        "failures": ["status 500, expected 200"]},
                       {"check_id": "c2", "passed": True, "command": "curl -s /health",
                        "response": {"status": 200}, "failures": []}],
            "network_requests": [{"method": "GET", "url": "http://127.0.0.1:8000/items",
                                  "status": 500},
                                 {"method": "POST", "url": "http://127.0.0.1:8000/x",
                                  "error": "net::ERR_CONNECTION_REFUSED"}],
            "contract": {"passed": False, "problem": "no network log",
                         "unmatched_operations": ["POST /x"]},
            "unit_tests": {"enabled": True, "command": "pytest", "exit_code": 1,
                           "log_path": "unit-tests.log"},
            "boundary": {"passed": False, "violations": ["wrote ../outside.txt"]}}
        self.write_validation(trial_dir, doc)
        # The fake's transcript reads a file only: add a write, as Claude Code records it.
        [call] = [r for r in state.read_jsonl(self.path(os.path.join("state", "invocations.jsonl")))
                  if r.get("milestone_id") == "M01"]
        with open(self.path(call["conversation_path"]), "a", encoding="utf-8") as f:
            for name in ("app.py", "..env.example"):
                f.write(json.dumps({"type": "assistant", "message": {"role": "assistant",
                                                                     "content": [
                    {"type": "tool_use", "id": "t1", "name": "Write", "input": {
                        "file_path": os.path.join(self.t.target_dir, name), "content": "x"}}]}})
                    + "\n")
        t = dashboard.trial(self.ctx(), "backend-dev", "M01", "1")
        self.assertEqual((t["key"], t["n"], t["status"], t["milestone"]), ("1", 1, "failed", "M01"))
        self.assertEqual(t["validation"], doc)
        kinds = [r["kind"] for r in t["why"]]
        self.assertEqual(kinds, ["check"] + ["criterion"] * (1 + len(rest))
                         + ["contract", "unit-tests", "boundary"])
        check, crit = t["why"][0], t["why"][1]
        self.assertEqual((check["check_id"], check["command"], check["status"], check["failures"]),
                         ("c1", "curl -s /items", 500, ["status 500, expected 200"]))
        self.assertEqual([r["path"].rsplit("/", 1)[1] for r in check["evidence"]],
                         ["c1.body", "c1.headers"])
        self.assertTrue(all(r["id"] for r in check["evidence"]), check["evidence"])
        self.assertEqual((crit["criterion_id"], crit["steps"], crit["observed"]),
                         (first, ["open /", "add"], "the list stays empty"))
        self.assertTrue(crit["text"])
        self.assertEqual([(r["kind"], bool(r["id"])) for r in crit["evidence"]], [("image", True)])
        # A criterion without a result counts as failed (FR-068).
        self.assertEqual([r["criterion_id"] for r in t["why"][2:2 + len(rest)]], rest)
        contract, unit, boundary = t["why"][-3:]
        self.assertEqual((contract["problem"], contract["unmatched_operations"]),
                         ("no network log", ["POST /x"]))
        self.assertEqual(contract["network_requests"], doc["network_requests"])
        self.assertEqual((unit["command"], unit["exit_code"], unit["log"]["path"]),
                         ("pytest", 1, f"backend-dev/state/milestones/M01/trials/1/unit-tests.log"))
        self.assertEqual(boundary["violations"], ["wrote ../outside.txt"])
        # SC-005: every failing item of validation.json is a reason.
        shown = json.dumps(t["why"])
        for item in [c["check_id"] for c in doc["checks"] if not c["passed"]] + \
                [c["criterion_id"] for c in doc["criteria"]] + ["POST /x", "wrote ../outside.txt"]:
            self.assertIn(item, shown)
        self.assertNotIn('"c2"', shown)
        # Steps in run order, with their calls and totals adding up.
        records = {r["seq"]: r for r in self.ctx().data["loops"]["backend-dev"]["invocations"]}
        seqs = [c["seq"] for s in t["steps"] for c in s["calls"]]
        self.assertEqual(seqs, sorted(seqs))
        self.assertTrue(seqs)
        self.assertEqual(t["totals"], dashboard.totals([records[q] for q in seqs]))
        for s in t["steps"]:
            self.assertEqual(s["totals"]["calls"], len(s["calls"]))
            self.assertTrue(all(c["route"] == f"#/call/backend-dev/{c['seq']}" for c in s["calls"]))
        # Files: the trial's folder, and what its calls changed.
        paths = [r["path"] for r in t["evidence"]]
        self.assertIn("backend-dev/state/milestones/M01/trials/1/evidence/shot.png", paths)
        self.assertIn("backend-dev/state/milestones/M01/trials/1/validation.json", paths)
        self.assertIn("..env.example", [f["path"] for f in t["files_changed"]])  # in the target
        [app] = [f for f in t["files_changed"] if f["path"] == "app.py"]
        self.assertEqual((app["step"], app["tool"], app["seq"]), ("implement", "Write", seqs[0]))
        self.assertGreater(app["added"], 0)  # the lines of the change, worked out by the server
        self.assertEqual(app["removed"], 0)
        # FR-020d: what the plan's ids say, and the target, without the loop's whole answer
        self.assertEqual(t["refs"], dashboard.loop(self.ctx(), "backend-dev")["refs"])
        self.assertEqual(t["target_dir"], self.ctx().data["loops"]["backend-dev"]["target_dir"])
        # FR-018b: the folder's files carry what the tree shows (size, kind).
        self.assertTrue(all(isinstance(r["size"], int) and r["kind"] for r in t["evidence"]),
                        t["evidence"])
        self.assertEqual(app["call_route"],
                         f"#/call/backend-dev/{seqs[0]}?at={app['block']}")

    def test_a_trial_that_failed_without_a_validation(self):
        trial_dir = self.failed_once()
        os.remove(os.path.join(trial_dir, "validation.json"))
        run = state.read_json(os.path.join(self.loop_dir, "state", "run.json"))
        run["milestones"]["M01"]["trials"][0]["reason"] = "interrupted"
        state.write_json_atomic(os.path.join(self.loop_dir, "state", "run.json"), run)
        doc = state.read_json(os.path.join(trial_dir, "trial.json"))
        doc["failure"] = {"reason": "interrupted", "detail": "the driver stopped"}
        state.write_json_atomic(os.path.join(trial_dir, "trial.json"), doc)
        t = dashboard.trial(self.ctx(), "backend-dev", "M01", "1")
        self.assertIsNone(t["validation"])
        self.assertEqual(t["why"], [{"kind": "interrupted", "message": "the driver stopped"}])

    def test_a_voided_trial(self):
        self.approved()
        self.scenario({"implement": [service_error(429), implemented("M01-T01"),
                                     implemented("M02-T01")]})
        self.assertEqual(self.cli("run"), 50, self.last_output)
        self.assertEqual(self.cli("run"), 0, self.last_output)
        ctx = self.ctx()
        void = dashboard.trial(ctx, "backend-dev", "M01", "1.1")
        self.assertEqual((void["status"], void["validation"], void["evidence"]), ("void", None, []))
        [reason] = void["why"]
        self.assertEqual(reason["kind"], "voided")
        self.assertIn(void["reason"], reason["message"])
        self.assertEqual(void["steps"][0]["calls"][0]["failure_class"], "service")
        passed = dashboard.trial(ctx, "backend-dev", "M01", "1")
        self.assertEqual((passed["status"], passed["why"]), ("passed", []))
        self.assertEqual([x["key"] for x in passed["routes"]["trials"]], ["1.1", "1"])
        for args in (("M01", "9"), ("M01", "1.2"), ("M99", "1")):
            with self.assertRaises(dashboard.NotFound):
                dashboard.trial(ctx, "backend-dev", *args)



class LoopTest(StubLoopMixin, unittest.TestCase):
    """`dashboard.loop`: the loop view's data, with the plan merged in (FR-020–FR-020e)."""

    def ctx(self):
        ws = workspace.open_workspace(WS, self.t.project(), self.t.kit(), create=False)
        return dashboard.Context(ws, self.t.env)

    @staticmethod
    def counted(m):
        return len([t for t in m["trials"] if t["status"] != "void"])

    def test_waiting_for_approval(self):
        plan = samples.plan()
        plan["open_questions"] = [{"id": "OQ1", "question": "Which port?", "context": "the API",
                                   "affects": ["M01"], "suggested_answer": "8080",
                                   "suggestion_reason": "common"}]
        self.scenario({"plan": {"structured_output": plan}})
        self.assertEqual(self.first_run(), 10, self.last_output)
        p = dashboard.loop(self.ctx(), "backend-dev")
        # us3 is not the project's default workspace: the commands name it
        self.assertEqual(p["approval"], {"status": "waiting", "commands": [
            "devloops approve --workspace us3", "devloops replan --workspace us3"]})
        self.assertEqual(p["next_action"]["route"], "#/loop/backend-dev")
        self.assertEqual([m["id"] for m in p["milestones"]], ["M01", "M02"])
        m1, m2 = p["milestones"]
        self.assertEqual((m1["title"], m1["goal"], m1["status"], self.counted(m1),
                          m1["depends_on"], m2["depends_on"], m1["route"]),
                         ("List items", "Clients can list items", "pending", 0, [], ["M01"],
                          "#/loop/backend-dev?m=M01"))
        self.assertEqual(m1["criteria"], [{"id": "M01-AC1", "text": "GET /items returns 200 and "
                                           "a list", "requirement_refs": ["FR-1"],
                                           "result": None, "observed": None, "evidence": []}])
        self.assertEqual(m1["tasks"], [{"id": "M01-T01", "title": "GET /items",
                                        "description": "Return all items",
                                        "requirement_refs": ["FR-1"], "status": "pending"}])
        self.assertEqual(p["questions"], {"open": 1, "unanswered": 1, "assumptions": 1,
                                          "route": "#/questions?loop=backend-dev"})
        refs = p["refs"]
        inventory = plan["requirements_inventory"][0]
        self.assertEqual(refs[inventory["ref"]], inventory["summary"])
        self.assertEqual((refs["M01-T01"], refs["M01-AC1"]),
                         ("GET /items", "GET /items returns 200 and a list"))
        self.assertEqual(p["stack"]["summary"], "Python stdlib HTTP server")
        self.assertEqual(p["runtime"]["openapi_path"], "openapi.json")
        q = dashboard.questions(self.ctx())
        self.assertEqual(q["refs"]["backend-dev"], refs)
        with self.assertRaises(dashboard.NotFound):
            dashboard.loop(self.ctx(), "frontend-dev")

    def test_planning_attempts(self):
        bad = samples.plan()
        bad["milestones"] = []
        self.scenario({"plan": [{"structured_output": bad}, {"structured_output": samples.plan()}]})
        self.assertEqual(self.first_run(), 10, self.last_output)
        p = dashboard.loop(self.ctx(), "backend-dev")
        self.assertNotIn("planning", p)
        first, second = [r for r in p["steps"] if r["step"] == "plan"]  # one row per attempt
        self.assertEqual((first["attempt"], first["status"], first["reason"], first["calls"]),
                         (1, "failed", "invalid-output", 1))
        self.assertTrue(first["detail"])
        self.assertEqual((second["attempt"], second["status"], second["reason"]), (2, "passed", None))
        self.assertLess(first["started_at"], second["started_at"])
        self.assertEqual([r["route"] for r in (first, second)],
                         ["#/call/backend-dev/1", "#/call/backend-dev/2"])
        records = self.ctx().data["loops"]["backend-dev"]["invocations"]
        self.assertAlmostEqual(first["totals"]["cost"] + second["totals"]["cost"],
                               sum(r["cost_usd"] for r in records if r["step"] == "plan"))

    def test_steps(self):
        self.approved()
        self.assertEqual(self.cli("run"), 0, self.last_output)
        d = dashboard.loop(self.ctx(), "backend-dev")
        self.assertNotIn("by_step", d)
        steps = [row["step"] for row in d["steps"]]
        self.assertEqual(steps[0], "plan")
        plan = d["steps"][0]  # one attempt: one row, without an attempt number
        self.assertEqual((plan["attempt"], plan["status"], plan["route"]),
                         (None, "passed", "#/call/backend-dev/1"))
        self.assertEqual(steps.count("plan"), 1)
        self.assertIn("implement", steps)
        records = self.ctx().data["loops"]["backend-dev"]["invocations"]
        for row in d["steps"]:  # each step's first call, and the rows in that order
            self.assertEqual(row["started_at"], min(r["started_at"] for r in records
                                                    if r["step"] == row["step"]))
        starts = [row["started_at"] for row in d["steps"]]
        self.assertEqual(starts, sorted(starts))
        self.assertEqual(sum(row["calls"] for row in d["steps"]), d["stats"]["calls"])
        self.assertAlmostEqual(sum(row["share"] for row in d["steps"]), 1)
        self.assertEqual(sum(row["totals"]["calls"] for row in d["steps"]), d["stats"]["calls"])
        implement = next(row for row in d["steps"] if row["step"] == "implement")
        self.assertAlmostEqual(implement["seconds"], sum(r["duration_ms"] for r in records
                                                         if r["step"] == "implement") / 1000)
        # by start; a step without a known start last (driver order, then an unknown step)
        rows = dashboard.step_rows({"invocations": [
            {"step": "zz", "cost_usd": 1}, {"step": "plan", "cost_usd": 1},
            {"step": "fix", "cost_usd": 1, "started_at": "2026-01-01T00:00:02.000Z"},
            {"step": "implement", "cost_usd": 1, "started_at": "2026-01-01T00:00:01.000Z"}],
            "totals": {"cost": 4}}, "backend-dev")
        self.assertEqual([(r["step"], r["share"], r["seconds"]) for r in rows],
                         [("implement", 0.25, None), ("fix", 0.25, None), ("plan", 0.25, None),
                          ("zz", 0.25, None)])
        self.assertEqual(rows[0]["started_at"], "2026-01-01T00:00:01.000Z")
        # a planning call recorded without a step is a "?" row, not an error
        rows = dashboard.step_rows({"invocations": [{"seq": 1, "trial": 1, "cost_usd": 1}],
                                    "planning": [{"n": 1, "status": "passed"}],
                                    "totals": {"cost": 1}}, "backend-dev")
        self.assertEqual([(r["step"], r["attempt"], r["status"]) for r in rows], [("?", None, "passed")])

    def test_criteria_from_the_latest_counted_trial(self):
        self.approved()
        self.assertEqual(self.cli("run", "--max-trials", "1", env={"DEVLOOPS_STUB": "fail"}), 20,
                         self.last_output)
        p = dashboard.loop(self.ctx(), "backend-dev")
        self.assertEqual((p["approval"]["status"], p["approval"]["action"]), ("approved", "approve"))
        self.assertNotIn("commands", p["approval"])
        m1, m2 = p["milestones"]
        self.assertEqual((m1["status"], self.counted(m1), m1["criteria_trial"]), ("failed", 1, "1"))
        self.assertEqual([(c["result"], c["trial_route"]) for c in m1["criteria"]],
                         [("failed", "#/loop/backend-dev/m/M01/t/1")])
        self.assertEqual([c["result"] for c in m2["criteria"]], [None])
        self.assertNotIn("trial_route", m2["criteria"][0])
        self.assertEqual(m1["tasks"][0]["status"], "failed")  # as run.json records it
        # A criterion the result does not mention fails too (FR-068)
        trial_dir = os.path.join(self.loop_dir, "state", "milestones", "M01", "trials", "1")
        doc = state.read_json(os.path.join(trial_dir, "validation.json"))
        doc["criteria"] = []
        state.write_json_atomic(os.path.join(trial_dir, "validation.json"), doc)
        self.assertEqual(dashboard.loop(self.ctx(), "backend-dev")["milestones"][0]["criteria"][0]
                         ["result"], "failed")
        # A trial still running leaves the last result shown
        run_path = os.path.join(self.loop_dir, "state", "run.json")
        run = state.read_json(run_path)
        run["milestones"]["M01"]["trials"].append({"n": 2, "status": "in-progress",
                                                   "started_at": "2030-01-01T00:00:00Z"})
        state.write_json_atomic(run_path, run)
        m1 = dashboard.loop(self.ctx(), "backend-dev")["milestones"][0]
        self.assertEqual((self.counted(m1), m1["criteria_trial"], m1["criteria"][0]["result"],
                          m1["criteria"][0]["trial_route"]),
                         (2, "1", "failed", "#/loop/backend-dev/m/M01/t/1"))

    def test_a_voided_trial_is_not_counted(self):
        self.approved()
        self.scenario({"implement": [service_error(429), implemented("M01-T01"),
                                     implemented("M02-T01")]})
        self.assertEqual(self.cli("run"), 50, self.last_output)
        m1 = dashboard.loop(self.ctx(), "backend-dev")["milestones"][0]
        self.assertEqual((self.counted(m1), [c["result"] for c in m1["criteria"]]), (0, [None]))
        self.assertEqual(self.cli("run"), 0, self.last_output)
        m1 = dashboard.loop(self.ctx(), "backend-dev")["milestones"][0]
        self.assertEqual((m1["status"], self.counted(m1), m1["criteria"][0]["result"]),
                         ("achieved", 1, "passed"))
        self.assertNotIn("trial_route", m1["criteria"][0])

    def test_the_workspace_flag(self):
        class Project:
            default_workspace, workspaces_dir = "main", "/p/workspaces"

        class Ws:
            project = Project()

            def __init__(self, name, path):
                self.name, self.path = name, path
        self.assertEqual(dashboard.workspace_flag(Ws("main", "/p/workspaces/main")), "")
        self.assertEqual(dashboard.workspace_flag(Ws("us3", "/p/workspaces/us3")),
                         " --workspace us3")
        self.assertEqual(dashboard.workspace_flag(Ws("x y", "/elsewhere/x y")),
                         " --workspace '/elsewhere/x y'")


SECRET = "S3CR3T-zürich-value"


class CallTest(StubLoopMixin, unittest.TestCase):
    """`dashboard.call`: one call with its conversation (FR-021, data-model Call)."""

    def setUp(self):
        super().setUp()
        self.t.make_project(self.t.root, {"workspaces_dir": "workspaces",
                                          "config": {"secrets": {"literals": [SECRET]}}})
        self.approved()
        self.assertEqual(self.cli("run"), 0, self.last_output)

    def ctx(self):
        ws = workspace.open_workspace(WS, self.t.project(), self.t.kit(), create=False)
        return dashboard.Context(ws, self.t.env)

    def records(self):
        return state.read_jsonl(self.path(os.path.join("state", "invocations.jsonl")))

    def rewrite(self, seq, **changes):
        records = self.records()
        for r in records:
            if r["seq"] == seq:
                r.update(changes)
                for k in [k for k, v in changes.items() if v is None]:
                    del r[k]
        with open(self.path(os.path.join("state", "invocations.jsonl")), "w") as f:
            f.write("".join(json.dumps(r) + "\n" for r in records))

    def test_a_copied_conversation(self):
        [r] = [r for r in self.records() if r.get("milestone_id") == "M01"]
        lines = [
            # a secret as written, and one that JSON escaping changed (ensure_ascii: \u00fc)
            {"type": "user", "message": {"role": "user", "content": f"use {SECRET}"}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": "a", "name": "Bash", "input": {"command": "pytest"}}]}},
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "a", "is_error": True,
                 "content": f"failed near {SECRET}"}]}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": "b", "name": "Edit", "input": {
                    "file_path": os.path.join(self.t.target_dir, "app.py"),
                    "old_string": "a", "new_string": "b"}}]}}]
        with open(self.path(r["conversation_path"]), "a", encoding="utf-8") as f:
            f.write("".join(json.dumps(x) + "\n" for x in lines) + "not json\n")
        c = dashboard.call(self.ctx(), "backend-dev", str(r["seq"]))
        self.assertEqual((c["seq"], c["step"], c["milestone_id"], c["trial"], c["session_id"],
                          c["conversation"], c["route"]),
                         (r["seq"], "implement", "M01", 1, r["session_id"], "copied",
                          f"#/call/backend-dev/{r['seq']}"))
        self.assertEqual(c["totals"], dashboard.totals([r]))
        self.assertEqual(c["routes"]["trial"], "#/loop/backend-dev/m/M01/t/1")
        self.assertEqual(c["prompt"]["path"], f"backend-dev/{r['prompt_path']}")
        self.assertTrue(c["prompt"]["id"])
        self.assertTrue(c["settings"]["path"].endswith("-implement.settings.json"), c["settings"])
        self.assertTrue(c["settings"]["id"])
        self.assertEqual(c["prompt_sources"], r["prompt_sources"])
        self.assertTrue(c["prompt_sources"])
        text = json.dumps(c, ensure_ascii=False)
        self.assertNotIn(SECRET, text)
        self.assertNotIn("S3CR3T", text)
        n = len(c["records"])
        self.assertEqual(c["records"][-1], {"raw": "not json"})
        self.assertEqual(c["errors"], [n - 3])
        self.assertIn({"path": "app.py", "tool": "Edit", "block": n - 2, "added": 1, "removed": 1},
                      c["files_changed"])
        self.assertEqual(c["refs"], dashboard.loop(self.ctx(), "backend-dev")["refs"])
        self.assertEqual(c["files_changed"][-1]["path"], "app.py")
        with self.assertRaises(dashboard.NotFound):
            dashboard.call(self.ctx(), "backend-dev", "999")
        with self.assertRaises(dashboard.NotFound):
            dashboard.call(self.ctx(), "frontend-dev", "1")

    def test_records_keep_what_the_actions_need(self):
        """The view builds its actions from the records (research R-15): times, thinking
        durations, images, and the final answer reach it unchanged, and secrets do not."""
        [r] = [r for r in self.records() if r.get("milestone_id") == "M01"]
        image = {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                             "data": "iVBORw0KGgoAAAANSUhEUg=="}}
        lines = [
            {"type": "assistant", "timestamp": "2026-01-01T00:00:01.000Z", "thinkingDurationMs": 735,
             "message": {"role": "assistant", "content": [{"type": "thinking", "thinking": ""}]}},
            {"type": "assistant", "timestamp": "2026-01-01T00:00:02.000Z", "message": {
                "role": "assistant", "content": [{"type": "tool_use", "id": "s", "name": "Shot",
                                                  "input": {}}]}},
            {"type": "user", "timestamp": "2026-01-01T00:00:02.500Z", "message": {
                "role": "user", "content": [{"type": "tool_result", "tool_use_id": "s", "content": [
                    {"type": "text", "text": f"saw {SECRET}"}, image]}]}},
            {"type": "assistant", "timestamp": "2026-01-01T00:00:03.000Z", "message": {
                "role": "assistant", "content": [{"type": "tool_use", "id": "o", "name": "StructuredOutput",
                                                  "input": {"tasks": [{"id": "M01-T01", "status": "implemented",
                                                                       "note": f"used {SECRET}"}]}}]}}]
        with open(self.path(r["conversation_path"]), "a", encoding="utf-8") as f:
            f.write("".join(json.dumps(x) + "\n" for x in lines))
        c = dashboard.call(self.ctx(), "backend-dev", str(r["seq"]))
        think, use, result, answer = c["records"][-4:]
        self.assertEqual((think["timestamp"], think["thinkingDurationMs"]), ("2026-01-01T00:00:01.000Z", 735))
        self.assertEqual(use["message"]["content"][0]["id"], "s")
        self.assertEqual(result["timestamp"], "2026-01-01T00:00:02.500Z")
        self.assertEqual(result["message"]["content"][0]["content"][1], image)
        self.assertEqual(answer["message"]["content"][0]["input"]["tasks"][0]["status"], "implemented")
        text = json.dumps(c, ensure_ascii=False)
        self.assertNotIn(SECRET, text)
        self.assertNotIn("S3CR3T", text)

    def test_from_history_and_unavailable(self):
        first, second = self.records()[:2]
        # The fake keeps each session in its history, as Claude Code does
        self.assertTrue(self.t.env.get("CLAUDE_CONFIG_DIR"))
        self.rewrite(first["seq"], conversation_path=None, conversation=None)
        self.rewrite(second["seq"], conversation_path=None, conversation="unavailable",
                     conversation_reason="not-found")
        ctx = self.ctx()
        c = dashboard.call(ctx, "backend-dev", str(first["seq"]))
        self.assertEqual(c["conversation"], "history")
        self.assertTrue(c["records"])
        self.assertNotIn("S3CR3T", json.dumps(c, ensure_ascii=False))
        c = dashboard.call(ctx, "backend-dev", str(second["seq"]))
        self.assertEqual((c["conversation"], c["unavailable_reason"], c["records"]),
                         ("unavailable", "not-found", []))
        os.remove(self.path(self.records()[2]["conversation_path"]))
        c = dashboard.call(ctx, "backend-dev", str(self.records()[2]["seq"]))
        self.assertEqual(c["conversation"], "unavailable")
        self.assertTrue(c["unavailable_reason"].startswith("missing: "), c["unavailable_reason"])

if __name__ == "__main__":
    unittest.main()
