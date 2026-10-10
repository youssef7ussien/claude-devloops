"""View data for the dashboard API (specs/005-dashboard-redesign contracts/api.md,
data-model.md).

Everything is read from the workspace's state (`workspace.json`, each loop's `state/` and
`outputs/open-questions.md`, `run/state.json`); nothing is written. `collect` gathers a workspace
once, and each builder (`summary`, `loop`, `trial`, `call`, …) turns it into the plain data of one
API path; the server (serve.py) and the export (dashboard_export.py) redact and send it.
"""
import os
import shlex
import socket
import threading
import urllib.parse
from datetime import datetime, timezone

from . import artifacts, claude, render, state

LOOPS = ("backend-dev", "frontend-dev")

# Status presentation: (label, icon, tone). Tones map to the fixed status palette; the icon and the
# label always travel with the color, so state is never read from color alone.
RUN_STATUS = {
    "completed": ("Completed", "✓", "good"),
    "awaiting-approval": ("Awaiting approval", "⏸", "warning"),
    "planning": ("Planning", "◷", "neutral"),
    "implementing": ("Implementing", "◷", "neutral"),
    "stopped-on-failure": ("Stopped on failure", "✕", "critical"),
    "stopped-on-input-error": ("Stopped on input error", "✕", "critical"),
    "stopped-on-service-error": ("Stopped on service error", "!", "serious"),
    "not-started": ("Not started", "–", "muted"),
}
TRIAL_STATUS = {
    "passed": ("Passed", "✓", "good"),
    "failed": ("Failed", "✕", "critical"),
    "void": ("Voided (not counted)", "!", "serious"),
    "in-progress": ("In progress", "◷", "neutral"),
}
MILESTONE_STATUS = {
    "achieved": ("Achieved", "✓", "good"),
    "failed": ("Failed", "✕", "critical"),
    "in-progress": ("In progress", "◷", "neutral"),
    "pending": ("Pending", "–", "muted"),
}
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp")


# --- collecting -------------------------------------------------------------------------------------

def _parse_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _seconds(start, end):
    a, b = _parse_time(start), _parse_time(end)
    return (b - a).total_seconds() if a and b else None


def _within(record, trial):
    """Whether a call started during a trial (from its start to its end, or on if it has none)."""
    at, start = _parse_time(record.get("started_at")), _parse_time(trial.get("started_at"))
    end = _parse_time(trial.get("ended_at"))
    if not at or not start:
        return True
    return start <= at and (end is None or at <= end)


TOKEN_KEYS = ("input", "output", "cache_creation", "cache_read")


def _tokens(records):
    total = {k: 0 for k in TOKEN_KEYS}
    for r in records:
        for k in total:
            total[k] += (r.get("tokens") or {}).get(k) or 0
    return total


def _cost(records):
    return sum(r.get("cost_usd") or 0 for r in records)


def _empty_tokens():
    return dict({k: 0 for k in TOKEN_KEYS}, total=0)


def totals(records):
    """The usage of some invocation records (specs/005 data-model, Totals): `{calls, cost, tokens:
    {input, output, cache_creation, cache_read, total}, partial, seconds}`.

    `partial` is true when a record lacks `tokens` or `cost_usd`, so its sums are a lower bound.
    `seconds` is the wall time from the earliest `started_at` to the latest `ended_at` (None when
    either is unknown)."""
    tokens, cost, partial = _empty_tokens(), 0.0, False
    for r in records:
        used = r.get("tokens")
        if not isinstance(used, dict) or r.get("cost_usd") is None:
            partial = True
        for k in TOKEN_KEYS:
            tokens[k] += (used if isinstance(used, dict) else {}).get(k) or 0
        cost += r.get("cost_usd") or 0
    tokens["total"] = sum(tokens[k] for k in TOKEN_KEYS)
    starts = [t for t in (_parse_time(r.get("started_at")) for r in records) if t]
    ends = [t for t in (_parse_time(r.get("ended_at")) for r in records) if t]
    seconds = (max(ends) - min(starts)).total_seconds() if starts and ends else None
    return {"calls": len(records), "cost": cost, "tokens": tokens, "partial": partial,
            "seconds": seconds}


def add(*levels):
    """The sum of several totals: calls, cost, and tokens add up; `partial` when any is.

    `seconds` is the sum of the parts' known seconds (None when none is known): the time spent
    in them, not the wall time spanning them, since parts may be far apart."""
    out = {"calls": 0, "cost": 0.0, "tokens": _empty_tokens(), "partial": False, "seconds": None}
    for t in levels:
        out["calls"] += t["calls"]
        out["cost"] += t["cost"]
        for k in out["tokens"]:
            out["tokens"][k] += t["tokens"][k]
        out["partial"] = out["partial"] or t["partial"]
        if t.get("seconds") is not None:
            out["seconds"] = (out["seconds"] or 0) + t["seconds"]
    return out


def loop_extras(level, achieved):
    """`{cache_hit_rate, cost_per_achieved}` of a loop's totals: cache reads over all input
    tokens, and cost over milestones achieved (None when there is nothing to divide by)."""
    t = level["tokens"]
    read = t["input"] + t["cache_creation"] + t["cache_read"]
    return {"cache_hit_rate": t["cache_read"] / read if read else None,
            "cost_per_achieved": level["cost"] / achieved if achieved else None}


def _steps(calls):
    """A trial's calls grouped by step, in the order the calls ran: `[{step, totals, calls}]`."""
    steps = []
    for r in sorted(calls, key=lambda r: r.get("seq") or 0):
        name = r.get("step") or "?"
        if not steps or steps[-1]["step"] != name:
            steps.append({"step": name, "records": []})
        steps[-1]["records"].append(r)
    return [{"step": s["step"], "totals": totals(s["records"]),
             "calls": [r.get("seq") for r in s["records"]]} for s in steps]


