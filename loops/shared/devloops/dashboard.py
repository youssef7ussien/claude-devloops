"""`workspaces/<ws>/dashboard.html`: one self-contained page summarizing a workspace.

Everything is read from the workspace's state (`workspace.json`, each loop's `state/` and
`outputs/open-questions.md`, `orchestrator/state.json`); nothing is read back from the page. The
page has inline CSS, server-rendered SVG charts, and a few lines of JavaScript for tooltips and
the theme toggle, so it opens offline from disk. State is already redacted (FR-070); every value is
HTML-escaped here.
"""
import html
import json
import os
import re
from datetime import datetime

from . import render, state

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
    try:
        with open(os.path.join(loop_dir, "outputs", "open-questions.md"), encoding="utf-8") as f:
            answers = render.parse_answers(f.read())
    except OSError:
        answers = {}

    by_milestone = {}
    for rec in invocations:
        by_milestone.setdefault(rec.get("milestone_id"), []).append(rec)

    milestones = []
    for m in plan.get("milestones", []):
        mid = m["id"]
        ms = (run.get("milestones") or {}).get(mid, {})
        trials = []
        for summary in ms.get("trials", []):
            n = summary["n"]
            trial_dir = os.path.join(state_dir, "milestones", mid, "trials", str(n))
            doc = state.read_json(os.path.join(trial_dir, "trial.json")) or {}
            calls = [r for r in by_milestone.get(mid, []) if r.get("trial") == n]
            trials.append({
                "n": n, "kind": doc.get("kind") or ("implement" if n == 1 else "fix"),
                "status": summary["status"], "reason": summary.get("reason"),
                "detail": (doc.get("failure") or {}).get("detail"),
                "started_at": summary.get("started_at"), "ended_at": summary.get("ended_at"),
                "seconds": _seconds(summary.get("started_at"), summary.get("ended_at")),
                "cost": _cost(calls), "tokens": _tokens(calls),
                "sessions": [r.get("session_id") for r in calls],
                "validation": state.read_json(os.path.join(trial_dir, "validation.json")),
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
        "invocations": invocations, "events": events, "answers": answers,
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


def _path_link(relpath, text=None):
    return f'<a href="{e(relpath)}">{e(text or relpath)}</a>'


class FileLinks:
    """How a page refers to workspace files and URLs: here, links to the files on disk.

    The full dashboard (fulldash.py) substitutes links to the copies embedded in the page.
    """

    def path(self, relpath, text=None):
        return _path_link(relpath, text)

    def image(self, relpath, alt):
        return (f'<a href="{e(relpath)}"><img class="thumb" loading="lazy" src="{e(relpath)}" '
                f'alt="{e(alt)}"></a>')

    def url(self, url):
        return f'<a href="{e(url)}">{e(url)}</a>'


FILE_LINKS = FileLinks()


# --- charts -----------------------------------------------------------------------------------------

def bar_chart(rows, value_format, title, unit_label):
    """Horizontal single-hue bars: `rows` are `(label, value, tooltip)`. Values label the bar end."""
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
    table = "".join(f"<tr><td>{e(label)}</td><td class='num'>{e(value_format(value))}</td></tr>"
                    for label, value, _ in rows)
    return ("".join(parts) +
            f'<details class="table-view"><summary>Table view</summary><table><thead><tr>'
            f'<th>{e(unit_label[0])}</th><th class="num">{e(unit_label[1])}</th></tr></thead>'
            f'<tbody>{table}</tbody></table></details>')


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
            text, icon, tone = TRIAL_STATUS.get(t["status"], (t["status"], "•", "muted"))
            reason = t.get("reason") or (t.get("failure") or {}).get("reason")
            tip = (f"{name} — {icon} {text}" + (f": {reason}" if reason else "") +
                   f" · {duration(_seconds(t.get('started_at'), t.get('ended_at')))}")
            parts.append(f'<g class="mark" tabindex="0" data-tip="{e(tip)}">'
                         f'<rect class="seg tone-{tone}" x="{x:.1f}" y="{y + 5}" width="{w:.1f}" '
                         f'height="{row_h - 12}" rx="4"/></g>')
    parts.append("</svg>")
    legend = "".join(f'<span class="legend-item"><span class="swatch tone-{tone}"></span>'
                     f'<span aria-hidden="true">{icon}</span> {e(text)}</span>'
                     for text, icon, tone in TRIAL_STATUS.values())
    return f'<div class="legend">{legend}</div>' + "".join(parts)


# --- sections ---------------------------------------------------------------------------------------

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
    return '<section class="kpis">' + "".join([
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
                f"<code>open-questions.md</code>, then <code>devloops approve {e(loop)}</code> "
                f"or <code>devloops replan {e(loop)}</code>.")
    if status == "stopped-on-failure" and code == "needs-input":
        return (f"Answer the new questions in <code>open-questions.md</code>, then "
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


def loop_section(loop, d, ws_path, links=FILE_LINKS):
    s = d["stats"]
    reason = d["status_reason"] or {}
    head = [f'<h2 id="{e(loop)}">{e(loop)} {pill(d["status"], RUN_STATUS)}</h2>']
    if reason:
        head.append(f'<p class="reason"><strong>{e(reason.get("code"))}</strong>: '
                    f'{e(reason.get("message"))}</p>')
    action = _next_action(loop, d)
    if action:
        head.append(f'<p class="action"><span aria-hidden="true">→</span> {action}</p>')
    rate = f"{100 * s['first_try'] / s['achieved']:.0f}%" if s["achieved"] else "–"
    head.append('<div class="kpis small">' + "".join([
        _kpi("Milestones", f"{s['achieved']} / {s['milestones']}"),
        _kpi("First-try", rate), _kpi("Trials", str(s["trials"])),
        _kpi("Calls", str(s["calls"])), _kpi("Cost", e(money(s["cost"]))),
        _kpi("Elapsed", e(duration(s["seconds"]))),
    ]) + "</div>")

    outputs = [links.path(f"{loop}/progress.md", "progress.md"),
               links.path(f"{loop}/outputs/plan-summary.md", "plan summary")]
    if os.path.exists(os.path.join(ws_path, loop, "outputs", "final-report.md")):
        outputs.append(links.path(f"{loop}/outputs/final-report.md", "final report"))
    if d["openapi_artifact"]:
        outputs.append(links.path(f"{loop}/{d['openapi_artifact']['path']}", "OpenAPI document"))
    if d["ui_url"]:
        outputs.append(f'UI: {links.url(d["ui_url"])}')
    head.append('<p class="outputs">' + " · ".join(outputs) + "</p>")

    plan = d["plan"]
    if plan:
        stack = plan.get("stack") or {}
        runtime = plan.get("runtime") or {}
        head.append('<div class="grid2"><div class="card"><h3>Stack</h3>'
                    f'<p>{e(stack.get("summary"))}</p><p class="muted">Source: '
                    f'{e(stack.get("source"))}</p></div><div class="card"><h3>Runtime</h3><dl>'
                    + "".join(f"<dt>{e(k)}</dt><dd><code>{e(v)}</code></dd>"
                              for k, v in runtime.items() if v)
                    + f'</dl><p class="muted">Target: <code>{e(d["target_dir"])}</code></p>'
                      '</div></div>')

    body = ["<h3>Milestones</h3>"]
    for m in d["milestones"]:
        body.append(milestone_card(loop, m, links))
    if not d["milestones"]:
        body.append('<p class="muted">No plan stored yet.</p>')
    return f'<section class="loop">{"".join(head)}{"".join(body)}</section>'


def milestone_card(loop, m, links=FILE_LINKS):
    last = m["trials"][-1] if m["trials"] else None
    validation = (last or {}).get("validation") or {}
    results = {c["criterion_id"]: c for c in validation.get("criteria", [])}
    open_attr = "" if m["status"] == "achieved" else " open"
    parts = [f'<details class="milestone"{open_attr}><summary><span class="mid">{e(m["id"])}</span> '
             f'{e(m["title"])} {pill(m["status"], MILESTONE_STATUS)}'
             f'<span class="summary-meta">{len(m["trials"])} trial(s) · {e(money(m["cost"]))} · '
             f'{e(duration(m["seconds"]))}</span></summary>']
    if m.get("goal"):
        parts.append(f'<p class="goal">{e(m["goal"])}</p>')
    if m["depends_on"]:
        parts.append(f'<p class="muted">Depends on {e(", ".join(m["depends_on"]))}</p>')

    parts.append("<h4>Tasks</h4><ul class='tasks'>")
    for t in m["tasks"]:
        done = t["status"] == "achieved"
        parts.append(f'<li><span class="check {"on" if done else ""}" aria-label="'
                     f'{"achieved" if done else e(t["status"])}">{"✓" if done else "○"}</span> '
                     f'<strong>{e(t["id"])}</strong> {e(t["title"])} '
                     f'<span class="refs">{e(", ".join(t.get("requirement_refs") or []))}</span>'
                     f'<div class="muted small">{e(t.get("description"))}</div></li>')
    parts.append("</ul>")

    parts.append("<h4>Acceptance criteria"
                 + (f" <span class='muted'>(trial {last['n']} validation)</span>" if last else "")
                 + "</h4><table><thead><tr><th>Criterion</th><th>Result</th><th>Observed</th>"
                   "<th>Evidence</th></tr></thead><tbody>")
    for c in m["criteria"]:
        r = results.get(c["id"])
        if r is None:
            result = pill("pending", MILESTONE_STATUS).replace("Pending", "Not validated")
        else:
            result = pill("passed" if r["passed"] else "failed", TRIAL_STATUS)
        evidence = ""
        if r and last:
            items = []
            for item in r.get("evidence") or []:
                rel = os.path.join(os.path.dirname(last["evidence_dir"]), item)
                if item.lower().endswith(IMAGE_EXTENSIONS):
                    items.append(links.image(rel, os.path.basename(item)))
                else:
                    items.append(links.path(rel, os.path.basename(item)))
            evidence = " ".join(items)
        parts.append(f'<tr><td><strong>{e(c["id"])}</strong> {e(c["text"])}</td><td>{result}</td>'
                     f'<td>{e((r or {}).get("observed"))}</td><td>{evidence}</td></tr>')
    parts.append("</tbody></table>")

    checks = validation.get("checks") or []
    if checks:
        parts.append("<h4>HTTP checks</h4><table><thead><tr><th>Check</th><th>Result</th>"
                     "<th>Command</th><th class='num'>Status</th></tr></thead><tbody>")
        for c in checks:
            failures = "; ".join(c.get("failures") or [])
            parts.append(f'<tr><td>{e(c["check_id"])}</td><td>'
                         f'{pill("passed" if c["passed"] else "failed", TRIAL_STATUS)}'
                         f'{"<div class=small>" + e(failures) + "</div>" if failures else ""}</td>'
                         f'<td><code class="cmd">{e(c.get("command"))}</code></td>'
                         f'<td class="num">{e((c.get("response") or {}).get("status"))}</td></tr>')
        parts.append("</tbody></table>")
    requests = validation.get("network_requests") or []
    if requests:
        parts.append("<h4>Network requests seen by the browser</h4><table><thead><tr>"
                     "<th>Method</th><th>URL</th><th class='num'>Status</th></tr></thead><tbody>")
        for r in requests:
            parts.append(f"<tr><td>{e(r.get('method'))}</td><td><code>{e(r.get('url'))}</code></td>"
                         f"<td class='num'>{e(r.get('status'))}</td></tr>")
        parts.append("</tbody></table>")
    contract = validation.get("contract")
    if contract:
        unmatched = contract.get("unmatched_operations") or []
        parts.append(f'<p>API contract: {pill("passed" if contract.get("passed") else "failed", TRIAL_STATUS)}'
                     + (f' Unmatched: <code>{e(", ".join(unmatched))}</code>' if unmatched else "")
                     + "</p>")

    parts.append("<h4>Trials</h4><table><thead><tr><th>#</th><th>Kind</th><th>Result</th>"
                 "<th>Detail</th><th class='num'>Duration</th><th class='num'>Cost</th>"
                 "<th>Sessions</th></tr></thead><tbody>")
    for t in m["trials"]:
        status = pill(t["status"], TRIAL_STATUS)
        reason = f'<strong>{e(t["reason"])}</strong>: ' if t["reason"] else ""
        detail = (t["detail"] or "")
        parts.append(f'<tr><td>{t["n"]}</td><td>{e(t["kind"])}</td><td>{status}</td>'
                     f'<td class="detail">{reason}{e(detail[:600])}'
                     f'{"…" if len(detail) > 600 else ""}</td>'
                     f'<td class="num">{e(duration(t["seconds"]))}</td>'
                     f'<td class="num">{e(money(t["cost"]))}</td>'
                     f'<td><code class="small">{e(" ".join(s[:8] for s in t["sessions"] if s))}'
                     f'</code></td></tr>')
    if not m["trials"]:
        parts.append('<tr><td colspan="7" class="muted">No trials yet.</td></tr>')
    parts.append("</tbody></table></details>")
    return "".join(parts)


def questions_section(data):
    rows = []
    for loop, d in data["loops"].items():
        planned = {q["id"]: q for q in (d["plan"].get("open_questions") or [])}
        ids = list(dict.fromkeys(list(planned) + list(d["answers"])))
        for qid in ids:
            q = planned.get(qid, {})
            question, answer = d["answers"].get(qid, (q.get("question"), ""))
            rows.append(f"<tr><td>{e(loop)}</td><td><strong>{e(qid)}</strong></td>"
                        f"<td>{e(question or q.get('question'))}</td>"
                        f"<td>{e(answer) if answer else '<span class=muted>Unanswered</span>'}"
                        f"</td></tr>")
    assumptions = []
    for loop, d in data["loops"].items():
        for a in d["plan"].get("assumptions") or []:
            assumptions.append(f"<tr><td>{e(loop)}</td><td><strong>{e(a['id'])}</strong></td>"
                               f"<td>{e(a['text'])}</td><td class='muted'>{e(a.get('source'))}</td>"
                               "</tr>")
    grants = []
    for loop, d in data["loops"].items():
        for g in d["grants"]:
            grants.append(f"<tr><td>{e(loop)}</td><td>{e(g.get('milestone_id'))}</td>"
                          f"<td class='num'>{e(g.get('extra_trials'))}</td><td>{e(g.get('reason'))}"
                          f"</td><td class='muted'>{e(g.get('granted_at'))}</td></tr>")
    out = ['<section><h2 id="decisions">Questions, assumptions, and retries</h2>']
    out.append("<h3>Open questions</h3>" + (
        "<table><thead><tr><th>Loop</th><th>ID</th><th>Question</th><th>Answer</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>" if rows else
        '<p class="muted">No questions were raised.</p>'))
    out.append("<h3>Planning assumptions</h3>" + (
        "<table><thead><tr><th>Loop</th><th>ID</th><th>Assumption</th><th>Source</th></tr>"
        f"</thead><tbody>{''.join(assumptions)}</tbody></table>" if assumptions else
        '<p class="muted">None recorded.</p>'))
    if grants:
        out.append("<h3>Retries granted</h3><table><thead><tr><th>Loop</th><th>Milestone</th>"
                   "<th class='num'>Trials</th><th>Reason</th><th>Granted</th></tr></thead>"
                   f"<tbody>{''.join(grants)}</tbody></table>")
    return "".join(out) + "</section>"


def sessions_section(data, links=FILE_LINKS):
    rows, events = [], []
    for loop, d in data["loops"].items():
        for r in d["invocations"]:
            tokens = sum((r.get("tokens") or {}).get(k) or 0
                         for k in ("input", "output", "cache_creation", "cache_read"))
            prompt = r.get("prompt_path")
            rows.append(
                f"<tr><td>{e(loop)}</td><td>{e(r.get('step'))}</td>"
                f"<td>{e(r.get('milestone_id') or 'planning')}</td><td class='num'>{e(r.get('trial'))}</td>"
                f"<td><code class='small'>{e(r.get('session_id'))}</code></td>"
                f"<td>{links.path(f'{loop}/{prompt}', 'prompt') if prompt else ''}</td>"
                f"<td class='num'>{e(number(tokens))}</td><td class='num'>{e(money(r.get('cost_usd')))}</td>"
                f"<td class='num'>{e(duration((r.get('duration_ms') or 0) / 1000))}</td>"
                f"<td>{'' if r.get('failure_class') in (None, 'none') else e(r.get('failure_class'))}"
                "</td></tr>")
        for ev in d["events"]:
            events.append((ev.get("at") or "", loop, ev))
    events.sort(key=lambda x: x[0])
    ev_rows = "".join(
        f"<tr><td class='muted small'>{e(at)}</td><td>{e(loop)}</td><td>{e(ev.get('type'))}</td>"
        f"<td>{e(ev.get('milestone'))}</td><td>{e(ev.get('message'))}</td></tr>"
        for at, loop, ev in events)
    return ('<section><h2 id="sessions">Claude sessions and events</h2>'
            f'<details><summary>All {len(rows)} Claude call(s)</summary><table><thead><tr>'
            "<th>Loop</th><th>Step</th><th>Milestone</th><th class='num'>Trial</th>"
            "<th>Session</th><th>Prompt</th><th class='num'>Tokens</th><th class='num'>Cost</th>"
            "<th class='num'>Duration</th><th>Failure</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table></details>"
            f'<details><summary>Event log ({len(events)} events)</summary><table><thead><tr>'
            "<th>Time</th><th>Loop</th><th>Type</th><th>Milestone</th><th>Message</th></tr></thead>"
            f"<tbody>{ev_rows}</tbody></table></details></section>")


def charts_section(data):
    cost_rows, step_rows = [], []
    for loop, d in data["loops"].items():
        cost_rows.append((f"{loop} · Planning", d["planning_cost"],
                          f"{loop} planning: {money(d['planning_cost'])}"))
        for m in d["milestones"]:
            cost_rows.append((f"{loop} · {m['id']}", m["cost"],
                              f"{loop} {m['id']} {m['title']}: {money(m['cost'])} over "
                              f"{m['calls']} call(s), {len(m['trials'])} trial(s)"))
    steps = {}
    for d in data["loops"].values():
        for step, v in d["by_step"].items():
            agg = steps.setdefault(step, {"calls": 0, "cost": 0.0, "tokens": 0})
            for k in agg:
                agg[k] += v[k]
    for step, v in sorted(steps.items(), key=lambda kv: -kv[1]["cost"]):
        step_rows.append((step, v["cost"], f"{step}: {money(v['cost'])} over {v['calls']} "
                                           f"call(s), {number(v['tokens'])} tokens"))
    return ('<section><h2 id="timeline">Trial timeline</h2>'
            '<div class="card">' + timeline(data) + "</div>"
            '<div class="grid2"><div class="card"><h3>Cost by milestone</h3>'
            + bar_chart(cost_rows, money, "Cost by milestone", ("Milestone", "Cost"))
            + '</div><div class="card"><h3>Cost by step</h3>'
            + bar_chart(step_rows, money, "Cost by step", ("Step", "Cost"))
            + "</div></div></section>")


def orchestrator_section(data):
    orch = data["orchestrator"]
    if not orch:
        return ""
    steps = "".join(f"<tr><td>{e(s['loop'])}</td><td>{pill(s['status'], RUN_STATUS)}</td>"
                    f"<td>{e(s.get('reason'))}</td><td class='muted small'>{e(s.get('started_at'))}"
                    f"</td><td class='muted small'>{e(s.get('ended_at'))}</td></tr>"
                    for s in orch.get("steps") or [])
    handoff = orch.get("handoff") or {}
    spec = handoff.get("api_spec") or {}
    runtime = handoff.get("backend_runtime") or {}
    hand = ""
    if handoff:
        hand = ("<h3>Handoff</h3><dl>"
                f"<dt>API spec</dt><dd><code>{e(spec.get('path'))}</code><div class='muted small'>"
                f"sha256 {e(spec.get('sha256'))}</div></dd>"
                + "".join(f"<dt>Backend {e(k)}</dt><dd><code>{e(v)}</code></dd>"
                          for k, v in runtime.items()) + "</dl>")
    return (f'<section><h2 id="orchestrator">Orchestrator {pill(orch.get("status"), {"running": ("Running", "◷", "neutral"), "paused": ("Paused", "⏸", "warning"), "completed": ("Completed", "✓", "good"), "stopped": ("Stopped", "✕", "critical")})}</h2>'
            "<table><thead><tr><th>Loop</th><th>Status</th><th>Reason</th><th>Started</th>"
            f"<th>Ended</th></tr></thead><tbody>{steps}</tbody></table>{hand}</section>")


# --- page -------------------------------------------------------------------------------------------

CSS = """
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink-2:#52514e;
--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;--border:rgba(11,11,11,.10);--series:#2a78d6;
--good:#0ca30c;--warning:#fab219;--serious:#ec835a;--critical:#d03b3b;--neutral:#2a78d6;
--good-ink:#006300;--chip:#f0efec}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--page:#0d0d0d;
--surface:#1a1a19;--ink:#fff;--ink-2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;
--border:rgba(255,255,255,.10);--series:#3987e5;--neutral:#3987e5;--good-ink:#0ca30c;--chip:#383835}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#fff;
--ink-2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--border:rgba(255,255,255,.10);
--series:#3987e5;--neutral:#3987e5;--good-ink:#0ca30c;--chip:#383835}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:14px/1.5 system-ui,-apple-system,
"Segoe UI",sans-serif}
header.top{position:sticky;top:0;z-index:5;background:var(--surface);border-bottom:1px solid
var(--border);padding:12px 24px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
header.top h1{font-size:18px;margin:0}
header.top nav{display:flex;gap:12px;flex-wrap:wrap;font-size:13px}
header.top .spacer{flex:1}
main{max-width:1240px;margin:0 auto;padding:20px 24px 60px}
a{color:var(--series)}
h2{font-size:20px;margin:32px 0 12px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
h3{font-size:15px;margin:18px 0 8px}h4{font-size:13px;margin:16px 0 6px;color:var(--ink-2)}
.meta{color:var(--ink-2);font-size:13px;margin:4px 0 0}
.muted{color:var(--muted)}.small{font-size:12px}
code{font:12px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;background:var(--chip);
padding:1px 5px;border-radius:4px;word-break:break-all}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(128px,1fr));gap:12px;margin:16px 0}
.kpis.small{grid-template-columns:repeat(auto-fill,minmax(120px,1fr))}
.tile,.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:12px 14px}
.tile-label{color:var(--ink-2);font-size:12px}
.tile-value{font-size:24px;font-weight:600;margin-top:2px}
.kpis.small .tile-value{font-size:18px}
.tile-sub{color:var(--muted);font-size:11px}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(380px,1fr));gap:16px;margin:16px 0}
.card{overflow-x:auto}
.pill{display:inline-flex;gap:4px;align-items:center;font-size:12px;font-weight:600;
padding:2px 9px;border-radius:999px;border:1px solid var(--border);background:var(--chip);color:var(--ink);white-space:nowrap}
.pill.tone-good{box-shadow:inset 3px 0 0 var(--good)}.pill.tone-critical{box-shadow:inset 3px 0 0 var(--critical)}
.pill.tone-warning{box-shadow:inset 3px 0 0 var(--warning)}.pill.tone-serious{box-shadow:inset 3px 0 0 var(--serious)}
.pill.tone-neutral{box-shadow:inset 3px 0 0 var(--neutral)}.pill.tone-muted{color:var(--ink-2)}
.pill.tone-good span[aria-hidden]{color:var(--good-ink)}.pill.tone-critical span[aria-hidden]{color:var(--critical)}
table{width:100%;border-collapse:collapse;font-size:13px;margin:6px 0 10px;background:var(--surface)}
th,td{text-align:left;padding:7px 9px;border-bottom:1px solid var(--grid);vertical-align:top}
th{color:var(--ink-2);font-weight:600;font-size:12px}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
td.detail{max-width:420px}
code.cmd{white-space:pre-wrap}
details{margin:8px 0}
details>summary{cursor:pointer;color:var(--ink-2);font-weight:600}
details.milestone{background:var(--surface);border:1px solid var(--border);border-radius:10px;
padding:10px 14px}
details.milestone>summary{color:var(--ink);display:flex;gap:10px;align-items:center;flex-wrap:wrap;font-size:14px}
.mid{font-weight:700}.summary-meta{margin-left:auto;color:var(--muted);font-weight:400;font-size:12px}
.goal{color:var(--ink-2)}
.tasks{list-style:none;padding:0;margin:0}.tasks li{padding:5px 0;border-bottom:1px solid var(--grid)}
.check{display:inline-block;width:18px;color:var(--muted)}.check.on{color:var(--good-ink);font-weight:700}
.refs{color:var(--muted);font-size:12px}
.thumb{height:64px;border-radius:6px;border:1px solid var(--border);margin:2px}
.reason{margin:4px 0}.action{background:var(--surface);border:1px solid var(--border);
border-left:3px solid var(--warning);border-radius:8px;padding:8px 12px}
.outputs{font-size:13px}
dl{display:grid;grid-template-columns:max-content 1fr;gap:4px 12px;margin:0;font-size:13px}
dt{color:var(--ink-2)}dd{margin:0}
.alert{border-left:3px solid var(--serious);background:var(--surface);padding:10px 14px;border-radius:8px}
svg.chart{max-width:100%;height:auto;display:block;font-size:12px}
svg .axis-label{fill:var(--ink-2)}svg .value-label{fill:var(--ink);font-weight:600}
svg .grid{stroke:var(--grid);stroke-width:1}svg .baseline{stroke:var(--axis);stroke-width:1}
svg .bar{fill:var(--series)}svg .hit{fill:transparent}
svg .mark:hover .bar,svg .mark:focus .bar{opacity:.8}svg .mark:focus{outline:none}
svg .seg{stroke:var(--surface);stroke-width:2}
svg .seg.tone-good,.swatch.tone-good{fill:var(--good);background:var(--good)}
svg .seg.tone-critical,.swatch.tone-critical{fill:var(--critical);background:var(--critical)}
svg .seg.tone-serious,.swatch.tone-serious{fill:var(--serious);background:var(--serious)}
svg .seg.tone-neutral,.swatch.tone-neutral{fill:var(--neutral);background:var(--neutral)}
svg .seg.tone-muted,.swatch.tone-muted{fill:var(--muted);background:var(--muted)}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:var(--ink-2);margin-bottom:8px}
.legend-item{display:inline-flex;gap:5px;align-items:center}
.swatch{width:12px;height:12px;border-radius:3px;display:inline-block}
#tip{position:fixed;pointer-events:none;z-index:10;background:var(--surface);color:var(--ink);
border:1px solid var(--border);box-shadow:0 4px 14px rgba(0,0,0,.18);border-radius:8px;
padding:6px 10px;font-size:12px;max-width:340px;display:none}
button.theme{font:inherit;font-size:12px;border:1px solid var(--border);background:var(--chip);
color:var(--ink);border-radius:8px;padding:4px 10px;cursor:pointer}
@media (max-width:640px){main{padding:16px}header.top{padding:10px 16px}.grid2{grid-template-columns:1fr}}
"""

JS = """
(function(){
  var root=document.documentElement,btn=document.getElementById('theme');
  function apply(t){if(t){root.setAttribute('data-theme',t)}else{root.removeAttribute('data-theme')}}
  try{apply(localStorage.getItem('devloops-theme'))}catch(e){}
  if(btn){btn.addEventListener('click',function(){
    var dark=root.getAttribute('data-theme')==='dark'||(!root.getAttribute('data-theme')&&
      window.matchMedia('(prefers-color-scheme: dark)').matches);
    var next=dark?'light':'dark';apply(next);try{localStorage.setItem('devloops-theme',next)}catch(e){}
  })}
  var tip=document.getElementById('tip');
  function show(el,x,y){tip.textContent=el.getAttribute('data-tip');tip.style.display='block';
    var w=tip.offsetWidth,h=tip.offsetHeight;
    tip.style.left=Math.min(x+14,window.innerWidth-w-8)+'px';tip.style.top=Math.max(8,y-h-10)+'px'}
  function hide(){tip.style.display='none'}
  document.querySelectorAll('[data-tip]').forEach(function(el){
    el.addEventListener('mousemove',function(ev){show(el,ev.clientX,ev.clientY)});
    el.addEventListener('mouseleave',hide);
    el.addEventListener('focus',function(){var r=el.getBoundingClientRect();show(el,r.left,r.top)});
    el.addEventListener('blur',hide);
  });
})();
"""


def nav_links(data):
    nav = "".join(f'<a href="#{e(loop)}">{e(loop)}</a>' for loop in data["loops"])
    nav += ('<a href="#timeline">Timeline</a><a href="#decisions">Questions</a>'
            '<a href="#sessions">Sessions</a>')
    if data["orchestrator"]:
        nav = '<a href="#orchestrator">Orchestrator</a>' + nav
    return nav


def large_evidence_alert(data, links=FILE_LINKS):
    if not data["large_evidence"]:
        return ""
    return ('<p class="alert"><strong>Review before committing:</strong> evidence files over '
            '1 MB, the likeliest place for a secret to hide: '
            + ", ".join(links.path(i["path"]) + f" ({number(i['bytes'])}B)"
                        for i in data["large_evidence"]) + "</p>")


def header(title, nav):
    return (f'<header class="top"><h1>{e(title)}</h1><nav>{nav}</nav>'
            '<span class="spacer"></span><button class="theme" id="theme" type="button">'
            'Toggle theme</button></header>')


def summary_sections(data, ws_path, links=FILE_LINKS):
    """The body shared by both dashboards: KPIs, orchestrator, charts, loops, and sessions."""
    body = [kpi_row(data), large_evidence_alert(data, links)]
    if not data["loops"]:
        body.append('<p class="muted">No loop has started in this workspace yet.</p>')
    body.append(orchestrator_section(data))
    if data["loops"]:
        body.append(charts_section(data))
    for loop, d in data["loops"].items():
        body.append(loop_section(loop, d, ws_path, links))
    if data["loops"]:
        body.append(questions_section(data))
        body.append(sessions_section(data, links))
    return body


def page(title, body, css=""):
    """A complete page: inline styles, `body` (a list of HTML strings), and the one script."""
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<title>{e(title)}</title><style>{CSS}{css}</style></head><body>"
            + "".join(body) + f'<div id="tip" role="tooltip"></div><script>{JS}</script>'
            "</body></html>\n")


def full_dashboards_section(data):
    """Links to the workspace's full dashboards, newest first (002 FR-036a)."""
    items = data.get("full_dashboards") or []
    if not items:
        return ""
    rows = "".join(f"<li>{_path_link(i['link'], i['name'])} "
                   f"<span class='muted small'>{e(number(i['bytes']))}B</span></li>"
                   for i in items)
    return ('<section><h2 id="full-dashboards">Full dashboards</h2><p class="muted">'
            'Self-contained pages with every artifact and Claude Code conversation, newest first. '
            f'They contain full conversations: review before sharing.</p><ul>{rows}</ul></section>')


def render_page(data, ws_path):
    req = data["requirements"]
    mode = req.get("mode")
    selection = f" · story {req.get('story_id')}" if req.get("story_id") else ""
    nav = nav_links(data)
    if data.get("full_dashboards"):
        nav += '<a href="#full-dashboards">Full dashboards</a>'
    body = [
        header(f"devloops · {data['workspace']}", nav), "<main>",
        f'<p class="meta">Requirements <code>{e(req.get("path"))}</code> · mode '
        f'{e(mode)}{e(selection)} · generated {e(data["generated_at"])}</p>',
        *summary_sections(data, ws_path),
        full_dashboards_section(data),
        "</main>",
    ]
    return page(f"devloops · {data['workspace']}", body)


def write(ws):
    """Render `workspaces/<ws>/dashboard.html` from state and return its path."""
    path = os.path.join(ws.path, FILENAME)
    state.write_text_atomic(path, render_page(collect(ws), ws.path))
    return path


def data_json(ws):
    """The collected data as JSON text (for tooling and tests)."""
    return json.dumps(collect(ws), default=str, indent=2)
