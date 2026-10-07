"""`workspaces/<ws>/dashboard.html`: one self-contained page summarizing a workspace.

Everything is read from the workspace's state (`workspace.json`, each loop's `state/` and
`outputs/open-questions.md`, `orchestrator/state.json`); nothing is read back from the page. The
views here (overview, loops, calls, questions, events) are shared with the full dashboard
(fulldash.py); the shell, styles, and script come from ui.py, so the page opens offline from disk.
State is already redacted (FR-070); every value is HTML-escaped here.
"""
import html
import json
import os
import re
import socket
from datetime import datetime

from . import __version__, render, state, ui

LOOPS = ("backend-dev", "frontend-dev")
FILENAME = "dashboard.html"
REFRESH_SECONDS = 10  # how often the page reloads itself while a loop is running

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


def _tokens(records):
    total = {"input": 0, "output": 0, "cache_creation": 0, "cache_read": 0}
    for r in records:
        for k in total:
            total[k] += (r.get("tokens") or {}).get(k) or 0
    return total


def _cost(records):
    return sum(r.get("cost_usd") or 0 for r in records)


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
            trials.append({
                "n": n, "kind": doc.get("kind") or ("implement" if n == 1 else "fix"),
                "status": summary["status"], "reason": summary.get("reason"),
                "detail": (doc.get("failure") or {}).get("detail"),
                "started_at": summary.get("started_at"), "ended_at": summary.get("ended_at"),
                "seconds": _seconds(summary.get("started_at"), summary.get("ended_at")),
                "cost": _cost(calls), "tokens": _tokens(calls),
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
            "seconds": _seconds(ms.get("started_at"), ms.get("ended_at")),
        })

    planning_calls = by_milestone.get(None, [])
    planning = [dict(t, seconds=_seconds(t.get("started_at"), t.get("ended_at")))
                for t in (run.get("planning") or {}).get("trials", [])]
    times = [_parse_time(e.get("at")) for e in events] + \
        [_parse_time(r.get(k)) for r in invocations for k in ("started_at", "ended_at")]
    times = [t for t in times if t]
    by_step = {}
    for rec in invocations:
        step = by_step.setdefault(rec.get("step") or "?", {"calls": 0, "cost": 0.0, "tokens": 0})
        step["calls"] += 1
        step["cost"] += rec.get("cost_usd") or 0
        step["tokens"] += sum((rec.get("tokens") or {}).get(k) or 0
                              for k in ("input", "output", "cache_creation", "cache_read"))
    counted = [t for m in milestones for t in m["trials"] if t["status"] != "void"]
    achieved = [m for m in milestones if m["status"] == "achieved"]
    return {
        "loop": loop, "status": run.get("status"), "status_reason": run.get("status_reason"),
        "plan": plan, "milestones": milestones, "planning": planning,
        "planning_cost": _cost(planning_calls), "planning_tokens": _tokens(planning_calls),
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


def running(ws, loop):
    """Whether a command is running `loop` now: its lock is held by a live process (a lock left
    by a crash, or held on another host, does not count)."""
    lock = state.read_json(os.path.join(ws.loop_dir(loop), "state", "lock"))
    if not isinstance(lock, dict) or lock.get("host") != socket.gethostname():
        return False
    try:
        os.kill(int(lock.get("pid")), 0)
    except PermissionError:
        return True
    except (OSError, TypeError, ValueError):
        return False
    return True


def collect(ws):
    """The page's data for a workspace: its identity, each started loop, and the orchestrator."""
    loops = {loop: collect_loop(ws, loop) for loop in LOOPS}
    loops = {k: v for k, v in loops.items() if v}
    orch = state.read_json(os.path.join(ws.path, "orchestrator", "state.json"))
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
        "targets": ws.data.get("targets") or {}, "loops": loops, "orchestrator": orch,
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
        },
    }


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
    return sum((record.get("tokens") or {}).get(k) or 0
               for k in ("input", "output", "cache_creation", "cache_read"))


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


def _next_action(loop, d):
    status = d["status"]
    reason = (d["status_reason"] or {})
    code = reason.get("code")
    if status == "awaiting-approval":
        return (f"Review <code>{e(loop)}/outputs/</code>, answer "
                f"<code>open-questions.md</code> (an empty answer accepts Claude's suggestion), "
                f"then <code>devloops approve {e(loop)}</code> "
                f"or <code>devloops replan {e(loop)}</code>.")
    if status == "stopped-on-failure" and code == "needs-input":
        return (f"Answer the new questions in <code>open-questions.md</code> (an empty answer "
                f"accepts Claude's suggestion), then "
                f"<code>devloops retry {e(loop)} --milestone {e(reason.get('milestone_id'))} "
                f"--reason \"…\"</code>.")
    if status == "stopped-on-failure" and code in ("trials-exhausted",):
        return (f"Read the last trial's validation and evidence below, then "
                f"<code>devloops retry {e(loop)} --milestone {e(reason.get('milestone_id'))} "
                f"--reason \"…\"</code>.")
    if status == "stopped-on-service-error":
        return f"Fix the cause (log in, wait out a rate limit), then <code>devloops run {e(loop)}</code>."
    if status in ("planning", "implementing"):
        return f"Run <code>devloops run {e(loop)}</code> to continue."
    return None