def collect_loop(ws, loop):
    """Everything the page shows about one loop, or None if the loop never started."""
    loop_dir = ws.loop_dir(loop)
    state_dir = os.path.join(loop_dir, "state")
    run = state.read_json(os.path.join(state_dir, "run.json"))
    if run is None:
        return None
    plan = state.read_json(os.path.join(state_dir, "plan.json")) or {}
    invocations = state.read_jsonl(os.path.join(state_dir, "invocations.jsonl"))
    events = state.read_jsonl(os.path.join(state_dir, "events.jsonl"))
    questions = render.load_questions(loop_dir)

    by_milestone = {}
    for rec in invocations:
        by_milestone.setdefault(rec.get("milestone_id"), []).append(rec)

    milestones = []
    for m in plan.get("milestones", []):
        mid = m["id"]
        ms = (run.get("milestones") or {}).get(mid, {})
        trials = []
        summaries = ms.get("trials", [])
        for k, summary in enumerate(summaries):
            n = summary["n"]
            trial_dir = os.path.join(state_dir, "milestones", mid, "trials", str(n))
            # A voided trial keeps its number, so its re-run shares it, and its folder: the files
            # there are the last one's, and calls are told apart by when they ran.
            latest = all(later["n"] != n for later in summaries[k + 1:])
            shared = sum(1 for other in summaries if other["n"] == n) > 1
            doc = (state.read_json(os.path.join(trial_dir, "trial.json")) or {}) if latest else {}
            calls = [r for r in by_milestone.get(mid, []) if r.get("trial") == n
                     and (not shared or _within(r, summary))]
            attempt = sum(1 for earlier in summaries[:k] if earlier["n"] == n) + 1
            trials.append({
                # `key` names the trial in addresses: `n`, or `n.k` for an earlier attempt of
                # number n that was voided and re-run under the same number
                "key": str(n) if latest else f"{n}.{attempt}", "attempt": attempt,
                "n": n, "kind": doc.get("kind") or ("implement" if n == 1 else "fix"),
                "status": summary["status"], "reason": summary.get("reason"),
                "detail": (doc.get("failure") or {}).get("detail"),
                "started_at": summary.get("started_at"), "ended_at": summary.get("ended_at"),
                "seconds": _seconds(summary.get("started_at"), summary.get("ended_at")),
                "cost": _cost(calls), "tokens": _tokens(calls),
                "totals": totals(calls), "steps": _steps(calls),
                "sessions": [r.get("session_id") for r in calls],
                "validation": (state.read_json(os.path.join(trial_dir, "validation.json"))
                               if latest else None),
                "evidence_dir": os.path.relpath(os.path.join(trial_dir, "evidence"), ws.path),
            })
        calls = by_milestone.get(mid, [])
        milestones.append({
            "id": mid, "title": m["title"], "goal": m.get("goal"),
            "depends_on": m.get("depends_on") or [],
            "status": ms.get("status", "pending"),
            "tasks": [dict(t, status=(ms.get("tasks") or {}).get(t["id"], "pending"))
                      for t in m.get("tasks", [])],
            "criteria": m.get("acceptance_criteria", []),
            "trials": trials,
            "checks": (state.read_json(os.path.join(state_dir, "milestones", mid, "checks.json"))
                       or {}).get("checks", []),
            "cost": _cost(calls), "tokens": _tokens(calls), "calls": len(calls),
            "totals": totals(calls),
            "seconds": _seconds(ms.get("started_at"), ms.get("ended_at")),
        })

    planning_calls = by_milestone.get(None, [])
    planning = [dict(t, seconds=_seconds(t.get("started_at"), t.get("ended_at")))
                for t in (run.get("planning") or {}).get("trials", [])]
    times = [_parse_time(e.get("at")) for e in events] + \
        [_parse_time(r.get(k)) for r in invocations for k in ("started_at", "ended_at")]
    times = [t for t in times if t]
    step_records = {}
    for rec in invocations:
        step_records.setdefault(rec.get("step") or "?", []).append(rec)
    by_step = {}
    for name, records in step_records.items():
        t = totals(records)  # `calls`, `cost`, and `tokens`: the loop totals' names
        by_step[name] = {"calls": t["calls"], "cost": t["cost"], "tokens": t["tokens"]["total"],
                         "totals": t}
    counted = [t for m in milestones for t in m["trials"] if t["status"] != "void"]
    achieved = [m for m in milestones if m["status"] == "achieved"]
    loop_totals = totals(invocations)
    return {
        "loop": loop, "status": run.get("status"), "status_reason": run.get("status_reason"),
        "plan": plan, "milestones": milestones, "planning": planning,
        "planning_cost": _cost(planning_calls), "planning_tokens": _tokens(planning_calls),
        "planning_totals": totals(planning_calls),
        "totals": loop_totals, "extras": loop_extras(loop_totals, len(achieved)),
        "invocations": invocations, "events": events, "questions": questions,
        "grants": run.get("grants") or [], "approval": run.get("approval"),
        "ui_url": run.get("ui_url"), "openapi_artifact": run.get("openapi_artifact"),
        "target_dir": run.get("target_dir"),
        "inputs": run.get("inputs") or {},
        "by_step": by_step,
        "stats": {
            "milestones": len(milestones), "achieved": len(achieved),
            "trials": len(counted),
            "first_try": sum(1 for m in achieved
                             if [t["n"] for t in m["trials"] if t["status"] == "passed"] == [1]),
            "calls": len(invocations), "cost": _cost(invocations), "tokens": _tokens(invocations),
            "start": min(times).isoformat() if times else None,
            "end": max(times).isoformat() if times else None,
            "seconds": (max(times) - min(times)).total_seconds() if times else None,
        },
    }


def lock_holder(ws, loop):
    """The pid of the live process on this host holding `loop`'s lock, or None (a lock left by a
    crash, or held on another host, does not count)."""
    lock = state.read_json(os.path.join(ws.loop_dir(loop), "state", "lock"))
    if not isinstance(lock, dict) or lock.get("host") != socket.gethostname():
        return None
    try:
        pid = int(lock.get("pid"))
        os.kill(pid, 0)
    except PermissionError:
        return pid
    except (OSError, TypeError, ValueError):
        return None
    return pid


def running(ws, loop):
    """Whether a command is running `loop` now: its lock is held by a live process."""
    return lock_holder(ws, loop) is not None


def collect(ws):
    """The page's data for a workspace: its identity, each started loop the run includes (003
    FR-016b), and the run."""
    from . import orchestrator  # imported here: the orchestrator imports the engine
    loops = {loop: collect_loop(ws, loop) for loop in orchestrator.select_loops(ws.project, ws)}
    loops = {k: v for k, v in loops.items() if v}
    run = orchestrator.read_state(ws)
    large = []
    for loop in loops:
        milestones_dir = os.path.join(ws.loop_dir(loop), "state", "milestones")
        for dirpath, _, names in os.walk(milestones_dir):
            if "evidence" not in os.path.relpath(dirpath, milestones_dir).split(os.sep):
                continue
            for name in names:
                path = os.path.join(dirpath, name)
                size = os.path.getsize(path)
                if size > 1024 * 1024:
                    large.append({"path": os.path.relpath(path, ws.path), "bytes": size})
    stats = [d["stats"] for d in loops.values()]
    starts = [s["start"] for s in stats if s["start"]]
    ends = [s["end"] for s in stats if s["end"]]
    return {
        "workspace": ws.name, "generated_at": state.now_iso(),
        "requirements": ws.data.get("requirements") or {},
        "targets": ws.data.get("targets") or {}, "loops": loops, "run": run,
        "large_evidence": large,
        "running": [loop for loop in loops if running(ws, loop)],
        "totals": {
            "milestones": sum(s["milestones"] for s in stats),
            "achieved": sum(s["achieved"] for s in stats),
            "trials": sum(s["trials"] for s in stats),
            "first_try": sum(s["first_try"] for s in stats),
            "calls": sum(s["calls"] for s in stats),
            "cost": sum(s["cost"] for s in stats),
            "tokens": sum(sum(s["tokens"].values()) for s in stats),
            "seconds": _seconds(min(starts), max(ends)) if starts and ends else None,
            "usage": add(*(d["totals"] for d in loops.values())),
        },
    }


# --- view data for the API (specs/005-dashboard-redesign contracts/api.md) --------------------------

class NotFound(LookupError):
    """An API path that names no such loop, milestone, trial, call, or file (a 404)."""


