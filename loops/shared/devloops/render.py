"""Markdown views rendered from state (FR-002–004b, FR-034, FR-058).

Every view is regenerated from `state/` and never read back as input. The one exception is the
developer's answers in `outputs/open-questions.md`, which is an input file: re-rendering keeps an
answer when the same question (same ID and text) is still open.
"""
import json
import os
import re

from . import selector, state

STOPPED = ("stopped-on-failure", "stopped-on-input-error", "stopped-on-service-error")
TOKEN_FIELDS = (("input", "Input"), ("output", "Output"), ("cache_creation", "Cache creation"),
                ("cache_read", "Cache read"))


def slug(title, limit=40):
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s[:limit].rstrip("-") or "milestone"


def milestone_filename(milestone):
    return f"milestone-{milestone['id'][1:]}-{slug(milestone['title'])}.md"


def _cell(value):
    if value is None or value == "":
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ")


def _table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(_cell(v) for v in row) + " |" for row in rows]
    return "\n".join(lines)


def _refs(refs):
    return ", ".join(refs) if refs else "none"


def _reason(trial):
    return (trial.get("failure") or {}).get("reason") or trial.get("reason")


# --- Milestone file ----------------------------------------------------------------------------

def render_milestone(milestone, ms_state, trials):
    """`trials` are the milestone's `trial.json` documents, in order."""
    tasks = ms_state.get("tasks", {})
    lines = [f"# {milestone['id']}: {milestone['title']}", "",
             f"- **Status**: {ms_state.get('status', 'pending')}",
             f"- **Goal**: {milestone['goal']}",
             f"- **Depends on**: {_refs(milestone['depends_on'])}", "", "## Tasks", ""]
    for task in milestone["tasks"]:
        status = tasks.get(task["id"], "pending")
        box = "x" if status == "achieved" else " "
        lines.append(f"- [{box}] **{task['id']}** {task['title']} ({status}): "
                     f"{task['description']} (refs: {_refs(task['requirement_refs'])})")
    lines += ["", "## Acceptance criteria", ""]
    for c in milestone["acceptance_criteria"]:
        lines.append(f"- **{c['id']}** {c['text']} (refs: {_refs(c['requirement_refs'])})")
    lines += ["", "## Trials", ""]
    if trials:
        lines.append(_table(["Trial", "Kind", "Status", "Reason", "Started", "Ended"],
                            [[t["n"], t.get("kind"), t["status"], _reason(t), t.get("started_at"),
                              t.get("ended_at")] for t in trials]))
    else:
        lines.append("_No trials yet._")
    lines += ["", "## Assumptions", ""]
    assumptions = [(t["n"], a) for t in trials for a in t.get("assumptions") or []]
    if assumptions:
        for n, a in assumptions:
            lines.append(f"- {a['text']} (trial {n}; affects: {_refs(a.get('affects'))})")
    else:
        lines.append("_None._")
    return "\n".join(lines) + "\n"


# --- progress.md ------------------------------------------------------------------------------

def _sum_tokens(records):
    """Sum each counter; a counter missing from any record is `unavailable`."""
    sums = {}
    for key, _ in TOKEN_FIELDS:
        values = [(r.get("tokens") or {}).get(key) for r in records]
        sums[key] = "unavailable" if any(v is None for v in values) else sum(values)
    costs = [r.get("cost_usd") for r in records]
    sums["cost"] = "unavailable" if any(c is None for c in costs) else f"{sum(costs):.4f}"
    return sums


def _usage_row(label, status, start, end, records):
    if not records:
        return [label, status, start, end, "", "", "", "", "", ""]
    sums = _sum_tokens(records)
    return [label, status, start, end, *[sums[k] for k, _ in TOKEN_FIELDS], sums["cost"],
            ", ".join(r["session_id"] for r in records)]


def _trial_dir_rel(mid, n):
    return f"state/milestones/{mid}/trials/{n}"


