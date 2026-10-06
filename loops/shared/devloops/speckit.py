"""The spec-kit bridge: a spec-kit feature folder as the requirements (002 FR-023 to FR-026,
research P-16, data-model "Spec-kit feature").

Devloops reads spec-kit's files and its active-feature record only; it never runs spec-kit.
`spec.md` is the requirements input. `plan.md` and `tasks.md`, when present, are recorded with
their fingerprints. `tasks.md` is parsed here, so the plan's coverage of it can be checked.
"""
import json
import os
import re

from .state import input_error

ACTIVE = "active"
FEATURE_RECORD = os.path.join(".specify", "feature.json")
PHASE = re.compile(r"^## Phase (\d+(?:\.\d+)*): (.+?)\s*$")
TASK = re.compile(r"^- \[( |x|X)\] (T\d{3,})\b(.*)$")
STORY_LABEL = re.compile(r"\[US(\d+)\]")
PARALLEL_LABEL = re.compile(r"\[P\]")
STORY_HEADING = re.compile(r"^#{2,4} User Story (\d+)\b(.*)$")
STORY_ID = re.compile(r"^US\d+$")


def _missing(message):
    return input_error("missing-input", message, input="requirements")


def resolve_feature(arg, project):
    """The feature folder for `--speckit-feature` (`"active"` or a directory).

    Returns `{feature_dir, spec, plan_md, tasks_md}`, all absolute (`plan_md` and `tasks_md` are
    None when absent). The active feature is the `feature_directory` in `.specify/feature.json`
    (FR-024). A folder without a readable `spec.md` is `missing-input` (FR-026).
    """
    if not arg or arg == ACTIVE:
        record = os.path.join(project.root, FEATURE_RECORD)
        try:
            with open(record, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            raise _missing(f"no active spec-kit feature: {record} does not exist; pass "
                           "--speckit-feature <dir>")
        except (OSError, ValueError) as e:
            raise _missing(f"no active spec-kit feature: {record} cannot be read: {e}")
        directory = data.get("feature_directory") if isinstance(data, dict) else None
        if not isinstance(directory, str) or not directory.strip():
            raise _missing(f"no active spec-kit feature: {record} has no feature_directory")
        arg = directory
    feature_dir = project.resolve(arg)
    if not os.path.isdir(feature_dir):
        raise _missing(f"spec-kit feature folder {feature_dir} does not exist")
    spec = os.path.join(feature_dir, "spec.md")
    if not os.path.isfile(spec):
        raise _missing(f"spec-kit feature {feature_dir} has no spec.md")

    def optional(name):
        path = os.path.join(feature_dir, name)
        return path if os.path.isfile(path) else None
    return {"feature_dir": feature_dir, "spec": spec, "plan_md": optional("plan.md"),
            "tasks_md": optional("tasks.md")}


def parse_tasks(text):
    """The phases of a `tasks.md`: `[{n, title, tasks: [{id, story, parallel, done, text}]}]`.

    A phase is a `## Phase <n>: <title>` heading; a task is a `- [ ]` / `- [x]` line starting with
    `T<digits>`. `[P]` sets `parallel` and `[US<n>]` sets `story`. Other lines are ignored, and
    tasks before the first phase heading go in a phase numbered 0.
    """
    phases = []
    for line in text.splitlines():
        heading = PHASE.match(line)
        if heading:
            number = heading.group(1)  # "3", or "3.1" in older spec-kit templates
            phases.append({"n": int(number) if number.isdigit() else number,
                           "title": heading.group(2), "tasks": []})
            continue
        task = TASK.match(line)
        if not task:
            continue
        rest = task.group(3)
        story = STORY_LABEL.search(rest)
        if not phases:
            phases.append({"n": 0, "title": "(before the first phase)", "tasks": []})
        phases[-1]["tasks"].append({
            "id": task.group(2), "story": f"US{story.group(1)}" if story else None,
            "parallel": bool(PARALLEL_LABEL.search(rest)), "done": task.group(1) != " ",
            "text": " ".join(PARALLEL_LABEL.sub("", STORY_LABEL.sub("", rest)).split()),
        })
    return phases


def stories(spec_text):
    """`{"US<n>": heading text}` for every `User Story <n>` heading of `spec.md` (FR-025)."""
    found = {}
    for line in spec_text.splitlines():
        match = STORY_HEADING.match(line)
        if match:
            found.setdefault(f"US{match.group(1)}", line.lstrip("#").strip())
    return found


def _read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def load_phases(block):
    """The parsed phases of a recorded spec-kit block's `tasks.md`, or None without one."""
    tasks = (block.get("tasks_md") or {}).get("path") if block else None
    return parse_tasks(_read(tasks)) if tasks else None


def phase_key(n):
    """A phase number's sort key: `3` < `3.1` < `3.2` < `3.10` < `4`."""
    return tuple(int(part) for part in str(n).split("."))


def tasks_by_id(phases):
    return {t["id"]: dict(t, phase=p["n"]) for p in phases or [] for t in p["tasks"]}


SCOPE_RULE = (
    "Follow tasks.md: one or more milestones per spec-kit phase, in the phases' order, each with "
    "`speckit_phase` set to its phase number. Put the spec-kit task IDs each planned task "
    "implements in its `speckit_tasks`. Every in-scope spec-kit task must be planned or listed in "
    "`speckit_omitted` with a reason (for example \"frontend task\" for backend-dev). A `done` "
    "mark in tasks.md is not proof of anything: plan the task anyway unless the code shows it.")


def context(requirements):
    """The planning context's `speckit` block (research P-16) for recorded spec-kit requirements
    (`inputs.speckit_requirements`: `spec.md` is their `path`)."""
    block, story_id = requirements["speckit"], requirements.get("story_id")
    phases = load_phases(block)
    ctx = {"feature_dir": block["feature_dir"], "spec": requirements["path"],
           "plan_md": (block.get("plan_md") or {}).get("path"),
           "tasks_md": (block.get("tasks_md") or {}).get("path"),
           "phases": phases, "stories": stories(_read(requirements["path"]))}
    if phases is not None:
        rule = SCOPE_RULE
        if story_id:
            rule += (f" Only story {story_id} is in scope: its tasks (labelled [{story_id}]), plus "
                     "unlabelled setup or foundational tasks only when the story needs them. "
                     "Never reference tasks labelled with another story.")
        ctx["rule"] = rule
    if ctx["plan_md"]:
        ctx["plan_md_rule"] = ("plan.md is the feature's technical plan: treat the stack it names "
                               "as named in the requirements (stack source `requirements`).")
    return ctx


def in_scope(phases, story_id, referenced=()):
    """The spec-kit task IDs the plan must account for (FR-023a, FR-023d).

    Every task without a story; with one, its labelled tasks plus the unlabelled tasks the plan
    references (setup or foundational work the story needs).
    """
    tasks = tasks_by_id(phases)
    if not story_id:
        return [tid for tid in tasks]
    return [tid for tid, t in tasks.items()
            if t["story"] == story_id or (t["story"] is None and tid in referenced)]