class Context:
    """What the API's answers for one version of a workspace share, each worked out once when
    first needed: the collected data, the file listing, and the redactor. The server keeps one
    per workspace version (serve.py); every builder is `builder(ctx, **path parameters) -> dict`.

    `workspaces` are the names the page can switch to (served); `version` is the workspace version
    the answers are for (the server's digest), shown in the summary."""

    def __init__(self, ws, env=None, workspaces=None, version=None):
        self.ws = ws
        self.env = os.environ if env is None else env
        self.workspaces = list(workspaces or [ws.name])
        self.version = version
        self._lock = threading.RLock()  # `index` asks for `data` while making itself
        self._made = {}

    def _once(self, name, make):
        """`make()`, worked out by the first thread that asks; the others wait for it (the
        server answers a page's requests in parallel)."""
        with self._lock:
            if name not in self._made:
                self._made[name] = make()
            return self._made[name]

    @property
    def data(self):
        return self._once("data", lambda: collect(self.ws))

    @property
    def index(self):
        """`artifacts.file_index`: `{trees, count, by_id, inputs}`."""
        return self._once("index", lambda: artifacts.file_index(self.ws, self.data))

    @property
    def redactor(self):
        return self._once("redactor", lambda: artifacts.workspace_redactor(self.ws, self.env))


    @property
    def refs(self):
        """`{workspace-relative path: FileRef}` of the listed files."""
        def make():
            out = {}

            def walk(nodes):
                for node in nodes:
                    if node.get("file"):
                        out.setdefault(node["file"]["path"], node["file"])
                    walk(node.get("children") or [])
            walk(self.index["trees"])
            return out
        return self._once("refs", make)

    def file_ref(self, rel):
        """The FileRef of a workspace-relative path, or `{id: None, path, missing: true}`."""
        rel = os.path.normpath(rel).replace(os.sep, "/")
        return self.refs.get(rel) or {"id": None, "path": rel, "missing": True}


# Addresses in the app (assets/app/router.js ROUTES): what each item of the data links to.
ROUTES = {"overview": "", "run": "run", "loop": "loop/{loop}",
          "trial": "loop/{loop}/m/{milestone}/t/{key}", "calls": "calls",
          "call": "call/{loop}/{seq}", "files": "files", "file": "file/{id}",
          "questions": "questions", "events": "events"}


def _quote(value):
    return urllib.parse.quote(str(value), safe="!~*'()")  # as encodeURIComponent


def route(view, query=None, **params):
    """The app's address of a view: `route("trial", loop=…, milestone=…, key=…)` ->
    `#/loop/…/m/…/t/…`; `query` adds `?k=v`."""
    path = ROUTES[view].format(**{k: _quote(v) for k, v in params.items()})
    q = "&".join(f"{_quote(k)}={_quote(v)}" for k, v in (query or {}).items()
                 if v not in (None, ""))
    return "#/" + path + (f"?{q}" if q else "")


def next_action(loop, d):
    """What the developer does next about a loop: `{text, route}` or None. In `text`, commands and
    paths are between backticks; `route` is where the page shows what to look at."""
    status = d["status"]
    reason = d["status_reason"] or {}
    code = reason.get("code")
    if code == "interrupted":
        return None  # the reason's message says what it cost and what to run
    if status == "awaiting-approval":
        return {"text": f"Review `{loop}/outputs/`, answer `open-questions.md` (an empty answer "
                        f"accepts Claude's suggestion), then `devloops approve` or "
                        f"`devloops replan`.", "route": route("loop", loop=loop)}
    mid = reason.get("milestone_id")
    if status == "stopped-on-failure" and code == "needs-input":
        return {"text": f"Answer the new questions in `open-questions.md` (an empty answer accepts "
                        f"Claude's suggestion), then `devloops retry --milestone {mid} "
                        f"--reason \"…\"`.", "route": route("questions")}
    if status == "stopped-on-failure" and code in ("trials-exhausted",):
        trials = next((m["trials"] for m in d["milestones"] if m["id"] == mid), [])
        return {"text": f"Read the last trial's validation and evidence, then `devloops retry "
                        f"--milestone {mid} --reason \"…\"`.",
                "route": (route("trial", loop=loop, milestone=mid, key=trials[-1]["key"])
                          if trials else route("loop", loop=loop))}
    if status == "stopped-on-service-error":
        return {"text": "Fix the cause (log in, wait out a rate limit), then `devloops run`.",
                "route": None}
    if status in ("planning", "implementing"):
        return {"text": "Run `devloops run` to continue.", "route": None}
    return None


TONE_ORDER = {"critical": 0, "warning": 1, "info": 2}


def attention_items(data, file_route=None, records=False):
    """What a reader should look at first, most urgent first: `[{kind, tone, loop, message,
    route, ...}]` (specs/005 data-model AttentionItem). `file_route(rel)` links a file.

    Kinds: `loop` (stopped, paused, or interrupted; `status`, `reason`, `action`),
    `failing-criteria` (on a milestone's latest trial; `milestone`, `trial`, `criteria`),
    `passed-after` (a milestone achieved after failed or voided trials; `failed`, `voided`,
    `reasons`), `auto-accepted`, `unanswered`, and `suggested` questions (`questions`, while the
    loop is not done for the last two), `failed-call` (`call`, `step`, `failure`), and
    `large-evidence` (`files: [{path, bytes, route}]`, over 1 MB). With `records`, a failed call
    also carries its invocation `record`."""
    items = []
    for loop, d in data["loops"].items():
        status = d["status"]
        reason = d["status_reason"] or {}
        if status.startswith("stopped") or status == "awaiting-approval" \
                or reason.get("code") == "interrupted":
            label = RUN_STATUS.get(status, (status,))[0]
            items.append({"kind": "loop", "tone": "critical" if status.startswith("stopped")
                          else "warning", "loop": loop, "status": status,
                          "reason": reason.get("message") or "",
                          "message": f"{loop} is {label.lower()}" + (
                              f": {reason['message']}" if reason.get("message") else ""),
                          "action": next_action(loop, d), "route": route("loop", loop=loop)})
        for m in d["milestones"]:
            last = m["trials"][-1] if m["trials"] else None
            failing = [c["criterion_id"] for c in ((last or {}).get("validation") or {})
                       .get("criteria", []) if not c.get("passed")]
            if failing and m["status"] != "achieved":
                items.append({"kind": "failing-criteria", "tone": "critical", "loop": loop,
                              "milestone": m["id"], "trial": last["key"], "criteria": failing,
                              "message": f"{loop} {m['id']}: {', '.join(failing)} failing on "
                                         f"trial {last['n']}",
                              "route": route("trial", loop=loop, milestone=m["id"],
                                             key=last["key"])})
            bad = [t for t in m["trials"] if t["status"] in ("failed", "void")]
            if m["status"] == "achieved" and bad:
                failed = sum(1 for t in bad if t["status"] == "failed")
                voided = len(bad) - failed
                kinds = ", ".join(f"{n} {word}" for n, word in ((failed, "failed"),
                                                                (voided, "voided")) if n)
                reasons = sorted({t["reason"] for t in bad if t.get("reason")})
                items.append({"kind": "passed-after", "tone": "info", "loop": loop,
                              "milestone": m["id"], "failed": failed, "voided": voided,
                              "reasons": reasons,
                              "message": f"{loop} {m['id']} passed after {kinds} trial(s)"
                                         + (f" ({', '.join(reasons)})" if reasons else ""),
                              "route": route("loop", {"m": m["id"]}, loop=loop)})
        sources = {qid: question_answer(d, qid)[1][1] for qid in question_ids(d)}
        auto = [qid for qid, src in sources.items()
                if src == "accepted" and "automatically" in d["questions"][qid]["source"]]
        groups = [("auto-accepted", "warning", auto,
                   "suggested answer(s) accepted automatically", "review them like assumptions")]
        if status != "completed":
            groups += [("unanswered", "warning",
                        [qid for qid, src in sources.items() if src is None],
                        "unanswered question(s)", ""),
                       ("suggested", "info",
                        [qid for qid, src in sources.items() if src == "suggested"],
                        "suggested answer(s) not yet accepted",
                        "an empty answer accepts the suggestion")]
        for kind, tone_, ids, what, note in groups:
            if ids:
                items.append({"kind": kind, "tone": tone_, "loop": loop, "questions": ids,
                              "what": what, "note": note,
                              "message": f"{loop}: {len(ids)} {what} ({', '.join(ids)})"
                                         + (f"; {note}" if note else ""),
                              "route": route("questions")})
        for r in d["invocations"]:
            failure = r.get("failure_class")
            if failure not in (None, "none"):
                items.append({"kind": "failed-call", "tone": "warning", "loop": loop,
                              "call": r.get("seq"), "step": r.get("step"), "failure": failure,
                              "message": f"{loop} call #{r.get('seq')} {r.get('step')} failed "
                                         f"({failure})",
                              "route": route("call", loop=loop, seq=r.get("seq")),
                              **({"record": r} if records else {})})
    if data["large_evidence"]:
        files = [dict(i, route=file_route(i["path"]) if file_route else None)
                 for i in data["large_evidence"]]
        items.append({"kind": "large-evidence", "tone": "warning", "files": files,
                      "message": "Evidence files over 1 MB, the likeliest place for a secret to "
                                 "hide; review before committing",
                      "route": route("files")})
    return sorted(items, key=lambda item: TONE_ORDER[item["tone"]])