ATTENTION = {"critical": ("✕", "Needs action"), "warning": ("!", "Check"),
             "info": ("i", "Note")}


def attention(data, links=FILE_LINKS, call_href=None):
    """What a reader should look at first: `[(tone, html)]`, most urgent first.

    Stopped or paused loops and their next action; acceptance criteria failing on a milestone's
    latest trial; suggested answers accepted automatically; unanswered questions and suggestions
    not accepted yet while a loop is not done; failed calls; large evidence
    files; and milestones that passed only after failed or voided trials. `call_href(loop,
    record)` links a call (the full dashboard); otherwise calls link to the calls view.
    """
    items = []
    for loop, d in data["loops"].items():
        status = d["status"]
        if status.startswith("stopped") or status == "awaiting-approval":
            reason = d["status_reason"] or {}
            text = f'<a href="#{e(loop)}"><strong>{e(loop)}</strong></a> is {pill(status, RUN_STATUS)}'
            if reason.get("message"):
                text += f' {e(reason["message"])}'
            action = _next_action(loop, d)
            items.append(("critical" if status.startswith("stopped") else "warning",
                          text + (f'<div class="small">→ {action}</div>' if action else "")))
        for m in d["milestones"]:
            last = m["trials"][-1] if m["trials"] else None
            failing = [c["criterion_id"] for c in ((last or {}).get("validation") or {})
                       .get("criteria", []) if not c.get("passed")]
            where = f'<a href="#ms-{e(loop)}-{e(m["id"])}">{e(loop)} {e(m["id"])}</a>'
            if failing and m["status"] != "achieved":
                items.append(("critical", f'{where}: {e(", ".join(failing))} failing on trial '
                                          f'{e(last["n"])}'))
            bad = [t for t in m["trials"] if t["status"] in ("failed", "void")]
            if m["status"] == "achieved" and bad:
                kinds = ", ".join(f'{sum(1 for t in bad if t["status"] == s)} {word}'
                                  for s, word in (("failed", "failed"), ("void", "voided"))
                                  if any(t["status"] == s for t in bad))
                reasons = sorted({t["reason"] for t in bad if t.get("reason")})
                items.append(("info", f'{where} passed after {e(kinds)} trial(s)'
                              + (f' ({e(", ".join(reasons))})' if reasons else "")))
        sources = {qid: question_answer(d, qid)[1][1] for qid in question_ids(d)}
        auto = [qid for qid, src in sources.items()
                if src == "accepted" and "automatically" in d["questions"][qid]["source"]]
        if auto:
            items.append(("warning", f'<a href="#questions">{e(loop)}: {len(auto)} suggested '
                                     f'answer(s) accepted automatically</a> ({e(", ".join(auto))});'
                                     ' review them like assumptions'))
        if status != "completed":
            open_ = [qid for qid, src in sources.items() if src is None]
            if open_:
                items.append(("warning", f'<a href="#questions">{e(loop)}: {len(open_)} unanswered '
                                         f'question(s)</a> ({e(", ".join(open_))})'))
            pending = [qid for qid, src in sources.items() if src == "suggested"]
            if pending:
                items.append(("info", f'<a href="#questions">{e(loop)}: {len(pending)} suggested '
                                      f'answer(s) not yet accepted</a> ({e(", ".join(pending))});'
                                      ' an empty answer accepts the suggestion'))
        for r in d["invocations"]:
            failure = r.get("failure_class")
            if failure not in (None, "none"):
                href = call_href(loop, r) if call_href else "calls"
                items.append(("warning", f'<a href="#{e(href)}">{e(loop)} call #{e(r.get("seq"))} '
                                         f'{e(r.get("step"))}</a> failed ({e(failure)})'))
    if data["large_evidence"]:
        items.append(("warning", "Evidence files over 1 MB, the likeliest place for a secret to "
                                 "hide; review before committing: " + ", ".join(
                                     links.path(i["path"]) + f" ({number(i['bytes'])}B)"
                                     for i in data["large_evidence"])))
    order = {"critical": 0, "warning": 1, "info": 2}
    return sorted(items, key=lambda item: order[item[0]])


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