def render_progress(loop, workspace_name, run, plan, events, invocations, trials_by_mid):
    status = run.get("status", "not-started")
    lines = [f"# Progress: {loop}", "", f"- **Workspace**: {workspace_name}",
             f"- **Status**: {status}", f"- **Target**: {run.get('target_dir')}",
             f"- **Claude calls**: {run.get('invocation_count', 0)} of "
             f"{(run.get('effective_config') or {}).get('max_invocations_per_run')}"]
    if run.get("ui_url"):
        lines.append(f"- **UI URL**: {run['ui_url']}")
    if run.get("openapi_artifact"):
        lines.append(f"- **OpenAPI artifact**: {run['openapi_artifact'].get('path')}")

    if status in STOPPED:
        reason = run.get("status_reason") or {}
        lines += ["", "## Stop", "", f"- **Status**: {status}",
                  f"- **Reason**: {reason.get('code')}: {reason.get('message')}"]
        mid = reason.get("milestone_id")
        if mid and mid in (run.get("milestones") or {}):
            ms = run["milestones"][mid]
            used = len(selector.counted_trials(ms))
            lines += [f"- **Milestone**: {mid}",
                      f"- **Trials used**: {used} of {selector.trial_limit(run, mid)}"]
            docs = trials_by_mid.get(mid) or []
            if docs:
                last = docs[-1]
                rel = _trial_dir_rel(mid, last["n"])
                if last.get("validation"):
                    lines += [f"- **Last validation**: [{rel}/validation.json]({rel}/validation.json)",
                              f"- **Evidence**: [{rel}/evidence/]({rel}/evidence/)"]
                else:
                    lines.append(f"- **Last validation**: none (trial {last['n']} failed before "
                                 f"validation: {_reason(last)}; see {rel}/trial.json)")
        for key in ("input", "tool"):
            if reason.get(key):
                lines.append(f"- **{key.capitalize()}**: {reason[key]}")

    lines += ["", "## Milestones", ""]
    headers = ["Milestone", "Status", "Start", "End", *[h for _, h in TOKEN_FIELDS], "Cost (USD)",
               "Sessions"]
    planning = run.get("planning") or {}
    ptrials = planning.get("trials") or []
    rows = [_usage_row("Planning", planning.get("status", ""),
                       ptrials[0].get("started_at") if ptrials else None,
                       ptrials[-1].get("ended_at") if ptrials else None,
                       [r for r in invocations if r.get("milestone_id") is None])]
    for m in (plan or {}).get("milestones", []):
        ms = (run.get("milestones") or {}).get(m["id"], {})
        trials = ms.get("trials") or []
        rows.append(_usage_row(f"{m['id']} {m['title']}", ms.get("status", "pending"),
                               trials[0].get("started_at") if trials else None, ms.get("ended_at"),
                               [r for r in invocations if r.get("milestone_id") == m["id"]]))
    lines.append(_table(headers, rows))

    lines += ["", "## Trials", ""]
    trial_rows = [["planning", t["n"], t.get("kind"), t["status"], _reason(t), t.get("started_at"),
                   t.get("ended_at")] for t in ptrials]
    for m in (plan or {}).get("milestones", []):
        for t in trials_by_mid.get(m["id"], []):
            trial_rows.append([m["id"], t["n"], t.get("kind"), t["status"], _reason(t),
                               t.get("started_at"), t.get("ended_at")])
    lines.append(_table(["Milestone", "Trial", "Kind", "Status", "Reason", "Start", "End"],
                        trial_rows) if trial_rows else "_No trials yet._")

    lines += ["", "## Action items", ""]
    if events:
        for e in events:
            where = " · ".join(str(x) for x in (e.get("milestone"),
                                                 f"trial {e['trial']}" if e.get("trial") else None)
                               if x)
            lines.append(f"- {e['at']} **{e['type']}**" + (f" ({where})" if where else "")
                         + f": {e['message']}")
    else:
        lines.append("_No actions yet._")
    return "\n".join(lines) + "\n"


# --- plan-summary.md ----------------------------------------------------------------------------

def render_plan_summary(plan):
    stack, runtime = plan["stack"], plan["runtime"]
    lines = ["# Plan summary", "", "## Stack", "", f"- **Summary**: {stack['summary']}",
             f"- **Source**: {stack['source']}"]
    if stack["conflicts"]:
        lines.append("- **Conflicts**:")
        lines += [f"  - {c}" for c in stack["conflicts"]]
    else:
        lines.append("- **Conflicts**: none")
    lines += ["", "## Runtime", ""]
    for key in ("install_command", "start_command", "cwd", "base_url", "ready_url",
                "unit_test_command", "openapi_path"):
        if runtime.get(key):
            lines.append(f"- **{key}**: `{runtime[key]}`")
    lines += ["", "## Milestones", ""]
    for m in plan["milestones"]:
        lines.append(f"- **{m['id']}** {m['title']} (depends on: {_refs(m['depends_on'])}; "
                     f"{len(m['tasks'])} task(s), {len(m['acceptance_criteria'])} criteria)")
    lines += ["", "## Requirements covered", ""]
    lines += [f"- **{r['ref']}** {r['summary']}" for r in plan["requirements_inventory"]]
    lines += ["", "## Planning assumptions", ""]
    lines += ([f"- **{a['id']}** {a['text']} (source: {a['source']})" for a in plan["assumptions"]]
              or ["_None._"])
    lines += ["", f"Open questions: {len(plan['open_questions'])} (see open-questions.md)"]
    return "\n".join(lines) + "\n"