def _trial_summary(loop, mid, t):
    return {"key": t["key"], "n": t["n"], "attempt": t["attempt"], "kind": t["kind"],
            "status": t["status"], "reason": t["reason"], "detail": t["detail"],
            "started_at": t["started_at"], "ended_at": t["ended_at"], "seconds": t["seconds"],
            "totals": t["totals"], "route": route("trial", loop=loop, milestone=mid, key=t["key"])}


def _card(loop, d):
    s = d["stats"]
    return {"loop": loop, "status": d["status"], "status_reason": d["status_reason"],
            "next_action": next_action(loop, d),
            "milestones": {"total": s["milestones"], "achieved": s["achieved"]},
            "trials": s["trials"], "first_try": s["first_try"], "seconds": s["seconds"],
            "totals": d["totals"], "route": route("loop", loop=loop)}


def summary(ctx):
    """`api/summary` (data-model Workspace summary): the workspace's status and totals, a card per
    loop, what needs attention, the run, the charts' rows, and the counts of the navigation. It
    does not list the files (the overview must open fast in a large workspace, SC-001)."""
    data = ctx.data
    t = data["totals"]

    def file_route(rel):  # the explorer filtered to the file: listing every file takes long
        return route("files", {"q": rel.replace(os.sep, "/")})
    timeline_rows, milestone_rows, steps = [], [], {}
    for loop, d in data["loops"].items():
        timeline_rows.append({"label": f"{loop} · Planning", "trials": [
            dict(tr, label=f"Planning trial {tr['n']} ({tr.get('kind')})", route=None)
            for tr in d["planning"]]})
        milestone_rows.append({"loop": loop, "id": None, "title": "Planning",
                               "totals": d["planning_totals"], "trials": len(d["planning"])})
        for m in d["milestones"]:
            timeline_rows.append({"label": f"{loop} · {m['id']}", "trials": [
                dict(_trial_summary(loop, m["id"], tr),
                     label=f"{m['id']} trial {tr['n']} ({tr['kind']})") for tr in m["trials"]]})
            milestone_rows.append({"loop": loop, "id": m["id"], "title": m["title"],
                                   "totals": m["totals"], "trials": len(m["trials"]),
                                   "route": route("loop", {"m": m["id"]}, loop=loop)})
        for name, step in d["by_step"].items():
            steps.setdefault(name, []).append(step["totals"])
    return {
        "workspace": data["workspace"], "generated_at": data["generated_at"],
        "version": ctx.version, "requirements": data["requirements"], "targets": data["targets"],
        "status": _overall_status(data),
        "totals": dict(t["usage"], milestones=t["milestones"], achieved=t["achieved"],
                       trials=t["trials"], first_try=t["first_try"], elapsed=t["seconds"]),
        "loops": [_card(loop, d) for loop, d in data["loops"].items()],
        "run": data["run"], "running": data["running"],
        "attention": attention_items(data, file_route),
        "large_evidence": data["large_evidence"],
        "workspaces": ctx.workspaces,
        "timeline": timeline_rows, "cost_by_milestone": milestone_rows,
        "by_step": sorted(({"step": name, "totals": add(*levels)} for name, levels in steps.items()),
                          key=lambda row: -row["totals"]["cost"]),
        "counts": {"calls": t["calls"],
                   "questions": sum(len(question_ids(d)) for d in data["loops"].values()),
                   "assumptions": sum(len((d["plan"] or {}).get("assumptions") or [])
                                      for d in data["loops"].values()),
                   "events": sum(len(d["events"]) for d in data["loops"].values())},
    }


def _loop_data(ctx, loop):
    d = ctx.data["loops"].get(loop)
    if d is None:
        raise NotFound(f"no loop {loop!r} in this workspace")
    return d