def orchestrator_view(data):
    orch = data["orchestrator"]
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
    return ui.view("orchestrator", "Orchestrator", body,
                   badge=pill(orch.get("status"), ORCHESTRATOR_STATUS))


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


def loop_view(loop, d, ws_path, links=FILE_LINKS, call_ref=None, files_view=False):
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
    parts.append(f'<div class="toolbar outputs gap-top">{buttons}<span class="spacer"></span>{more}</div>')

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


def calls_view(data, links=FILE_LINKS, call_ids=None, models=None, sources=""):
    """Every Claude call. With `call_ids` (the full dashboard) a row opens the call's conversation;
    otherwise it links its prompt file."""
    rows = []
    for loop, d in data["loops"].items():
        for r in sorted(d["invocations"], key=lambda r: r.get("seq") or 0):
            failure = r.get("failure_class")
            result = (f'<span class="pill tone-critical"><span aria-hidden="true">✕</span> '
                      f'{e(failure)}</span>' if failure not in (None, "none")
                      else '<span class="muted small">ok</span>')
            cid = call_ids(loop, r) if call_ids else None
            prompt = r.get("prompt_path")
            model = (models or {}).get((loop, r.get("seq"))) or r.get("model") or ""
            last = (f'<td class="muted small">{e(model)}</td>'
                    if call_ids else
                    f"<td>{links.path(f'{loop}/{prompt}', 'prompt') if prompt else ''}</td>")
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
            ("Model" if call_ids else "Prompt", 0), ("Tokens", 1), ("Cost", 1), ("Duration", 1),
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
    hint = ("Select a call to read its conversation, prompt, and settings." if call_ids else
            "The full dashboard shows each call's conversation.")
    body = (f'<div class="toolbar"><input class="input" type="search" placeholder="Filter calls…" '
            f'aria-label="Filter calls" data-filter-for="calls-table"><div class="chips" role="group" '
            f'aria-label="Loops">{chips}</div></div>'
            + table(head, rows, ' id="calls-table"', empty="No Claude call recorded.")
            + f'{split}<p class="muted small">{hint}</p>{sources}')
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


def sidebar(data, kind, details):
    """The navigation: the run, each loop (its status as a dot), and `details` links."""
    run = [ui.nav_link("overview", "Overview", "grid")]
    if data["orchestrator"]:
        run.append(ui.nav_link("orchestrator", "Orchestrator", "flow"))
    loops = [ui.nav_link(loop, loop, "loop", ui.nav_dot(tone(d["status"], RUN_STATUS),
                                                        RUN_STATUS.get(d["status"], (d["status"],))[0]))
             for loop, d in data["loops"].items()]
    groups = [("Run", run)] + ([("Loops", loops)] if loops else []) + [("Details", details)]
    generated = (data["generated_at"] or "")[:19].replace("T", " ") + " UTC"
    return ui.sidebar(data["workspace"], kind, groups, generated, __version__)


def detail_links(data, files=None):
    calls = sum(len(d["invocations"]) for d in data["loops"].values())
    events = sum(len(d["events"]) for d in data["loops"].values())
    links = [ui.nav_link("calls", "Claude calls", "chat", ui.nav_count(calls))]
    if files is not None:
        links.append(ui.nav_link("files", "Files", "folder", ui.nav_count(files)))
    links += [ui.nav_link("questions", "Questions", "help"),
              ui.nav_link("events", "Events", "list", ui.nav_count(events))]
    return links


def render_page(data, ws_path):
    views = [overview_view(data), orchestrator_view(data)]
    views += [loop_view(loop, d, ws_path) for loop, d in data["loops"].items()]
    views += [calls_view(data), questions_view(data), events_view(data),
              full_dashboards_view(data)]
    details = detail_links(data)
    if data.get("full_dashboards"):
        details.append(ui.nav_link("full-dashboards", "Full dashboards", "history",
                                   ui.nav_count(len(data["full_dashboards"]))))
    refresh = REFRESH_SECONDS if data.get("running") else 0
    return ui.page(f"devloops · {data['workspace']}", sidebar(data, "dashboard", details),
                   ui.topbar(data["workspace"], pill(_overall_status(data), RUN_STATUS),
                             live=bool(refresh)),
                   [v for v in views if v], refresh=refresh)


def write(ws):
    """Render `workspaces/<ws>/dashboard.html` from state and return its path."""
    path = os.path.join(ws.path, FILENAME)
    state.write_text_atomic(path, render_page(collect(ws), ws.path))
    return path


def data_json(ws):
    """The collected data as JSON text (for tooling and tests)."""
    return json.dumps(collect(ws), default=str, indent=2)
