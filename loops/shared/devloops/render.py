"""Markdown views rendered from state (FR-002–004b, FR-034, FR-058).

Every view is regenerated from `state/` and never read back as input. The one exception is the
developer's answers in `outputs/open-questions.md`, which is an input file: re-rendering keeps an
answer when the same question (same ID and text) is still open.
"""
import json
import os
import re

from . import selector, speckit, state

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

def render_plan_summary(plan, speckit_phases=None, story_id=None):
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
    if speckit_phases is not None:
        lines += ["", *render_speckit_coverage(plan, speckit_phases, story_id)]
    lines += ["", f"Open questions: {len(plan['open_questions'])} (see open-questions.md)"]
    return "\n".join(lines) + "\n"


def render_speckit_coverage(plan, phases, story_id=None):
    """The plan summary's "Spec-kit tasks" section (002 FR-023b, FR-023d): what is planned, what
    is left out and why, and what the plan adds, so the differences are reviewed at approval."""
    tasks = speckit.tasks_by_id(phases)
    planned = {}
    unmatched = []
    for m in plan["milestones"]:
        for t in m["tasks"]:
            refs = t.get("speckit_tasks") or []
            for tid in refs:
                planned.setdefault(tid, []).append(t["id"])
            if not refs:
                unmatched.append(f"- **{t['id']}** {t['title']}")
    omitted = {o["id"]: o["reason"] for o in plan.get("speckit_omitted") or []}

    def label(tid):
        t = tasks.get(tid) or {}
        story = f" [{t['story']}]" if t.get("story") else ""
        done = " (already marked done in tasks.md)" if t.get("done") else ""
        return f"**{tid}**{story} {t.get('text', '')}{done}"
    lines = ["## Spec-kit tasks", "", "### Planned", ""]
    lines += [f"- {label(tid)} → {', '.join(ids)}" for tid, ids in planned.items()] or ["_None._"]
    lines += ["", "### Left out", ""]
    lines += [f"- {label(tid)}: {reason}" for tid, reason in omitted.items()] or ["_None._"]
    if story_id:
        needed = [tid for tid in planned if tid in tasks and tasks[tid]["story"] is None]
        lines += ["", f"### Setup and foundational tasks needed by {story_id}", ""]
        lines += [f"- {label(tid)}" for tid in needed] or ["_None._"]
        others = sorted(tid for tid, t in tasks.items()
                        if t["story"] not in (None, story_id))
        if others:
            lines += ["", f"Out of scope (other stories): {', '.join(others)}"]
    lines += ["", "### Devloops tasks with no spec-kit task", ""]
    lines += unmatched or ["_None._"]
    done = [tid for tid, t in tasks.items() if t["done"]]
    if done:
        lines += ["", "### Already marked done in tasks.md", "",
                  "Planned or listed anyway: a `done` mark is not proof the code exists.", ""]
        lines += [f"- {label(tid)}" for tid in done]
    return lines


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
SOURCE_MARK = "**Answer source:**"
_ANSWER_RE = re.compile(r"(?m)^\*\*Answer:\*\*")
_FIELDS = {"Question": "question", "Context": "context", "Affects": "affects",
           "Suggested answer": "suggested", "Why": "reason", "Answer source": "source"}
# Only these labels start a field, so a `**Note:**` line inside a suggestion stays part of it.
_FIELD_RE = re.compile(r"(?m)^\*\*(" + "|".join(_FIELDS) + r"):\*\* ?")


def _split_blocks(text):
    """`[preamble, "### OQ1...", "### OQ2...", ...]`; joining the list gives `text` back."""
    return re.split(r"(?m)^(?=### )", text or "")


def parse_questions(text):
    """Map question ID -> `{question, context, affects, suggested, reason, source, answer}` from
    open-questions.md. A field runs until the next `**Field:**` line; the answer is everything
    after the `**Answer:**` marker. Blocks without that marker are skipped."""
    out = {}
    for block in _split_blocks(text)[1:]:
        qid = block[4:].split("\n", 1)[0].strip()
        answer = _ANSWER_RE.search(block)
        if not answer:
            continue
        head = block[:answer.start()]
        fields = dict.fromkeys(_FIELDS.values(), "")
        marks = list(_FIELD_RE.finditer(head))
        for i, m in enumerate(marks):
            key = _FIELDS.get(m.group(1))
            if key:
                stop = marks[i + 1].start() if i + 1 < len(marks) else len(head)
                fields[key] = head[m.end():stop].strip()
        fields["answer"] = block[answer.end():].strip()
        out[qid] = fields
    return out


def parse_answers(text):
    """Map question ID -> (question text, answer text) from an existing open-questions.md."""
    return {qid: (q["question"], q["answer"]) for qid, q in parse_questions(text).items()}