def loop(ctx, loop):  # noqa: F811 - the builder of api/loops/<loop>; `loop` is its parameter
    """`api/loops/<loop>` (data-model Loop, FR-020–FR-020e): status, next action, approval,
    totals with their breakdown, milestones in plan order with their goal, dependencies, criteria
    (each from the milestone's `criteria_trial`; a failed one links to that trial), tasks, and
    trials, the steps (StepRow) with the planning attempts, what each plan id says (`refs`), the
    open questions' counts, and the outputs. The plan view was merged into it (FR-020)."""
    d = _loop_data(ctx, loop)
    milestones = []
    for m in d["milestones"]:
        last = criteria_trial(m)
        results = {c.get("criterion_id"): c for c in ((last or {}).get("validation") or {})
                   .get("criteria") or []}
        criteria = []
        for c in m["criteria"]:
            r = results.get(c["id"])
            state_ = _criterion_state(last, c["id"])
            evidence = [ctx.file_ref(os.path.join(os.path.dirname(last["evidence_dir"]), item))
                        for item in (r or {}).get("evidence") or []] if last else []
            criteria.append(dict({"id": c["id"], "text": c.get("text", ""),
                                  "requirement_refs": c.get("requirement_refs") or [],
                                  "result": {"passing": "passed", "failing": "failed"}.get(state_),
                                  "observed": (r or {}).get("observed"), "evidence": evidence},
                                 **({"trial_route": route("trial", loop=loop, milestone=m["id"],
                                                          key=last["key"])}
                                    if state_ == "failing" else {})))
        milestones.append({
            "id": m["id"], "title": m["title"], "goal": m["goal"], "status": m["status"],
            "depends_on": m["depends_on"], "criteria": criteria,
            "tasks": [{"id": t["id"], "title": t.get("title", ""),
                       "description": t.get("description", ""),
                       "requirement_refs": t.get("requirement_refs") or [],
                       "status": t["status"]} for t in m["tasks"]],
            "criteria_trial": last["key"] if last else None,
            "trials": [_trial_summary(loop, m["id"], t) for t in m["trials"]],
            "totals": m["totals"], "seconds": m["seconds"],
            "route": route("loop", {"m": m["id"]}, loop=loop)})
    outputs = [(f"{loop}/progress.md", "Progress"),
               (f"{loop}/outputs/plan-summary.md", "Plan summary"),
               (f"{loop}/outputs/final-report.md", "Final report")]
    if d["openapi_artifact"]:
        outputs.append((f"{loop}/{d['openapi_artifact']['path']}", "OpenAPI document"))
    plan = d["plan"] or {}
    open_questions = _loop_questions(loop, d)
    return {
        "loop": loop, "status": d["status"], "status_reason": d["status_reason"],
        "next_action": next_action(loop, d), "approval": _approval(ctx, d), "grants": d["grants"],
        "inputs": d["inputs"], "ui_url": d["ui_url"], "openapi_artifact": d["openapi_artifact"],
        "target_dir": d["target_dir"], "stack": plan.get("stack"), "runtime": plan.get("runtime"),
        "totals": dict(d["totals"], **d["extras"]),
        "stats": {k: d["stats"][k] for k in ("milestones", "achieved", "trials", "first_try",
                                              "calls", "seconds")},
        "milestones": milestones,
        "steps": step_rows(d, loop),
        "refs": plan_refs(d),
        "questions": {"open": len(open_questions),
                      "unanswered": sum(1 for q in open_questions
                                        if q["status"] not in ("developer", "accepted")),
                      "assumptions": len(plan.get("assumptions") or []),
                      "route": route("questions", {"loop": loop})},
        "outputs": [dict(ref, label=label) for ref, label in
                    ((ctx.file_ref(path), label) for path, label in outputs)
                    if not ref.get("missing")],
    }


def _approval(ctx, d):
    """`{status: "waiting", commands}` while the plan waits (approve and replan, with
    `--workspace` when the workspace is not the default), `{status: "approved", approved_at,
    action}` once approved, else `{status: "none"}`."""
    if d["status"] == "awaiting-approval":
        flag = workspace_flag(ctx.ws)
        return {"status": "waiting",
                "commands": [f"devloops approve{flag}", f"devloops replan{flag}"]}
    if d["approval"]:
        return {"status": "approved", "approved_at": d["approval"].get("approved_at"),
                "action": d["approval"].get("action")}
    return {"status": "none"}


def step_rows(d, loop):
    """The loop's Steps card (data-model StepRow, FR-020c): `[{step, calls, started_at, seconds,
    totals, share}]`, ordered by `started_at`, the start of the row's first call (a row without a
    known start last, then in the driver's step order, `claude.STEPS`, and an unknown step by
    name). Each planning attempt (plan or replan) is a row of its own, with `attempt` (its number
    among its step's attempts, None when the step has one), `status`, `reason`, `detail`, and
    `route` (its call); every other step is one row. `seconds` sums the calls' durations (None
    when none is known); `share` is the row's cost over the loop's (None when the loop's cost is
    not known)."""
    loop_cost = d["totals"]["cost"]

    def row(name, records):
        t = totals(records)
        known = [r["duration_ms"] for r in records if isinstance(r.get("duration_ms"), (int, float))]
        starts = [r["started_at"] for r in records if isinstance(r.get("started_at"), str)]
        return {"step": name, "calls": len(records),
                "started_at": min(starts) if starts else None,
                "seconds": sum(known) / 1000 if known else None, "totals": t,
                "share": t["cost"] / loop_cost if loop_cost else None}

    rows, claimed = [], set()
    attempts = [a for a in _planning_attempts(d) if a["calls"]]
    per_step = {}
    for a in attempts:
        name = a["calls"][0].get("step") or "?"
        per_step[name] = per_step.get(name, 0) + 1
    seen = {}
    for a in attempts:
        name = a["calls"][0].get("step") or "?"
        seen[name] = seen.get(name, 0) + 1
        claimed.update(id(r) for r in a["calls"])
        first = min(a["calls"], key=lambda r: r.get("seq") or 0)
        rows.append({**row(name, a["calls"]),
                     "attempt": seen[name] if per_step[name] > 1 else None,
                     "status": a["status"], "reason": a["reason"], "detail": a["detail"],
                     "route": route("call", loop=loop, seq=first.get("seq"))})
    by_step = {}
    for r in d["invocations"]:
        if id(r) not in claimed:
            by_step.setdefault(r.get("step") or "?", []).append(r)
    rows.extend(row(name, records) for name, records in by_step.items())
    order = list(claude.STEPS)
    rows.sort(key=lambda r: (r["started_at"] is None, r["started_at"] or "",
                             order.index(r["step"]) if r["step"] in order else len(order),
                             r["step"]))
    return rows


def plan_refs(d):
    """What each id of a loop's plan says (FR-020d): every `requirements_inventory` ref → its
    summary, every task id → its title, every criterion id → its text."""
    plan, refs = d["plan"] or {}, {}
    for item in plan.get("requirements_inventory") or []:
        if item.get("ref") and item.get("summary"):
            refs[item["ref"]] = item["summary"]
    for m in plan.get("milestones") or []:
        for t in m.get("tasks") or []:
            if t.get("id") and t.get("title"):
                refs[t["id"]] = t["title"]
        for c in m.get("acceptance_criteria") or []:
            if c.get("id") and c.get("text"):
                refs[c["id"]] = c["text"]
    return refs


def workspace_flag(ws):
    """` --workspace <name or path>` for a command run on `ws`, or "" for the default workspace."""
    project = getattr(ws, "project", None)
    if project is None or ws.name == project.default_workspace:
        return ""
    elsewhere = os.path.dirname(os.path.realpath(ws.path)) != os.path.realpath(project.workspaces_dir)
    return f" --workspace {shlex.quote(ws.path if elsewhere else ws.name)}"


def criteria_trial(m):
    """The trial a milestone's criteria are shown from (plan and loop views): its latest counted
    (not voided) trial with a validation result, so a trial still running, or one that failed
    before validating, leaves the last result shown; None when no trial validated."""
    return next((t for t in reversed(m["trials"])
                 if t["status"] != "void" and t["validation"] is not None), None)


