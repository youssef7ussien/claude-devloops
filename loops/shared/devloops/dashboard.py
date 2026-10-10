"""`workspaces/<ws>/dashboard.html`: one self-contained summary page of a workspace.

Everything is read from the workspace's state (`workspace.json`, each loop's `state/` and
`outputs/open-questions.md`, `run/state.json`); nothing is read back from the page. The
views here (overview, loops, calls, questions, events) are shared with the full dashboard and the
served one (fulldash.py, serve.py); the shell, styles, and script come from ui.py, so the page
opens offline from disk. The summary links no workspace file: files and conversations are what
`devloops dashboard` shows. State is already redacted (FR-070); every value is
HTML-escaped here.
"""
import html
import json
import os
import re
import shlex
import socket
import threading
import urllib.parse
from datetime import datetime, timezone

from . import __version__, artifacts, render, state, ui

LOOPS = ("backend-dev", "frontend-dev")
FILENAME = "dashboard.html"

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
        t = totals(records)  # `calls`, `cost`, and `tokens` are the summary page's names
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


FULL_NAME = re.compile(r"^(\d{8}T\d{6}Z)(?:-(\d+))?\.html$")


def full_dashboards_dir(ws):
    """`<dashboards_dir>/<workspace>`, where the workspace's full dashboards go (002 FR-036)."""
    return os.path.join(ws.project.dashboards_dir, ws.name)