# --- task.md ------------------------------------------------------------------------------------

def render_task(template, values):
    """Replace every `{{name}}` placeholder; `None` renders as `none`."""
    def replace(match):
        value = values.get(match.group(1), match.group(0))
        if value is None:
            return "none"
        return value if isinstance(value, str) else json.dumps(value, indent=2)
    return re.sub(r"\{\{([a-z_0-9]+)\}\}", replace, template)


def task_values(run, workspace_name):
    req = (run.get("inputs") or {}).get("requirements") or {}
    api = (run.get("inputs") or {}).get("api_spec") or {}
    return {
        "workspace": workspace_name,
        "requirements_path": req.get("path"),
        "requirements_sha256": req.get("sha256"),
        "mode": req.get("mode"),
        "story_id": req.get("story_id"),
        "target_dir": run.get("target_dir"),
        "api_spec_path": api.get("path"),
        "effective_config": "```json\n" + json.dumps(run.get("effective_config"), indent=2)
                            + "\n```",
    }


# --- open-questions.md ---------------------------------------------------------------------------

ANSWER_MARK = "**Answer:**"


def parse_answers(text):
    """Map question ID -> (question text, answer text) from an existing open-questions.md."""
    answers = {}
    for block in re.split(r"(?m)^### ", text or "")[1:]:
        qid = block.split("\n", 1)[0].strip()
        question = re.search(r"(?m)^\*\*Question:\*\* (.*)$", block)
        if ANSWER_MARK not in block:
            continue
        answer = block.split(ANSWER_MARK, 1)[1].strip()
        answers[qid] = (question.group(1).strip() if question else "", answer)
    return answers


def render_open_questions(loop, workspace_name, questions, existing_text=None):
    """`questions` are `{id, question, context, affects}`; kept answers need the same ID and text."""
    previous = parse_answers(existing_text)
    lines = [f"# Open questions: {loop}", "",
             f"Write each answer after its {ANSWER_MARK} marker (more lines are fine), then run "
             f"`devloops approve {loop} --workspace {workspace_name}` to accept the plan, or "
             f"`devloops replan {loop} --workspace {workspace_name}` to plan again with the "
             "answers.", ""]
    if not questions:
        lines.append("_No open questions._")
    for q in questions:
        kept = previous.get(q["id"])
        answer = kept[1] if kept and kept[0] == q["question"].strip() else ""
        lines += [f"### {q['id']}", "", f"**Question:** {q['question']}",
                  f"**Context:** {q.get('context') or 'none'}",
                  f"**Affects:** {_refs(q.get('affects'))}", "",
                  f"{ANSWER_MARK} {answer}".rstrip(), ""]
    return "\n".join(lines).rstrip("\n") + "\n"


# --- final-report.md ----------------------------------------------------------------------------