def _criterion_state(trial, criterion_id):
    """`passing`, `failing`, or `unchecked` of a criterion on a trial: unchecked without a trial
    or a validation result; failing when the result has no entry for it (FR-068)."""
    if trial is None or trial["validation"] is None:
        return "unchecked"
    result = next((c for c in trial["validation"].get("criteria") or []
                   if c.get("criterion_id") == criterion_id), None)
    return "passing" if result and result.get("passed") else "failing"


def _planning_attempts(d):
    """The loop's planning attempts, each a planning trial with its calls (FR-020c): `key` is `n`,
    or `n.k` for an earlier attempt voided and re-run under the same number (as milestone trials);
    `reason` and `detail` from the trial's failure; `calls`, the planning calls of that trial."""
    calls = [r for r in d["invocations"] if r.get("milestone_id") is None]
    trials, out = d.get("planning") or [], []
    for k, t in enumerate(trials):
        n = t.get("n")
        latest = all(later.get("n") != n for later in trials[k + 1:])
        shared = sum(1 for other in trials if other.get("n") == n) > 1
        attempt = sum(1 for earlier in trials[:k] if earlier.get("n") == n) + 1
        mine = [r for r in calls if r.get("trial") == n and (not shared or _within(r, t))]
        failure = t.get("failure") or {}
        out.append({"key": str(n) if latest else f"{n}.{attempt}", "n": n, "attempt": attempt,
                    "kind": t.get("kind"), "status": t.get("status"),
                    "reason": failure.get("reason"), "detail": failure.get("detail"),
                    "started_at": t.get("started_at"), "ended_at": t.get("ended_at"),
                    "seconds": t.get("seconds"), "calls": mine})
    return out


_PARSED = {}  # conversation path -> ((size, mtime), artifacts.parse_conversation result)
_PARSED_KEEP = 64
_PARSED_LOCK = threading.Lock()  # the server answers requests in parallel


def parsed_conversation(path, redactor):
    """`artifacts.parse_conversation` of a copied conversation, kept per path while its size and
    modification time stay the same (the newest _PARSED_KEEP); None when it cannot be read."""
    try:
        st = os.stat(path)
        stamp = (st.st_size, st.st_mtime_ns)
        with _PARSED_LOCK:
            hit = _PARSED.get(path)
        if hit and hit[0] == stamp:
            return hit[1]
        with open(path, encoding="utf-8", errors="replace") as f:
            result = artifacts.parse_conversation(f.read(), redactor)
    except OSError:
        return None
    with _PARSED_LOCK:
        _PARSED.pop(path, None)
        _PARSED[path] = (stamp, result)
        while len(_PARSED) > _PARSED_KEEP:
            _PARSED.pop(next(iter(_PARSED)))
    return result


def _why(t, criteria_text, ref):
    """A trial's reasons for not passing (FR-019, data-model Reason), in the order checks,
    criteria, contract, unit tests, boundary, voided or interrupted; `ref(rel)` is the FileRef of a
    path relative to the trial's folder. A failed trial with none of these (its step's call
    failed, say) gets one `failure` reason with the trial's own reason and detail."""
    if t["status"] in ("passed", "in-progress"):
        return []
    v = t["validation"] or {}
    why = []
    for c in v.get("checks") or []:
        if not c.get("passed"):
            resp = c.get("response") or {}
            why.append({"kind": "check", "check_id": c.get("check_id"), "command": c.get("command"),
                        "status": resp.get("status"), "failures": c.get("failures") or [],
                        "evidence": [ref(resp[k]) for k in ("body_path", "headers_path")
                                     if resp.get(k)]})
    if t["validation"] is not None:
        results = {c.get("criterion_id"): c for c in v.get("criteria") or []}
        ids = list(criteria_text) + [cid for cid in results if cid not in criteria_text]
        for cid in ids:
            c = results.get(cid)
            if c is None or not c.get("passed"):
                c = c or {"observed": "no result was recorded for this criterion"}
                why.append({"kind": "criterion", "criterion_id": cid,
                            "text": criteria_text.get(cid, ""), "steps": c.get("steps") or [],
                            "observed": c.get("observed") or "",
                            "evidence": [ref(e) for e in c.get("evidence") or []]})
    contract = v.get("contract") or {}
    if contract and not contract.get("passed", True):
        why.append({"kind": "contract", "problem": contract.get("problem"),
                    "unmatched_operations": contract.get("unmatched_operations") or [],
                    "network_requests": v.get("network_requests") or []})
    unit = v.get("unit_tests") or {}
    if unit.get("enabled") and unit.get("exit_code") != 0:
        why.append({"kind": "unit-tests", "command": unit.get("command"),
                    "exit_code": unit.get("exit_code"),
                    "log": ref(unit["log_path"]) if unit.get("log_path") else None})
    boundary = v.get("boundary") or {}
    if boundary and not boundary.get("passed", True):
        why.append({"kind": "boundary", "violations": boundary.get("violations") or []})
    message = ": ".join(x for x in (t.get("reason"), t.get("detail")) if x)
    if t["status"] == "void":
        why.append({"kind": "voided", "message": message or "voided"})
    elif t.get("reason") == "interrupted":
        why.append({"kind": "interrupted", "message": t.get("detail") or "interrupted"})
    elif not why and t["status"] == "failed":
        why.append({"kind": "failure", "reason": t.get("reason"), "detail": t.get("detail")})
    return why


def _in_target(path, target):
    """A changed file's path relative to the loop's target when it lies inside it, else as is."""
    root = os.path.normpath(target).rstrip(os.sep) if target else None
    if root and os.path.isabs(path) and os.path.normpath(path).startswith(root + os.sep):
        return os.path.normpath(path)[len(root) + 1:].replace(os.sep, "/")
    return path