def effective_answer(q):
    """What a question's answer is, and where it came from: `(text, "developer" | "suggested" |
    "accepted" | None)`. An empty answer stands for the suggestion until something accepts it.
    An accepted suggestion the developer has since rewritten is theirs: the `**Answer source:**`
    line counts only while the answer is still the suggestion."""
    if q["answer"]:
        accepted = q["source"] and q["answer"] == q["suggested"]
        return q["answer"], ("accepted" if accepted else "developer")
    if q["suggested"]:
        return q["suggested"], "suggested"
    return "", None


def _question_lines(qid, question, context, affects, suggested, reason, answer="", source=""):
    lines = [f"### {qid}", "", f"**Question:** {question}", f"**Context:** {context or 'none'}",
             f"**Affects:** {_refs(affects)}"]
    if suggested:
        lines += [f"**Suggested answer:** {suggested}", f"**Why:** {reason or 'not given'}"]
    if source:
        lines.append(f"{SOURCE_MARK} {source}")
    return lines + ["", f"{ANSWER_MARK} {answer}".rstrip(), ""]


def _intro(loop, workspace_name):
    return [f"# Open questions: {loop}", "",
            f"Claude suggests an answer where it can. Leave {ANSWER_MARK} empty to accept the "
            f"suggestion, or write your own answer after the marker (more lines are fine). By "
            f"default the run accepts the suggestions itself. When it pauses for review, run "
            f"`devloops approve {loop} --workspace {workspace_name}` to accept the plan and "
            f"continue, or `devloops replan {loop} --workspace {workspace_name}` to plan again "
            f"with the answers. Approving (or `retry` after a needs-input stop) copies each "
            f"accepted suggestion into its answer and marks it with {SOURCE_MARK}.", ""]


def render_open_questions(loop, workspace_name, questions, existing_text=None):
    """`questions` are plan `open_questions`; kept answers need the same ID and text."""
    previous = parse_questions(existing_text)
    lines = _intro(loop, workspace_name)
    if not questions:
        lines.append("_No open questions._")
    for q in questions:
        kept = previous.get(q["id"])
        same = kept and kept["question"] == q["question"].strip()
        lines += _question_lines(q["id"], q["question"], q.get("context"), q.get("affects"),
                                 q.get("suggested_answer"), q.get("suggestion_reason"),
                                 kept["answer"] if same else "", kept["source"] if same else "")
    return "\n".join(lines).rstrip("\n") + "\n"


def append_open_questions(existing_text, questions, context):
    """Append `needs_input` questions to open-questions.md as new `OQ<n>`, each unanswered.

    `questions` are `{question, requirement_refs, suggested_answer, suggestion_reason}`;
    numbering continues after the highest `OQ<n>` already in the file. Returns `(text, ids)`.
    Answers already written are kept as they are.
    """
    text = (existing_text or "").replace("_No open questions._\n", "").rstrip("\n")
    numbers = [int(n) for n in re.findall(r"(?m)^### OQ(\d+)\s*$", text)]
    next_n = max(numbers, default=0) + 1
    ids = []
    lines = [text, ""] if text else []
    for i, q in enumerate(questions):
        qid = f"OQ{next_n + i}"
        ids.append(qid)
        lines += _question_lines(qid, q["question"], context, q.get("requirement_refs"),
                                 q.get("suggested_answer"), q.get("suggestion_reason"))
    return "\n".join(lines).rstrip("\n") + "\n", ids


def accept_suggestions(text, how, ids=None):
    """Copy each suggestion whose answer is empty into the answer, marked `**Answer source:**
    suggested answer, accepted <how>`. `ids` limits it to those questions. Returns `(text,
    accepted_ids)`; the text is unchanged when nothing was accepted."""
    blocks = _split_blocks(text)
    questions = parse_questions(text)
    accepted = []
    for i, block in enumerate(blocks[1:], 1):
        qid = block[4:].split("\n", 1)[0].strip()
        q = questions.get(qid)
        if not q or q["answer"] or not q["suggested"] or (ids is not None and qid not in ids):
            continue
        head = block[:_ANSWER_RE.search(block).start()].rstrip("\n")
        blocks[i] = (f"{head}\n{SOURCE_MARK} suggested answer, accepted {how}\n\n"
                     f"{ANSWER_MARK} {q['suggested']}\n\n")
        accepted.append(qid)
    if not accepted:
        return text, []
    return "".join(blocks).rstrip("\n") + "\n", accepted


# --- final-report.md ----------------------------------------------------------------------------