def render_final_report(loop, workspace_name, run, plan, trials_by_mid, validations):
    """`validations` maps milestone ID -> the last trial's validation result (or None)."""
    lines = [f"# Final report: {loop}", "", f"- **Workspace**: {workspace_name}",
             f"- **Outcome**: {run.get('status')}"]
    reason = run.get("status_reason")
    if reason:
        lines.append(f"- **Reason**: {reason.get('code')}: {reason.get('message')}")
    if run.get("ui_url"):
        lines.append(f"- **UI URL**: {run['ui_url']}")
    if run.get("openapi_artifact"):
        art = run["openapi_artifact"]
        lines.append(f"- **OpenAPI artifact**: {art.get('path')} (sha256 {art.get('sha256')})")
    lines += ["", "## Milestones", ""]
    rows = []
    for m in plan["milestones"]:
        ms = run["milestones"][m["id"]]
        rows.append([m["id"], m["title"], ms["status"],
                     f"{len(selector.counted_trials(ms))} of {selector.trial_limit(run, m['id'])}"])
    lines.append(_table(["Milestone", "Title", "Status", "Trials used"], rows))
    lines += ["", "## Validation summary", ""]
    rows = []
    for m in plan["milestones"]:
        vr = validations.get(m["id"])
        if not vr:
            rows.append([m["id"], "not validated", "", "", ""])
            continue
        crit = vr.get("criteria") or []
        unit = vr.get("unit_tests") or {}
        rows.append([m["id"], "passed" if vr.get("passed") else "failed",
                     f"{sum(1 for c in crit if c.get('passed'))} of "
                     f"{len(m['acceptance_criteria'])}",
                     "passed" if (vr.get("contract") or {}).get("passed") else "failed",
                     ("exit " + str(unit.get("exit_code"))) if unit.get("enabled") else "disabled"])
    lines.append(_table(["Milestone", "Validation", "Criteria passed", "Contract", "Unit tests"],
                        rows))
    lines += ["", "## Assumptions for review", ""]
    items = [f"- **{a['id']}** (planning) {a['text']} (source: {a['source']})"
             for a in plan["assumptions"]]
    for m in plan["milestones"]:
        for t in trials_by_mid.get(m["id"], []):
            for a in t.get("assumptions") or []:
                items.append(f"- ({m['id']}, trial {t['n']}) {a['text']} "
                             f"(affects: {_refs(a.get('affects'))})")
    lines += items or ["_None._"]
    return "\n".join(lines) + "\n"


# --- Everything from state -------------------------------------------------------------------------

def load_trials(loop_dir, run):
    trials = {}
    for mid, ms in (run.get("milestones") or {}).items():
        docs = []
        for summary in ms.get("trials") or []:
            path = os.path.join(loop_dir, _trial_dir_rel(mid, summary["n"]), "trial.json")
            docs.append(state.read_json(path, default=dict(summary)))
        trials[mid] = docs
    return trials


def load_validations(loop_dir, run):
    out = {}
    for mid, ms in (run.get("milestones") or {}).items():
        trials = ms.get("trials") or []
        out[mid] = state.read_json(os.path.join(
            loop_dir, _trial_dir_rel(mid, trials[-1]["n"]), "validation.json")) if trials else None
    return out


def render_all(loop_dir, loop, workspace_name, repo_root, final=False, questions=None):
    """Re-render every view of one loop run from its state.

    `questions` (a list) rewrites `outputs/open-questions.md`; the engine passes it only when it
    is allowed to write that file (T055).
    """
    run = state.read_json(os.path.join(loop_dir, "state", "run.json"), default={})
    plan = state.read_json(os.path.join(loop_dir, "state", "plan.json"))
    events = state.read_jsonl(os.path.join(loop_dir, "state", "events.jsonl"))
    invocations = state.read_jsonl(os.path.join(loop_dir, "state", "invocations.jsonl"))
    outputs = os.path.join(loop_dir, "outputs")
    trials = load_trials(loop_dir, run)

    if plan:
        for m in plan["milestones"]:
            ms = (run.get("milestones") or {}).get(m["id"], {})
            state.write_text_atomic(os.path.join(outputs, milestone_filename(m)),
                                    render_milestone(m, ms, trials.get(m["id"], [])))
        state.write_text_atomic(os.path.join(outputs, "plan-summary.md"), render_plan_summary(plan))
    if questions is not None:
        path = os.path.join(outputs, "open-questions.md")
        existing = None
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                existing = f.read()
        state.write_text_atomic(path, render_open_questions(loop, workspace_name, questions,
                                                            existing))
    state.write_text_atomic(os.path.join(loop_dir, "progress.md"),
                            render_progress(loop, workspace_name, run, plan, events, invocations,
                                            trials))
    template = os.path.join(repo_root, "loops", loop, "task.md")
    if run and os.path.exists(template):
        with open(template, encoding="utf-8") as f:
            text = render_task(f.read(), task_values(run, workspace_name))
        state.write_text_atomic(os.path.join(loop_dir, "task.md"), text)
    if final and plan:
        state.write_text_atomic(os.path.join(outputs, "final-report.md"),
                                render_final_report(loop, workspace_name, run, plan, trials,
                                                    load_validations(loop_dir, run)))