def trial(ctx, loop, milestone, key):  # noqa: F811 - the builder; `loop` is its parameter
    """`api/loops/<loop>/milestones/<id>/trials/<key>` (data-model Trial, FR-018, FR-019): the
    trial's outcome, its steps with their calls, its validation result, why it did not pass, the
    files in its folder (FileRefs with `size` and `kind`, FR-018b), and the files its calls
    changed (`[{path, step, seq, tool, call_route, block, added, removed}]`, each path's last
    change, with the lines all its calls added and removed; `seq` lets the view ask for the call
    when a change is opened, FR-018d). An earlier attempt voided under the same number (`n.k`)
    has no files of its own: the folder holds the latest attempt's. `refs` (what the plan's ids
    say, FR-020d) and `target_dir` spare the view the loop's whole answer."""
    d = _loop_data(ctx, loop)
    m = next((m for m in d["milestones"] if m["id"] == milestone), None)
    if m is None:
        raise NotFound(f"no milestone {milestone!r} in {loop}")
    t = next((t for t in m["trials"] if t["key"] == key), None)
    if t is None:
        raise NotFound(f"no trial {key!r} of {milestone}")
    folder = os.path.dirname(t["evidence_dir"]).replace(os.sep, "/")
    latest = "." not in t["key"]

    def ref(rel):
        return ctx.file_ref(f"{folder}/{rel}")
    by_seq = {r.get("seq"): r for r in d["invocations"]}
    steps, changed = [], {}
    loop_dir, target = ctx.ws.loop_dir(loop), d["target_dir"]
    for s in t["steps"]:
        records = [by_seq[q] for q in s["calls"] if q in by_seq]
        steps.append({"step": s["step"], "totals": s["totals"],
                      "calls": [call_ref(loop, r) for r in records]})
        for r in records:
            if not r.get("conversation_path"):
                continue
            parsed = parsed_conversation(os.path.join(loop_dir, r["conversation_path"]),
                                         ctx.redactor)
            for f in (parsed or {}).get("files_changed") or []:
                path = _in_target(f["path"], target)
                before = changed.pop(path, None) or {"added": 0, "removed": 0}
                changed[path] = {"path": path, "step": r.get("step"), "seq": r.get("seq"),
                                 "tool": f["tool"], "block": f["block"],
                                 "added": before["added"] + f["added"],
                                 "removed": before["removed"] + f["removed"],
                                 "call_route": route("call", {"at": f["block"]}, loop=loop,
                                                     seq=r.get("seq"))}
    criteria_text = {c["id"]: c.get("text", "") for c in m["criteria"]}
    evidence = sorted((dict(r, size=r.get("size", 0), kind=r.get("kind") or "missing")
                       for path, r in ctx.refs.items() if path.startswith(folder + "/")),
                      key=lambda r: r["path"]) if latest else []
    return {"loop": loop, "milestone": milestone, "title": m["title"], "key": t["key"],
            "n": t["n"], "attempt": t["attempt"], "kind": t["kind"], "status": t["status"],
            "reason": t["reason"], "detail": t["detail"], "started_at": t["started_at"],
            "ended_at": t["ended_at"], "seconds": t["seconds"], "totals": t["totals"],
            "steps": steps, "validation": t["validation"], "why": _why(t, criteria_text, ref),
            "evidence": evidence, "files_changed": list(changed.values()),
            "refs": plan_refs(d), "target_dir": target,
            "routes": {"loop": route("loop", {"m": milestone}, loop=loop),
                       "trials": [{"key": x["key"], "status": x["status"],
                                   "route": route("trial", loop=loop, milestone=milestone,
                                                  key=x["key"])} for x in m["trials"]]}}


def _model_name(r):
    # A call from before models were recorded has no `model` key at all.
    return r.get("model") or ("(Claude Code default)" if "model" in r else "(not recorded)")


def call_ref(loop, r):
    """data-model CallRef of one invocation record."""
    if r.get("conversation_path"):
        conversation = "copied"
    elif r.get("conversation") == "unavailable":
        conversation = "unavailable"
    else:
        conversation = "history"
    return {"loop": loop, "seq": r.get("seq"), "step": r.get("step"),
            "milestone_id": r.get("milestone_id"), "trial": r.get("trial"),
            "model": r.get("model"), "session_id": r.get("session_id"),
            "started_at": r.get("started_at"), "duration_ms": r.get("duration_ms"),
            "totals": totals([r]), "failure_class": r.get("failure_class"),
            # how a failed call ended, for its Result (FR-018b)
            "timed_out": r.get("timed_out"), "is_error": r.get("is_error"),
            "subtype": r.get("subtype"), "api_error_status": r.get("api_error_status"),
            "conversation": conversation, "route": route("call", loop=loop, seq=r.get("seq"))}


def _trial_of(d, r):
    """The key of the trial a milestone call ran in, or None."""
    m = next((m for m in d["milestones"] if m["id"] == r.get("milestone_id")), None)
    same = [t for t in (m or {}).get("trials", []) if t["n"] == r.get("trial")]
    inside = [t for t in same if _within(r, t)]
    return (inside or same or [{}])[-1].get("key")


def call(ctx, loop, seq):
    """`api/calls/<loop>/<seq>` (data-model Call, FR-021): the call's record with its prompt and
    settings files and where each prompt part came from, and its conversation: every record
    parsed and redacted, the records holding a failed tool result (`errors`), and the files it
    changed (`files_changed`, each path's last change, relative to the target when inside it).
    `conversation` says where the transcript was read from: `copied`, `history`, or
    `unavailable` (with `unavailable_reason`, and no records). `refs` is what the plan's ids say
    (FR-020d), for the call's answer."""
    d = _loop_data(ctx, loop)
    r = next((r for r in d["invocations"] if str(r.get("seq")) == str(seq)), None)
    if r is None:
        raise NotFound(f"no call {seq} in {loop}")
    out = call_ref(loop, r)
    prompt = r.get("prompt_path")
    settings = prompt[:-len(".md")] + ".settings.json" if prompt and prompt.endswith(".md") else None
    key = _trial_of(d, r)
    out.update({
        "ended_at": r.get("ended_at"), "num_turns": r.get("num_turns"),
        "is_error": r.get("is_error"), "subtype": r.get("subtype"),
        "api_error_status": r.get("api_error_status"), "timed_out": r.get("timed_out"),
        "permission_denials": r.get("permission_denials") or [],
        "prompt": ctx.file_ref(f"{loop}/{prompt}") if prompt else None,
        "settings": ctx.file_ref(f"{loop}/{settings}") if settings else None,
        "prompt_sources": r.get("prompt_sources") or [],
        "refs": plan_refs(d),
        "routes": {"loop": route("loop", loop=loop),
                   "trial": route("trial", loop=loop, milestone=r["milestone_id"], key=key)
                   if key else None}})
    parsed, reason = None, None
    if r.get("conversation_path"):
        path = os.path.join(ctx.ws.loop_dir(loop), r["conversation_path"])
        parsed = parsed_conversation(path, ctx.redactor)
        reason = None if parsed else f"missing: {os.path.relpath(path, ctx.ws.path)}"
    else:
        text, _, reason = artifacts.read_conversation(ctx.ws, loop, r, d["target_dir"], ctx.env)
        parsed = artifacts.parse_conversation(text, ctx.redactor) if text is not None else None
    if parsed is None:
        out.update(conversation="unavailable", unavailable_reason=reason, records=[], errors=[],
                   files_changed=[])
        return out
    out.update(records=parsed["records"], errors=parsed["errors"],
               files_changed=[dict(f, path=_in_target(f["path"], d["target_dir"]))
                              for f in parsed["files_changed"]])
    return out


def calls(ctx):
    """`api/calls`: `{calls: [CallRef], by_model: [{model, calls, cost}], loops, steps}`, calls by
    loop then sequence, models by cost; `steps` is the driver's step order (`claude.STEPS`), which
    the view's step chips follow, as the loop view's Steps card does (FR-020i)."""
    rows, by_model = [], {}
    for loop, d in ctx.data["loops"].items():
        for r in sorted(d["invocations"], key=lambda r: r.get("seq") or 0):
            rows.append(call_ref(loop, r))
            entry = by_model.setdefault(_model_name(r), {"model": _model_name(r), "calls": 0,
                                                         "cost": 0.0})
            entry["calls"] += 1
            entry["cost"] += r.get("cost_usd") or 0
    return {"calls": rows, "loops": list(ctx.data["loops"]), "steps": list(claude.STEPS),
            "by_model": sorted(by_model.values(), key=lambda m: -m["cost"])}


def files(ctx):
    """`api/files`: `{trees, count}` (artifacts.file_index)."""
    return {"trees": ctx.index["trees"], "count": ctx.index["count"]}