def list_full_dashboards(ws):
    """The workspace's full dashboards, newest first: `[{name, path, link, bytes}]`.

    `link` is relative to the workspace folder, for the lightweight page. Read-only.
    """
    if getattr(ws, "project", None) is None:
        return []
    directory = full_dashboards_dir(ws)
    try:
        names = os.listdir(directory)
    except OSError:
        return []
    found = []
    for name in names:
        match = FULL_NAME.match(name)
        path = os.path.join(directory, name)
        if not match or not os.path.isfile(path):
            continue
        found.append(((match.group(1), int(match.group(2) or 1)), {
            "name": name, "path": path, "link": os.path.relpath(path, ws.path),
            "bytes": os.path.getsize(path)}))
    return [item for _, item in sorted(found, key=lambda pair: pair[0], reverse=True)]


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
        "full_dashboards": list_full_dashboards(ws),
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
ROUTES = {"overview": "", "run": "run", "loop": "loop/{loop}", "plan": "loop/{loop}/plan",
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
                        f"`devloops replan`.", "route": route("plan", loop=loop)}
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
    also carries its invocation `record` (the summary page links it)."""
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
                   "events": sum(len(d["events"]) for d in data["loops"].values())},
    }


def _loop_data(ctx, loop):
    d = ctx.data["loops"].get(loop)
    if d is None:
        raise NotFound(f"no loop {loop!r} in this workspace")
    return d


def loop(ctx, loop):  # noqa: F811 - the builder of api/loops/<loop>; `loop` is its parameter
    """`api/loops/<loop>` (data-model Loop): status, next action, totals with their breakdown,
    planning, milestones with their trials and acceptance criteria, cost by step, and outputs."""
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
            criteria.append({"id": c["id"], "text": c["text"],
                             "requirement_refs": c.get("requirement_refs") or [],
                             "result": {"passing": "passed", "failing": "failed"}.get(state_),
                             "observed": (r or {}).get("observed"), "evidence": evidence})
        milestones.append({
            "id": m["id"], "title": m["title"], "goal": m["goal"], "status": m["status"],
            "depends_on": m["depends_on"], "tasks": m["tasks"], "criteria": criteria,
            "criteria_trial": last["key"] if last else None,
            "trials": [_trial_summary(loop, m["id"], t) for t in m["trials"]],
            "totals": m["totals"], "seconds": m["seconds"]})
    outputs = [(f"{loop}/progress.md", "Progress"),
               (f"{loop}/outputs/plan-summary.md", "Plan summary"),
               (f"{loop}/outputs/final-report.md", "Final report")]
    if d["openapi_artifact"]:
        outputs.append((f"{loop}/{d['openapi_artifact']['path']}", "OpenAPI document"))
    plan = d["plan"] or {}
    return {
        "loop": loop, "status": d["status"], "status_reason": d["status_reason"],
        "next_action": next_action(loop, d), "approval": d["approval"], "grants": d["grants"],
        "inputs": d["inputs"], "ui_url": d["ui_url"], "openapi_artifact": d["openapi_artifact"],
        "target_dir": d["target_dir"], "stack": plan.get("stack"), "runtime": plan.get("runtime"),
        "totals": dict(d["totals"], **d["extras"]),
        "stats": {k: d["stats"][k] for k in ("milestones", "achieved", "trials", "first_try",
                                              "calls", "seconds")},
        "planning": {"trials": [dict(t, route=None) for t in d["planning"]],
                     "totals": d["planning_totals"]},
        "milestones": milestones,
        "by_step": {name: step["totals"] for name, step in d["by_step"].items()},
        "outputs": [dict(ref, label=label) for ref, label in
                    ((ctx.file_ref(path), label) for path, label in outputs)
                    if not ref.get("missing")],
    }


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


def plan(ctx, loop):  # noqa: F811 - the builder of api/loops/<loop>/plan
    """`api/loops/<loop>/plan` (data-model Plan, FR-020): the stored plan's milestones in plan
    order, each criterion's state from the milestone's `criteria_trial` (a failing one links to
    that trial), the open questions with their answers, the assumptions, and the approval:
    `{status: "waiting"|"approved"|"none", commands?, approved_at?, action?}`, `commands` (approve,
    replan) while the plan waits, with `--workspace` when it is not the default."""
    d = _loop_data(ctx, loop)
    p = d["plan"] or {}
    milestones = []
    for m in d["milestones"]:
        counted = [t for t in m["trials"] if t["status"] != "void"]
        last = criteria_trial(m)
        criteria = []
        for c in m["criteria"]:
            state_ = _criterion_state(last, c["id"])
            criteria.append(dict({"id": c["id"], "text": c.get("text", ""),
                                  "requirement_refs": c.get("requirement_refs") or [],
                                  "state": state_},
                                 **({"trial_route": route("trial", loop=loop, milestone=m["id"],
                                                          key=last["key"])}
                                    if state_ == "failing" else {})))
        milestones.append({
            "id": m["id"], "title": m["title"], "goal": m["goal"], "status": m["status"],
            "trials_used": len(counted), "depends_on": m["depends_on"], "criteria": criteria,
            "tasks": [{"id": t["id"], "title": t.get("title", ""),
                       "description": t.get("description", ""),
                       "requirement_refs": t.get("requirement_refs") or [],
                       "status": t["status"]} for t in m["tasks"]],
            "route": route("loop", {"m": m["id"]}, loop=loop)})
    if d["status"] == "awaiting-approval":
        flag = workspace_flag(ctx.ws)
        approval = {"status": "waiting",
                    "commands": [f"devloops approve{flag}", f"devloops replan{flag}"]}
    elif d["approval"]:
        approval = {"status": "approved", "approved_at": d["approval"].get("approved_at"),
                    "action": d["approval"].get("action")}
    else:
        approval = {"status": "none"}
    return {"loop": loop, "status": d["status"], "approval": approval, "milestones": milestones,
            "open_questions": _loop_questions(loop, d),
            "assumptions": [{"id": a.get("id"), "text": a.get("text", ""),
                             "source": a.get("source", "")} for a in p.get("assumptions") or []],
            "stack": p.get("stack"), "runtime": p.get("runtime"),
            "routes": {"loop": route("loop", loop=loop)}}


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
    files in its folder, and the files its calls changed (`[{path, step, call_route, block}]`,
    each path's last change). An earlier attempt voided under the same number (`n.k`) has no
    files of its own: the folder holds the latest attempt's."""
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
                changed.pop(path, None)
                changed[path] = {"path": path, "step": r.get("step"), "tool": f["tool"],
                                 "block": f["block"],
                                 "call_route": route("call", {"at": f["block"]}, loop=loop,
                                                     seq=r.get("seq"))}
    criteria_text = {c["id"]: c.get("text", "") for c in m["criteria"]}
    evidence = sorted((r for path, r in ctx.refs.items() if path.startswith(folder + "/")),
                      key=lambda r: r["path"]) if latest else []
    return {"loop": loop, "milestone": milestone, "title": m["title"], "key": t["key"],
            "n": t["n"], "attempt": t["attempt"], "kind": t["kind"], "status": t["status"],
            "reason": t["reason"], "detail": t["detail"], "started_at": t["started_at"],
            "ended_at": t["ended_at"], "seconds": t["seconds"], "totals": t["totals"],
            "steps": steps, "validation": t["validation"], "why": _why(t, criteria_text, ref),
            "evidence": evidence, "files_changed": list(changed.values()),
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
    `unavailable` (with `unavailable_reason`, and no records)."""
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
    """`api/calls`: `{calls: [CallRef], by_model: [{model, calls, cost}], loops}`, calls by loop
    then sequence, models by cost."""
    rows, by_model = [], {}
    for loop, d in ctx.data["loops"].items():
        for r in sorted(d["invocations"], key=lambda r: r.get("seq") or 0):
            rows.append(call_ref(loop, r))
            entry = by_model.setdefault(_model_name(r), {"model": _model_name(r), "calls": 0,
                                                         "cost": 0.0})
            entry["calls"] += 1
            entry["cost"] += r.get("cost_usd") or 0
    return {"calls": rows, "loops": list(ctx.data["loops"]),
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
    (`status`: developer, accepted, suggested, or none), the planning assumptions, and the
    retries granted."""
    found, assumptions, grants = [], [], []
    for loop, d in ctx.data["loops"].items():
        found += _loop_questions(loop, d)
        assumptions += [dict(a, loop=loop) for a in (d["plan"] or {}).get("assumptions") or []]
        grants += [dict(g, loop=loop) for g in d["grants"]]
    return {"questions": found, "assumptions": assumptions, "grants": grants}


def index(ctx):
    """`api/index` (data-model Index, FR-022): what the "go to" palette matches by name, each
    `{kind, label, detail, route}`: the views, then per loop the loop, its plan, milestones,
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
        add("view", f"{loop} plan", "milestones, criteria, and tasks", route("plan", loop=loop))
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


# --- formatting -------------------------------------------------------------------------------------

def e(value):
    return html.escape("" if value is None else str(value), quote=True)


def money(value):
    return f"${value:,.2f}" if value is not None else "–"


def number(value):
    if value is None:
        return "–"
    for limit, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if abs(value) >= limit:
            return f"{value / limit:.1f}{suffix}"
    return f"{value:,.0f}"


def duration(seconds):
    if seconds is None:
        return "–"
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, s = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {s:02d}s"
    hours, m = divmod(minutes, 60)
    return f"{hours}h {m:02d}m"


def pill(status, table):
    label, icon, tone = table.get(status, (status or "unknown", "•", "muted"))
    return f'<span class="pill tone-{tone}"><span aria-hidden="true">{icon}</span> {e(label)}</span>'


def tone(status, table):
    return table.get(status, (None, None, "muted"))[2]


def tokens_of(record):
    return sum((record.get("tokens") or {}).get(k) or 0 for k in TOKEN_KEYS)


def _path_link(relpath, text=None):
    return f'<a href="{e(relpath)}">{e(text or relpath)}</a>'


class FileLinks:
    """How a page refers to workspace files and URLs: here, links to the files on disk, which open
    in a new tab (a page opened from disk cannot read other files); images open in the viewer.

    The full dashboard (fulldash.py) substitutes links to the copies embedded in the page.
    """

    def path(self, relpath, text=None):
        return (f'<a href="{e(relpath)}" target="_blank" rel="noopener">'
                f'{ui.icon("file")}{e(text or relpath)}</a>')

    def image(self, relpath, alt):
        return (f'<a href="{e(relpath)}" data-image="" data-path="{e(relpath)}" title="{e(alt)}">'
                f'<img class="thumb" loading="lazy" src="{e(relpath)}" alt="{e(alt)}"></a>')

    def button(self, relpath, label, ic="file"):
        return (f'<a class="btn" href="{e(relpath)}" target="_blank" rel="noopener">{ui.icon(ic)}'
                f'{e(label)}</a>')

    def url(self, url):
        return f"<code>{e(url)}</code>"


FILE_LINKS = FileLinks()


class SummaryLinks(FileLinks):
    """The summary page's: a file is named, not linked (`devloops dashboard` opens it)."""

    def path(self, relpath, text=None):
        return f'<code title="{e(relpath)}">{e(text or relpath)}</code>'

    def image(self, relpath, alt):
        return self.path(relpath, alt)

    def button(self, relpath, label, ic="file"):
        return ""


SUMMARY_LINKS = SummaryLinks()


def serve_command(ws):
    """`devloops dashboard --daemon`, with `--workspace` when `ws` is not the default."""
    return "devloops dashboard --daemon" + workspace_flag(ws)


def serve_hint(command):
    return (f'<p class="callout serve-hint">{ui.icon("folder")}<span>Files and conversations: '
            f'<code>{e(command)}</code></span></p>')


# --- charts -----------------------------------------------------------------------------------------

def bar_chart(rows, value_format, title, unit_label):
    """Horizontal single-hue bars: `rows` are `(label, value, tooltip)`. Values label the bar end;
    a visually hidden table carries the same numbers for screen readers."""
    rows = [r for r in rows if r[1] is not None]
    if not rows or max(r[1] for r in rows) <= 0:
        return '<p class="muted">Nothing recorded yet.</p>'
    peak = max(r[1] for r in rows)
    label_w, chart_w, row_h, value_w = 170, 250, 28, 64
    height = row_h * len(rows) + 8
    width = label_w + chart_w + value_w
    parts = [f'<svg class="chart" width="{width}" viewBox="0 0 {width} {height}" '
             f'role="img" aria-label="{e(title)}">']
    for i, (label, value, tip) in enumerate(rows):
        y = i * row_h + 4
        w = max(8, chart_w * value / peak)
        parts.append(
            f'<g class="mark" tabindex="0" data-tip="{e(tip)}">'
            f'<rect class="hit" x="0" y="{y}" width="{label_w + chart_w + value_w}" '
            f'height="{row_h}"/>'
            f'<text class="axis-label" x="{label_w - 10}" y="{y + row_h / 2 + 4}" '
            f'text-anchor="end">{e(label)}</text>'
            f'<path class="bar" d="M{label_w},{y + 6} h{w - 4} a4,4 0 0 1 4,4 v{row_h - 20} '
            f'a4,4 0 0 1 -4,4 h{-(w - 4)} z"/>'
            f'<text class="value-label" x="{label_w + w + 6}" y="{y + row_h / 2 + 4}">'
            f'{e(value_format(value))}</text></g>')
    parts.append(f'<line class="baseline" x1="{label_w}" x2="{label_w}" y1="0" y2="{height}"/>')
    parts.append("</svg>")
    table = "".join(f"<tr><td>{e(label)}</td><td>{e(value_format(value))}</td></tr>"
                    for label, value, _ in rows)
    return ("".join(parts) + f'<table class="sr-only"><caption>{e(title)}</caption><thead><tr>'
            f'<th>{e(unit_label[0])}</th><th>{e(unit_label[1])}</th></tr></thead>'
            f'<tbody>{table}</tbody></table>')


def timeline(data):
    """A row per loop phase (planning, each milestone); trials as status-toned segments in time."""
    rows = []
    for loop, d in data["loops"].items():
        rows.append((f"{loop} · Planning",
                     [(t, f"Planning trial {t['n']} ({t.get('kind')})") for t in d["planning"]]))
        for m in d["milestones"]:
            rows.append((f"{loop} · {m['id']}",
                         [(t, f"{m['id']} trial {t['n']} ({t['kind']})") for t in m["trials"]]))
    spans = [(_parse_time(t.get("started_at")), _parse_time(t.get("ended_at")) or
              _parse_time(t.get("started_at"))) for _, ts in rows for t, _ in ts]
    spans = [(a, b) for a, b in spans if a and b]
    if not spans:
        return '<p class="muted">No trials yet.</p>'
    t0 = min(a for a, _ in spans)
    t1 = max(b for _, b in spans)
    total = max((t1 - t0).total_seconds(), 1)
    label_w, chart_w, row_h, pad = 190, 900, 30, 40
    height = row_h * len(rows) + 30
    width = label_w + chart_w + pad
    parts = [f'<svg class="chart" width="{width}" viewBox="0 0 {width} {height}" role="img" '
             f'aria-label="Trial timeline">']
    for k in range(5):  # time gridlines
        x = label_w + chart_w * k / 4
        parts.append(f'<line class="grid" x1="{x}" x2="{x}" y1="0" y2="{height - 22}"/>'
                     f'<text class="axis-label" x="{x}" y="{height - 6}" text-anchor="middle">'
                     f'+{e(duration(total * k / 4))}</text>')
    for i, (label, trials) in enumerate(rows):
        y = i * row_h + 4
        parts.append(f'<text class="axis-label" x="{label_w - 10}" y="{y + row_h / 2 + 2}" '
                     f'text-anchor="end">{e(label)}</text>')
        for t, name in trials:
            a = _parse_time(t.get("started_at"))
            if not a:
                continue
            b = _parse_time(t.get("ended_at")) or a
            x = label_w + chart_w * (a - t0).total_seconds() / total
            w = max(6, chart_w * (b - a).total_seconds() / total - 2)
            text, icon, tone_ = TRIAL_STATUS.get(t["status"], (t["status"], "•", "muted"))
            reason = t.get("reason") or (t.get("failure") or {}).get("reason")
            tip = (f"{name} — {icon} {text}" + (f": {reason}" if reason else "") +
                   f" · {duration(_seconds(t.get('started_at'), t.get('ended_at')))}")
            parts.append(f'<g class="mark" tabindex="0" data-tip="{e(tip)}">'
                         f'<rect class="seg tone-{tone_}" x="{x:.1f}" y="{y + 5}" width="{w:.1f}" '
                         f'height="{row_h - 12}" rx="4"/></g>')
    parts.append("</svg>")
    legend = "".join(f'<span class="legend-item"><span class="swatch tone-{tone_}"></span>'
                     f'<span aria-hidden="true">{icon}</span> {e(text)}</span>'
                     for text, icon, tone_ in TRIAL_STATUS.values())
    return f'<div class="legend">{legend}</div>' + "".join(parts)


# --- views ------------------------------------------------------------------------------------------

ORCHESTRATOR_STATUS = {"running": ("Running", "◷", "neutral"), "paused": ("Paused", "⏸", "warning"),
                       "completed": ("Completed", "✓", "good"), "stopped": ("Stopped", "✕", "critical")}


def table(head, rows, attrs="", empty=None):
    """A bordered, scrollable table; `head` is `[(label, numeric)]`."""
    if not rows and empty:
        return f'<p class="muted">{e(empty)}</p>'
    ths = "".join(f'<th{" class=num" if num else ""}>{e(label)}</th>' for label, num in head)
    return (f'<div class="table-wrap"><table{attrs}><thead><tr>{ths}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def _kpi(label, value, sub=None):
    return (f'<div class="tile"><div class="tile-label">{e(label)}</div>'
            f'<div class="tile-value">{value}</div>'
            + (f'<div class="tile-sub">{e(sub)}</div>' if sub else "") + "</div>")


def _overall_status(data):
    statuses = [d["status"] for d in data["loops"].values()]
    if not statuses:
        return "not-started"
    for s in ("stopped-on-service-error", "stopped-on-failure", "stopped-on-input-error",
              "awaiting-approval", "implementing", "planning"):
        if s in statuses:
            return s
    return "completed" if all(s == "completed" for s in statuses) else statuses[-1]


def kpi_row(data):
    t = data["totals"]
    rate = f"{100 * t['first_try'] / t['achieved']:.0f}%" if t["achieved"] else "–"
    return '<section class="kpis" aria-label="Totals">' + "".join([
        _kpi("Status", pill(_overall_status(data), RUN_STATUS)),
        _kpi("Milestones achieved", f"{t['achieved']} / {t['milestones']}"),
        _kpi("First-try pass rate", rate, "achieved on trial 1"),
        _kpi("Trials", str(t["trials"]), "counted (voids excluded)"),
        _kpi("Claude calls", str(t["calls"])),
        _kpi("Cost", e(money(t["cost"]))),
        _kpi("Tokens", e(number(t["tokens"])), "input + output + cache"),
        _kpi("Elapsed", e(duration(t["seconds"])), "first to last recorded action"),
    ]) + "</section>"


def _ticks(text):
    """Text with `commands` in backticks as HTML with <code>."""
    return re.sub(r"`([^`]*)`", r"<code>\1</code>", e(text))


def _next_action(loop, d):
    action = next_action(loop, d)
    return _ticks(action["text"]) if action else None


ATTENTION = {"critical": ("✕", "Needs action"), "warning": ("!", "Check"),
             "info": ("i", "Note")}


def attention(data, links=FILE_LINKS, call_href=None):
    """`attention_items` as `[(tone, html)]` for the summary page. `call_href(loop, record)` links
    a call (the full dashboard); otherwise calls link to the calls view."""
    out = []
    for item in attention_items(data, records=True):
        kind, loop = item["kind"], item.get("loop")
        where = (f'<a href="#ms-{e(loop)}-{e(item.get("milestone"))}">{e(loop)} '
                 f'{e(item.get("milestone"))}</a>')
        if kind == "loop":
            text = (f'<a href="#{e(loop)}"><strong>{e(loop)}</strong></a> is '
                    f'{pill(item["status"], RUN_STATUS)}'
                    + (f' {e(item["reason"])}' if item["reason"] else ""))
            if item["action"]:
                text += f'<div class="small">→ {_ticks(item["action"]["text"])}</div>'
        elif kind == "failing-criteria":
            text = (f'{where}: {e(", ".join(item["criteria"]))} failing on trial '
                    f'{e(item["trial"].split(".")[0])}')
        elif kind == "passed-after":
            kinds = ", ".join(f"{n} {word}" for n, word in ((item["failed"], "failed"),
                                                            (item["voided"], "voided")) if n)
            text = (f'{where} passed after {e(kinds)} trial(s)'
                    + (f' ({e(", ".join(item["reasons"]))})' if item["reasons"] else ""))
        elif kind in ("auto-accepted", "unanswered", "suggested"):
            ids = item["questions"]
            text = (f'<a href="#questions">{e(loop)}: {len(ids)} {e(item["what"])}</a> '
                    f'({e(", ".join(ids))})' + (f'; {e(item["note"])}' if item["note"] else ""))
        elif kind == "failed-call":
            href = call_href(loop, item["record"]) if call_href else "calls"
            text = (f'<a href="#{e(href)}">{e(loop)} call #{e(item["call"])} {e(item["step"])}'
                    f'</a> failed ({e(item["failure"])})')
        else:  # large-evidence
            text = (e(item["message"]) + ": " + ", ".join(
                links.path(i["path"]) + f" ({number(i['bytes'])}B)" for i in item["files"]))
        out.append((item["tone"], text))
    return out


def attention_panel(items):
    if not items:
        return ('<div class="attention ok"><span class="a-icon tone-good" aria-hidden="true">✓</span>'
                'Nothing needs attention.</div>')
    rows = "".join(f'<li class="tone-{tone}"><span class="a-icon" aria-hidden="true">'
                   f'{ATTENTION[tone][0]}</span><span class="sr-only">{ATTENTION[tone][1]}: </span>'
                   f'<div>{html_}</div></li>' for tone, html_ in items)
    title = ("Needs attention" if any(tone != "info" for tone, _ in items) else "Worth knowing")
    return (f'<section class="attention" aria-labelledby="attention-h"><h3 id="attention-h">{title} '
            f'<span class="count">{len(items)}</span></h3><ul>{rows}</ul></section>')


def _cost_rows(data):
    cost_rows, step_rows, steps = [], [], {}
    for loop, d in data["loops"].items():
        cost_rows.append((f"{loop} · Planning", d["planning_cost"],
                          f"{loop} planning: {money(d['planning_cost'])}"))
        for m in d["milestones"]:
            cost_rows.append((f"{loop} · {m['id']}", m["cost"],
                              f"{loop} {m['id']} {m['title']}: {money(m['cost'])} over "
                              f"{m['calls']} call(s), {len(m['trials'])} trial(s)"))
        for step, v in d["by_step"].items():
            agg = steps.setdefault(step, {"calls": 0, "cost": 0.0, "tokens": 0})
            for k in agg:
                agg[k] += v[k]
    for step, v in sorted(steps.items(), key=lambda kv: -kv[1]["cost"]):
        step_rows.append((step, v["cost"], f"{step}: {money(v['cost'])} over {v['calls']} "
                                           f"call(s), {number(v['tokens'])} tokens"))
    return cost_rows, step_rows


def overview_view(data, links=FILE_LINKS, notice="", call_href=None):
    req = data["requirements"]
    selection = f" · story {e(req.get('story_id'))}" if req.get("story_id") else ""
    sub = (f'Requirements <code>{e(req.get("path"))}</code> · mode {e(req.get("mode"))}{selection}'
           f' · generated {e(data["generated_at"])}')
    body = [notice, kpi_row(data), attention_panel(attention(data, links, call_href))]
    if not data["loops"]:
        body.append('<p class="muted">No loop has started in this workspace yet.</p>')
        return ui.view("overview", "Overview", "".join(body), sub)
    cards = []
    for loop, d in data["loops"].items():
        s = d["stats"]
        pct = 100 * s["achieved"] / s["milestones"] if s["milestones"] else 0
        action = _next_action(loop, d)
        cards.append(
            f'<a class="card loop-card" href="#{e(loop)}"><div class="row">{ui.icon("loop")}'
            f'<span class="name">{e(loop)}</span><span class="end">{pill(d["status"], RUN_STATUS)}'
            f'</span></div><div class="progress" role="img" aria-label="{s["achieved"]} of '
            f'{s["milestones"]} milestones achieved"><span style="width:{pct:.0f}%"></span></div>'
            f'<div class="facts"><span><b>{s["achieved"]}/{s["milestones"]}</b> milestones</span>'
            f'<span><b>{s["trials"]}</b> trials</span><span><b>{s["calls"]}</b> calls</span>'
            f'<span><b>{e(money(s["cost"]))}</b></span><span><b>{e(duration(s["seconds"]))}</b>'
            f'</span></div>' + (f'<div class="small next">→ {action}</div>' if action else "")
            + "</a>")
    cost_rows, step_rows = _cost_rows(data)
    body += [f'<h3>Loops</h3><div class="grid cols-2">{"".join(cards)}</div>',
             f'<h3 id="timeline">Trial timeline</h3><div class="card">{timeline(data)}</div>',
             '<div class="grid cols-2 gap-top"><div class="card"><h3>Cost by milestone</h3>'
             + bar_chart(cost_rows, money, "Cost by milestone", ("Milestone", "Cost"))
             + '</div><div class="card"><h3>Cost by step</h3>'
             + bar_chart(step_rows, money, "Cost by step", ("Step", "Cost")) + "</div></div>"]
    return ui.view("overview", "Overview", "".join(body), sub)


def run_view(data):
    orch = data["run"]
    if not orch:
        return ""
    rows = [f"<tr><td><a href='#{e(s['loop'])}'>{e(s['loop'])}</a></td>"
            f"<td>{pill(s['status'], RUN_STATUS)}</td><td>{e(s.get('reason') or '')}</td>"
            f"<td class='muted small'>{e(s.get('started_at'))}</td>"
            f"<td class='muted small'>{e(s.get('ended_at'))}</td></tr>"
            for s in orch.get("steps") or []]
    body = table([("Loop", 0), ("Status", 0), ("Reason", 0), ("Started", 0), ("Ended", 0)], rows,
                 empty="No loop has run yet.")
    handoff = orch.get("handoff") or {}
    if handoff:
        spec = handoff.get("api_spec") or {}
        runtime = handoff.get("backend_runtime") or {}
        body += ('<div class="card gap-top"><h3>Handoff</h3><dl>'
                 f"<dt>API spec</dt><dd><code>{e(spec.get('path'))}</code><div class='muted small'>"
                 f"sha256 {e(spec.get('sha256'))}</div></dd>"
                 + "".join(f"<dt>Backend {e(k)}</dt><dd><code>{e(v)}</code></dd>"
                           for k, v in runtime.items()) + "</dl></div>")
    return ui.view("run", "Run", body, badge=pill(orch.get("status"), ORCHESTRATOR_STATUS))


def _calls_link(call_ref, sessions):
    links = [call_ref(s) for s in sessions if s]
    return " ".join(f'<a href="#{e(cid)}">#{e(cid.rsplit("-", 1)[-1])}</a>' for cid in links if cid)


def milestone_card(loop, m, links=FILE_LINKS, call_ref=None):
    last = m["trials"][-1] if m["trials"] else None
    validation = (last or {}).get("validation") or {}
    results = {c["criterion_id"]: c for c in validation.get("criteria", [])}
    dots = "".join(f'<i class="tone-{tone(t["status"], TRIAL_STATUS)}" title="Trial {t["n"]}: '
                   f'{e(TRIAL_STATUS.get(t["status"], (t["status"],))[0])}"></i>' for t in m["trials"])
    parts = [f'<details class="ms" id="ms-{e(loop)}-{e(m["id"])}"'
             f'{"" if m["status"] == "achieved" else " open"}><summary>{ui.icon("chev", "chev")}'
             f'<span class="head"><span class="mid">{e(m["id"])}</span><span class="mtitle">'
             f'{e(m["title"])}</span>{pill(m["status"], MILESTONE_STATUS)}</span><span class="meta">'
             f'<span class="trials" role="img" aria-label="{len(m["trials"])} trial(s)">{dots}</span>'
             f'<span>{len(m["trials"])} trial(s)</span><span>{e(money(m["cost"]))}</span>'
             f'<span>{e(duration(m["seconds"]))}</span></span></summary><div class="body">']
    if m.get("goal"):
        parts.append(f'<p class="goal">{e(m["goal"])}</p>')
    if m["depends_on"]:
        parts.append(f'<p class="muted small">Depends on {e(", ".join(m["depends_on"]))}</p>')

    tasks = "".join(
        f'<li><span class="check {"on" if t["status"] == "achieved" else ""}" aria-label="'
        f'{"achieved" if t["status"] == "achieved" else e(t["status"])}">'
        f'{"✓" if t["status"] == "achieved" else "○"}</span><div><strong>{e(t["id"])}</strong> '
        f'{e(t["title"])} <span class="refs">{e(", ".join(t.get("requirement_refs") or []))}</span>'
        f'<div class="muted small">{e(t.get("description"))}</div></div></li>' for t in m["tasks"])
    crit = []
    for c in m["criteria"]:
        r = results.get(c["id"])
        if r is None:
            result = '<span class="muted small">Not validated</span>'
        else:
            result = pill("passed" if r["passed"] else "failed", TRIAL_STATUS)
        evidence = []
        for item in ((r or {}).get("evidence") or []) if last else []:
            rel = os.path.join(os.path.dirname(last["evidence_dir"]), item)
            if item.lower().endswith(IMAGE_EXTENSIONS):
                evidence.append(links.image(rel, os.path.basename(item)))
            else:
                evidence.append(links.path(rel, os.path.basename(item)))
        crit.append(f'<tr><td><strong>{e(c["id"])}</strong> {e(c["text"])}</td><td>{result}</td>'
                    f'<td class="small">{e((r or {}).get("observed"))}</td>'
                    f'<td><div class="evidence">{"".join(evidence)}</div></td></tr>')
    head = "Acceptance criteria" + (f" · trial {last['n']}" if last else "")
    parts.append(f'<h4>Tasks</h4><ul class="tasks">{tasks}</ul><h4>{e(head)}</h4>'
                 + table([("Criterion", 0), ("Result", 0), ("Observed", 0), ("Evidence", 0)], crit,
                         ' class="criteria"'))

    checks = validation.get("checks") or []
    if checks:
        rows = []
        for c in checks:
            failures = "; ".join(c.get("failures") or [])
            rows.append(f'<tr><td>{e(c["check_id"])}</td><td>'
                        f'{pill("passed" if c["passed"] else "failed", TRIAL_STATUS)}'
                        f'{"<div class=small>" + e(failures) + "</div>" if failures else ""}</td>'
                        f'<td><code class="cmd">{e(c.get("command"))}</code></td>'
                        f'<td class="num">{e((c.get("response") or {}).get("status"))}</td></tr>')
        parts.append("<h4>HTTP checks</h4>" + table(
            [("Check", 0), ("Result", 0), ("Command", 0), ("Status", 1)], rows))
    requests = validation.get("network_requests") or []
    if requests:
        rows = [f"<tr><td>{e(r.get('method'))}</td><td><code>{e(r.get('url'))}</code></td>"
                f"<td class='num'>{e(r.get('status'))}</td></tr>" for r in requests]
        parts.append("<h4>Network requests seen by the browser</h4>" + table(
            [("Method", 0), ("URL", 0), ("Status", 1)], rows))
    contract = validation.get("contract")
    if contract:
        unmatched = contract.get("unmatched_operations") or []
        unverified = contract.get("unverified_operations") or []
        parts.append(f'<p>API contract: {pill("passed" if contract.get("passed") else "failed", TRIAL_STATUS)}'
                     + (f' Unmatched: <code>{e(", ".join(unmatched))}</code>' if unmatched else "")
                     + (f' Not verified by any check, so not published: '
                        f'<code>{e(", ".join(unverified))}</code>' if unverified else "")
                     + "</p>")

    rows = []
    for t in m["trials"]:
        reason = f'<strong>{e(t["reason"])}</strong>: ' if t["reason"] else ""
        detail = (t["detail"] or "")
        calls = (_calls_link(call_ref, t["sessions"]) if call_ref else
                 f'<code class="small">{e(" ".join(s[:8] for s in t["sessions"] if s))}</code>')
        rows.append(f'<tr><td class="num">{t["n"]}</td><td>{e(t["kind"])}</td>'
                    f'<td>{pill(t["status"], TRIAL_STATUS)}</td><td class="small detail">{reason}'
                    f'{e(detail[:600])}{"…" if len(detail) > 600 else ""}</td>'
                    f'<td class="num">{e(duration(t["seconds"]))}</td>'
                    f'<td class="num">{e(money(t["cost"]))}</td><td>{calls}</td></tr>')
    parts.append("<h4>Trials</h4>" + table(
        [("#", 1), ("Kind", 0), ("Result", 0), ("Detail", 0), ("Duration", 1), ("Cost", 1),
         ("Calls" if call_ref else "Sessions", 0)], rows, empty="No trials yet."))
    return "".join(parts) + "</div></details>"


def loop_view(loop, d, ws_path, links=FILE_LINKS, call_ref=None, files_view=False, hint=""):
    s = d["stats"]
    reason = d["status_reason"] or {}
    parts = []
    if reason:
        parts.append(f'<p class="callout bad reason"><strong>{e(reason.get("code"))}</strong>: '
                     f'{e(reason.get("message"))}</p>')
    action = _next_action(loop, d)
    if action:
        parts.append(f'<p class="callout warn action"><span aria-hidden="true">→</span> {action}</p>')
    rate = f"{100 * s['first_try'] / s['achieved']:.0f}%" if s["achieved"] else "–"
    parts.append('<div class="kpis compact">' + "".join([
        _kpi("Milestones", f"{s['achieved']} / {s['milestones']}"),
        _kpi("First-try", rate), _kpi("Trials", str(s["trials"])),
        _kpi("Calls", str(s["calls"])), _kpi("Cost", e(money(s["cost"]))),
        _kpi("Elapsed", e(duration(s["seconds"]))),
    ]) + "</div>")

    keys = [(f"{loop}/progress.md", "Progress", "md"),
            (f"{loop}/outputs/plan-summary.md", "Plan summary", "md")]
    if os.path.exists(os.path.join(ws_path, loop, "outputs", "final-report.md")):
        keys.append((f"{loop}/outputs/final-report.md", "Final report", "md"))
    if d["openapi_artifact"]:
        keys.append((f"{loop}/{d['openapi_artifact']['path']}", "OpenAPI document", "json"))
    buttons = "".join(links.button(path, label, ic) for path, label, ic in keys)
    if d["ui_url"]:
        buttons += f'<span class="tag">UI {links.url(d["ui_url"])}</span>'
    more = f'<a class="btn ghost" href="#calls">{ui.icon("chat")}{s["calls"]} calls</a>'
    if files_view:
        more += f'<a class="btn ghost" href="#files">{ui.icon("folder")}Files</a>'
    parts.append(f'<div class="toolbar outputs gap-top">{buttons}<span class="spacer"></span>{more}</div>'
                 + hint)

    plan = d["plan"]
    if plan:
        stack = plan.get("stack") or {}
        runtime = plan.get("runtime") or {}
        parts.append('<div class="grid cols-2"><div class="card"><h3>Stack</h3>'
                     f'<p>{e(stack.get("summary"))}</p><p class="muted small">Source: '
                     f'{e(stack.get("source"))}</p></div><div class="card"><h3>Runtime</h3><dl>'
                     + "".join(f"<dt>{e(k)}</dt><dd><code>{e(v)}</code></dd>"
                               for k, v in runtime.items() if v)
                     + f'<dt>target</dt><dd><code>{e(d["target_dir"])}</code></dd></dl></div></div>')
    parts.append("<h3>Milestones</h3>")
    parts += [milestone_card(loop, m, links, call_ref) for m in d["milestones"]]
    if not d["milestones"]:
        parts.append('<p class="muted">No plan stored yet.</p>')
    return ui.view(loop, loop, "".join(parts), badge=pill(d["status"], RUN_STATUS))


ANSWER_SOURCE = {
    "developer": ("Your answer", "✓", "good"),
    "accepted": ("Suggestion accepted", "!", "warning"),
    "suggested": ("Suggested, not accepted yet", "◷", "neutral"),
    "none": ("Unanswered", "•", "critical"),
}


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


def questions_view(data):
    rows = []
    for loop, d in data["loops"].items():
        for qid in question_ids(d):
            question, (answer, source), q = question_answer(d, qid)
            cell = pill(source or "none", ANSWER_SOURCE)
            if answer:
                cell += (f'<div class="muted">{e(answer)}</div>' if source == "suggested"
                         else f"<div>{e(answer)}</div>")
            if source in ("suggested", "accepted") and q.get("reason"):
                cell += f'<div class="muted small">Why: {e(q["reason"])}</div>'
            if source == "accepted":
                cell += f'<div class="muted small">{e(q["source"])}</div>'
            rows.append(f"<tr><td>{e(loop)}</td><td><strong>{e(qid)}</strong></td>"
                        f"<td>{e(question)}</td><td>{cell}</td></tr>")
    assumptions = [f"<tr><td>{e(loop)}</td><td><strong>{e(a['id'])}</strong></td><td>{e(a['text'])}"
                   f"</td><td class='muted small'>{e(a.get('source'))}</td></tr>"
                   for loop, d in data["loops"].items() for a in d["plan"].get("assumptions") or []]
    grants = [f"<tr><td>{e(loop)}</td><td>{e(g.get('milestone_id'))}</td>"
              f"<td class='num'>{e(g.get('extra_trials'))}</td><td>{e(g.get('reason'))}</td>"
              f"<td class='muted small'>{e(g.get('granted_at'))}</td></tr>"
              for loop, d in data["loops"].items() for g in d["grants"]]
    body = ["<h3>Open questions</h3>" + table(
                [("Loop", 0), ("ID", 0), ("Question", 0), ("Answer", 0)], rows,
                empty="No questions were raised."),
            "<h3>Planning assumptions</h3>" + table(
                [("Loop", 0), ("ID", 0), ("Assumption", 0), ("Source", 0)], assumptions,
                empty="None recorded.")]
    if grants:
        body.append("<h3>Retries granted</h3>" + table(
            [("Loop", 0), ("Milestone", 0), ("Trials", 1), ("Reason", 0), ("Granted", 0)], grants))
    return ui.view("questions", "Questions and assumptions", "".join(body))


def calls_view(data, links=FILE_LINKS, call_ids=None, models=None, sources="", hint=None):
    """Every Claude call. With `call_ids` (the full and served dashboards) a row opens the call's
    conversation, prompt, and settings; `hint` replaces the line saying so."""
    rows = []
    for loop, d in data["loops"].items():
        for r in sorted(d["invocations"], key=lambda r: r.get("seq") or 0):
            failure = r.get("failure_class")
            result = (f'<span class="pill tone-critical"><span aria-hidden="true">✕</span> '
                      f'{e(failure)}</span>' if failure not in (None, "none")
                      else '<span class="muted small">ok</span>')
            cid = call_ids(loop, r) if call_ids else None
            model = (models or {}).get((loop, r.get("seq"))) or r.get("model") or ""
            last = f'<td class="muted small">{e(model)}</td>'
            attrs = f' class="row-link" data-open="{e(cid)}"' if cid else ""
            rows.append(
                f'<tr{attrs} data-loop="{e(loop)}"><td>{e(loop)}</td><td class="num">'
                f'{e(r.get("seq"))}</td><td><strong>{e(r.get("step"))}</strong></td>'
                f'<td>{e(r.get("milestone_id") or "planning")}</td><td class="num">'
                f'{e(r.get("trial") if r.get("trial") is not None else "")}</td>'
                f'<td><code class="small">{e((r.get("session_id") or "")[:8])}</code></td>{last}'
                f'<td class="num">{e(number(tokens_of(r)))}</td>'
                f'<td class="num">{e(money(r.get("cost_usd")))}</td>'
                f'<td class="num">{e(duration((r.get("duration_ms") or 0) / 1000))}</td>'
                f'<td>{result}</td></tr>')
    chips = "".join(f'<button type="button" class="chip" data-loop-chip="{e(loop)}" '
                    f'data-table="calls-table" aria-pressed="false">{e(loop)}</button>'
                    for loop in data["loops"])
    head = [("Loop", 0), ("#", 1), ("Step", 0), ("Milestone", 0), ("Trial", 1), ("Session", 0),
            ("Model", 0), ("Tokens", 1), ("Cost", 1), ("Duration", 1),
            ("Result", 0)]
    by_model = {}
    for loop, d in data["loops"].items():
        for r in d["invocations"]:
            # The same name the Model column shows (the transcript's, in the full dashboard).
            # A call from before models were recorded has no `model` key at all.
            name = ((models or {}).get((loop, r.get("seq"))) or r.get("model")
                    or ("(Claude Code default)" if "model" in r else "(not recorded)"))
            entry = by_model.setdefault(name, [0, 0])
            entry[0] += 1
            entry[1] += r.get("cost_usd") or 0
    # Only worth a line when calls ran on more than one model (`models` in the config).
    split = ("" if len(by_model) < 2 else
             '<p class="muted small">Cost by model: ' + " · ".join(
                 f"{e(name)} {e(money(cost))} ({count} call(s))"
                 for name, (count, cost) in sorted(by_model.items(), key=lambda x: -x[1][1]))
             + "</p>")
    if hint is None:
        hint = '<p class="muted small">Select a call to read its conversation, prompt, and settings.</p>'
    body = (f'<div class="toolbar"><input class="input" type="search" placeholder="Filter calls…" '
            f'aria-label="Filter calls" data-filter-for="calls-table"><div class="chips" role="group" '
            f'aria-label="Loops">{chips}</div></div>'
            + table(head, rows, ' id="calls-table"', empty="No Claude call recorded.")
            + f'{split}{hint}{sources}')
    total = sum(len(d["invocations"]) for d in data["loops"].values())
    return ui.view("calls", "Claude calls", body, f"{total} headless Claude Code call(s)")


def events_view(data):
    events = sorted(((ev.get("at") or "", loop, ev) for loop, d in data["loops"].items()
                     for ev in d["events"]), key=lambda x: x[0])
    rows = [f"<tr><td class='muted small nowrap'>{e(at)}</td><td>{e(loop)}</td>"
            f"<td><span class='tag'>{e(ev.get('type'))}</span></td><td>{e(ev.get('milestone'))}</td>"
            f"<td>{e(ev.get('message'))}</td></tr>" for at, loop, ev in events]
    body = ('<div class="toolbar"><input class="input" type="search" placeholder="Filter events…" '
            'aria-label="Filter events" data-filter-for="events-table"></div>'
            + table([("Time", 0), ("Loop", 0), ("Type", 0), ("Milestone", 0), ("Message", 0)], rows,
                    ' id="events-table"', empty="No events yet."))
    return ui.view("events", "Events", body, f"{len(events)} event(s), oldest first")


def full_dashboards_view(data):
    """Links to the workspace's full dashboards, newest first (002 FR-036a)."""
    items = data.get("full_dashboards") or []
    if not items:
        return ""
    rows = [f'<tr><td><a href="{e(i["link"])}" target="_blank" rel="noopener">{ui.icon("file")}'
            f'{e(i["name"])}</a></td><td class="num">{e(number(i["bytes"]))}B</td></tr>'
            for i in items]
    body = ('<p class="muted">Self-contained pages with every artifact and Claude Code conversation, '
            'newest first. They contain full conversations: review before sharing.</p>'
            + table([("File", 0), ("Size", 1)], rows))
    return ui.view("full-dashboards", "Full dashboards", body)


def sidebar(data, kind, details, workspaces=None):
    """The navigation: the run, each loop (its status as a dot), and `details` links; and, served,
    the `workspaces` to switch to."""
    run = [ui.nav_link("overview", "Overview", "grid")]
    if data["run"]:
        run.append(ui.nav_link("run", "Run", "flow"))
    loops = [ui.nav_link(loop, loop, "loop", ui.nav_dot(tone(d["status"], RUN_STATUS),
                                                        RUN_STATUS.get(d["status"], (d["status"],))[0]))
             for loop, d in data["loops"].items()]
    groups = [("Run", run)] + ([("Loops", loops)] if loops else []) + [("Details", details)]
    generated = (data["generated_at"] or "")[:19].replace("T", " ") + " UTC"
    return ui.sidebar(data["workspace"], kind, groups, generated, __version__, workspaces)


def detail_links(data, files=None):
    calls = sum(len(d["invocations"]) for d in data["loops"].values())
    events = sum(len(d["events"]) for d in data["loops"].values())
    links = [ui.nav_link("calls", "Claude calls", "chat", ui.nav_count(calls))]
    if files is not None:
        links.append(ui.nav_link("files", "Files", "folder", ui.nav_count(files)))
    links += [ui.nav_link("questions", "Questions", "help"),
              ui.nav_link("events", "Events", "list", ui.nav_count(events))]
    return links


def render_page(data, ws_path, command="devloops dashboard --daemon"):
    """The summary page: status, milestones, trials, failures, questions, and cost. Each place
    that would link a file or a conversation says how to see them instead (`command`)."""
    hint = serve_hint(command)
    links = SUMMARY_LINKS
    views = [overview_view(data, links, hint), run_view(data)]
    views += [loop_view(loop, d, ws_path, links, hint=hint) for loop, d in data["loops"].items()]
    views += [calls_view(data, links, hint=hint), questions_view(data), events_view(data),
              full_dashboards_view(data)]
    details = detail_links(data)
    if data.get("full_dashboards"):
        details.append(ui.nav_link("full-dashboards", "Full dashboards", "history",
                                   ui.nav_count(len(data["full_dashboards"]))))
    return ui.page(f"devloops · {data['workspace']}", sidebar(data, "summary", details),
                   ui.topbar(data["workspace"], pill(_overall_status(data), RUN_STATUS)),
                   [v for v in views if v])


def write(ws):
    """Render `workspaces/<ws>/dashboard.html` from state and return its path."""
    path = os.path.join(ws.path, FILENAME)
    state.write_text_atomic(path, render_page(collect(ws), ws.path, serve_command(ws)))
    return path


def data_json(ws):
    """The collected data as JSON text (for tooling and tests)."""
    return json.dumps(collect(ws), default=str, indent=2)