def render_final_report(loop, workspace_name, run, plan, trials_by_mid, validations,
                        questions=None):
    """`validations` maps milestone ID -> the last trial's validation result (or None);
    `questions` is `parse_questions` of open-questions.md."""
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
        if art.get("omitted_operations"):
            lines.append("- **Left out of the OpenAPI artifact** (in the target's document, but no "
                         "check ever called them): " + ", ".join(art["omitted_operations"]))
    # The decisions the requirements left open come first: review them before the results.
    accepted = [(qid, q) for qid, q in (questions or {}).items()
                if effective_answer(q)[1] == "accepted"]
    if accepted:
        lines += ["", "## Suggested answers accepted", "",
                  "Claude suggested these answers and nobody wrote a different one; review them "
                  "like assumptions.", ""]
        lines += [f"- **{qid}** {q['question']} **Answer:** {q['answer']} ({q['source']})"
                  for qid, q in accepted]
    lines += ["", "## Assumptions for review", ""]
    items = [f"- **{a['id']}** (planning) {a['text']} (source: {a['source']})"
             for a in plan["assumptions"]]
    for m in plan["milestones"]:
        for t in trials_by_mid.get(m["id"], []):
            for a in t.get("assumptions") or []:
                items.append(f"- ({m['id']}, trial {t['n']}) {a['text']} "
                             f"(affects: {_refs(a.get('affects'))})")
    lines += items or ["_None._"]
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


def load_questions(loop_dir):
    """`parse_questions` of the loop's open-questions.md; `{}` when there is none."""
    try:
        with open(os.path.join(loop_dir, "outputs", "open-questions.md"), encoding="utf-8") as f:
            return parse_questions(f.read())
    except OSError:
        return {}


def load_validations(loop_dir, run):
    out = {}
    for mid, ms in (run.get("milestones") or {}).items():
        trials = ms.get("trials") or []
        out[mid] = state.read_json(os.path.join(
            loop_dir, _trial_dir_rel(mid, trials[-1]["n"]), "validation.json")) if trials else None
    return out


def render_all(loop_dir, loop, workspace_name, kit, final=False, questions=None):
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
        req = (run.get("inputs") or {}).get("requirements") or {}
        try:
            phases = speckit.load_phases(req.get("speckit"))
        except OSError:
            phases = None  # tasks.md is gone; the start's input check reports it
        state.write_text_atomic(os.path.join(outputs, "plan-summary.md"),
                                render_plan_summary(plan, phases, req.get("story_id")))
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
    template = kit.path(loop, "task.md")
    if run and os.path.exists(template):
        with open(template, encoding="utf-8") as f:
            text = render_task(f.read(), task_values(run, workspace_name))
        state.write_text_atomic(os.path.join(loop_dir, "task.md"), text)
    if final and plan:
        state.write_text_atomic(os.path.join(outputs, "final-report.md"),
                                render_final_report(loop, workspace_name, run, plan, trials,
                                                    load_validations(loop_dir, run),
                                                    load_questions(loop_dir)))


# --- Orchestrator progress -----------------------------------------------------------------------------

def render_orchestrator_progress(workspace_name, orch):
    """`orchestrator/progress.md` from `orchestrator/state.json` (T066; R-15)."""
    lines = [f"# Orchestrator progress: {workspace_name}", "",
             f"**Status:** {orch['status']}", "",
             "Order: `backend-dev`, then `frontend-dev`. The frontend starts only after the "
             "backend is completed. Run `devloops orchestrate` again to resume.", "",
             "## Steps", ""]
    steps = orch.get("steps") or []
    if steps:
        lines.append(_table(["Loop", "Status", "Reason", "Started", "Ended"],
                            [(s["loop"], s["status"], s.get("reason"), s.get("started_at"),
                              s.get("ended_at")) for s in steps]))
    else:
        lines.append("No loop has started yet.")
    lines += ["", "## Handoff", ""]
    handoff = orch.get("handoff")
    if handoff:
        spec, runtime = handoff["api_spec"], handoff["backend_runtime"]
        lines += [f"- API spec: `{spec['path']}` (sha256 {spec.get('sha256') or 'missing'})"]
        lines += [f"- Backend {key}: `{runtime[key]}`"
                  for key in ("start_command", "cwd", "base_url", "ready_url") if runtime.get(key)]
    else:
        lines.append("Not built yet: it is built once `backend-dev` is completed.")
    for s in steps:
        if s["status"] == "awaiting-approval":
            lines += ["", f"**Action:** review `{s['loop']}/outputs/`, then run `devloops approve "
                          f"{s['loop']}`, which continues the run."]
        elif s["status"] in STOPPED:
            lines += ["", f"**Action:** `{s['loop']}` stopped ({s.get('reason')}); see "
                          f"`{s['loop']}/progress.md`."]
    return "\n".join(lines) + "\n"