def events(ctx):
    """`api/events`: every loop's events, oldest first, each with its `loop` and `n`, its place in
    that loop's events.jsonl (a search result opens `#/events?loop=<loop>&at=<n>`)."""
    found = [dict(ev, loop=loop, n=n) for loop, d in ctx.data["loops"].items()
             for n, ev in enumerate(d["events"])]
    return {"events": sorted(found, key=lambda ev: ev.get("at") or "")}


def _loop_questions(loop, d):
    """One loop's open questions as data-model Question, with their answers and where each came
    from."""
    found, planned = [], {q["id"]: q for q in (d["plan"] or {}).get("open_questions") or []}
    for qid in question_ids(d):
        question, (answer, source), q = question_answer(d, qid)
        p = planned.get(qid, {})
        found.append({"loop": loop, "id": qid, "question": question,
                      "context": q.get("context") or p.get("context") or "",
                      "affects": p.get("affects") or q.get("affects") or "",
                      "suggested_answer": q.get("suggested") or p.get("suggested_answer") or "",
                      "reason": q.get("reason") or "", "answer": answer,
                      "status": source or "none", "source": q.get("source") or ""})
    return found


def questions(ctx):
    """`api/questions`: the loops' open questions with their answers and where each came from
    (`status`: developer, accepted, suggested, or none), the planning assumptions, and what each
    loop's plan ids say (`refs`, FR-020d). The retries granted show on their milestone in the
    loop view (FR-020j)."""
    found, assumptions = [], []
    for loop, d in ctx.data["loops"].items():
        found += _loop_questions(loop, d)
        assumptions += [dict(a, loop=loop) for a in (d["plan"] or {}).get("assumptions") or []]
    return {"questions": found, "assumptions": assumptions,
            "refs": {loop: plan_refs(d) for loop, d in ctx.data["loops"].items()}}


def index(ctx):
    """`api/index` (data-model Index, FR-022): what the "go to" palette matches by name, each
    `{kind, label, detail, route}`: the views, then per loop the loop, its milestones,
    trials, and calls, then every listed file."""
    data, items = ctx.data, []

    def add(kind, label, detail, href):
        items.append({"kind": kind, "label": label, "detail": detail, "route": href})
    add("view", "Overview", "the workspace", route("overview"))
    if data["run"]:
        add("view", "Run", "the loops' order and handoff", route("run"))
    for name, label in (("calls", "Claude calls"), ("files", "Files"), ("questions", "Questions"),
                        ("events", "Events")):
        add("view", label, "", route(name))
    for loop, d in data["loops"].items():
        add("loop", loop, RUN_STATUS.get(d["status"], (d["status"],))[0], route("loop", loop=loop))
        for m in d["milestones"]:
            add("milestone", f"{m['id']} {m['title']}",
                f"{loop} · {MILESTONE_STATUS.get(m['status'], (m['status'],))[0]}",
                route("loop", {"m": m["id"]}, loop=loop))
            for t in m["trials"]:
                add("trial", f"{m['id']} trial {t['key']}",
                    f"{loop} · {t['kind']} · {TRIAL_STATUS.get(t['status'], (t['status'],))[0]}",
                    route("trial", loop=loop, milestone=m["id"], key=t["key"]))
        for r in sorted(d["invocations"], key=lambda r: r.get("seq") or 0):
            where = (f"{r['milestone_id']} trial {r.get('trial')}" if r.get("milestone_id")
                     else "planning")
            add("call", f"#{r.get('seq')} {r.get('step')}", f"{loop} · {where} · {_model_name(r)}",
                route("call", loop=loop, seq=r.get("seq")))
    for ref in sorted(ctx.refs.values(), key=lambda ref: ref["path"]):
        if not ref.get("missing"):
            add("file", ref["path"].rsplit("/", 1)[-1], ref["path"], route("file", id=ref["id"]))
    return {"items": items}


def _waiting_for(d):
    """What a stopped loop waits for from the developer: `approval`, `questions`, `retry`, or
    None."""
    reason = d["status_reason"] or {}
    if d["status"] == "awaiting-approval":
        return "approval"
    if d["status"] == "stopped-on-failure" and reason.get("code") == "needs-input":
        return "questions"
    if d["status"] == "stopped-on-failure" and reason.get("code") == "trials-exhausted":
        return "retry"  # as next_action: an invocation cap also names a milestone, but no retry
    return None


def now(ctx):
    """`api/now` (data-model Now, FR-016): the call running now, `{running: true, call,
    elapsed_seconds}`, read from a loop's `state/live.json` while a command holds that loop's
    lock; otherwise `{running: false, status, loop, next_action, waiting_for, busy}`, the loop
    being the one the overall status comes from, `busy` the loops a command runs between calls
    (validating, say; their next action is then not the developer's). Liveness is checked on
    each request: the server does not keep this answer (`now.cached`)."""
    from . import orchestrator, progress
    for loop in orchestrator.select_loops(ctx.ws.project, ctx.ws):
        doc = state.read_json(os.path.join(ctx.ws.loop_dir(loop), "state", progress.LIVE_NAME))
        # Only the lock holder's own call: a file left by a killed command is not running, even
        # while a later command holds the lock
        holder = lock_holder(ctx.ws, loop)
        if isinstance(doc, dict) and holder is not None and doc.get("pid") == holder:
            started = _parse_time(doc.get("started_at"))
            elapsed = (max(0.0, (datetime.now(timezone.utc) - started).total_seconds())
                       if started else None)
            return {"running": True, "call": doc, "elapsed_seconds": elapsed}
    data = ctx.data
    status = _overall_status(data)
    busy = [loop for loop in data["loops"] if running(ctx.ws, loop)]
    loop_ = next((loop for loop, d in data["loops"].items() if d["status"] == status), None)
    d = data["loops"].get(loop_)
    return {"running": False, "status": status, "loop": loop_, "busy": busy,
            "next_action": next_action(loop_, d) if d and not busy else None,
            "waiting_for": _waiting_for(d) if d and not busy else None}


now.cached = False


# --- questions and status ------------------------------------------------------------------------

def _overall_status(data):
    statuses = [d["status"] for d in data["loops"].values()]
    if not statuses:
        return "not-started"
    for s in ("stopped-on-service-error", "stopped-on-failure", "stopped-on-input-error",
              "awaiting-approval", "implementing", "planning"):
        if s in statuses:
            return s
    return "completed" if all(s == "completed" for s in statuses) else statuses[-1]


def question_ids(d):
    """A loop's question IDs: the plan's, then those only in open-questions.md (needs-input)."""
    planned = [q["id"] for q in d["plan"].get("open_questions") or []]
    return list(dict.fromkeys(planned + list(d["questions"])))


def question_answer(d, qid):
    """`(question, (answer, source), suggestion_reason)` of one question; see
    `render.effective_answer`. A planned question missing from the file uses the plan's text."""
    planned = {q["id"]: q for q in d["plan"].get("open_questions") or []}.get(qid, {})
    q = d["questions"].get(qid) or {
        "question": planned.get("question", ""), "answer": "", "source": "",
        "suggested": planned.get("suggested_answer", ""),
        "reason": planned.get("suggestion_reason", "")}
    return q["question"], render.effective_answer(q), q
