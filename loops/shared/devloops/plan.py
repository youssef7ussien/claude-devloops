"""Plan validation: schema plus semantic rules (research R-5, data-model.md "Plan")."""
from . import schema, speckit

STORY_MODES = ("story-file", "prd-story")


def validate_plan(plan, loop_def, mode="prd", story_id=None):
    """Return a list of problems; empty means the plan is valid.

    In a story mode with a story ID, every task and acceptance criterion must cite that ID, so no
    planned work falls outside the story (FR-010, FR-010a). Other refs, such as shared rules, may
    be cited alongside it.
    """
    errors = schema.validate(plan, "plan.schema.json")
    if errors:
        return errors  # the semantic rules assume the schema's shape

    inventory = [item["ref"] for item in plan["requirements_inventory"]]
    errors.extend(_duplicates(inventory, "requirements_inventory ref"))
    known_refs = set(inventory)

    milestones = plan["milestones"]
    milestone_ids = [m["id"] for m in milestones]
    errors.extend(_duplicates(milestone_ids, "milestone id"))
    errors.extend(_duplicates([t["id"] for m in milestones for t in m["tasks"]], "task id"))
    errors.extend(_duplicates([c["id"] for m in milestones for c in m["acceptance_criteria"]],
                              "acceptance criterion id"))
    errors.extend(_duplicates([q["id"] for q in plan["open_questions"]], "open question id"))
    errors.extend(_duplicates([a["id"] for a in plan["assumptions"]], "assumption id"))

    position = {mid: i for i, mid in enumerate(milestone_ids)}
    for i, m in enumerate(milestones):
        mid = m["id"]
        for dep in m["depends_on"]:
            if dep not in position:
                errors.append(f"milestone {mid} depends on unknown milestone {dep}")
            elif position[dep] >= i:
                errors.append(f"milestone {mid} depends on {dep}, which does not come before it "
                              "(milestones must be listed in dependency order, without cycles)")
        for kind, items in (("task", m["tasks"]), ("acceptance criterion", m["acceptance_criteria"])):
            for item in items:
                if not item["id"].startswith(mid + "-"):
                    errors.append(f"{kind} {item['id']} is listed under milestone {mid}")
                for ref in item["requirement_refs"]:
                    if ref not in known_refs:
                        errors.append(f"{kind} {item['id']} cites {ref!r}, which is not in "
                                      "requirements_inventory")
                if mode in STORY_MODES and story_id and story_id not in item["requirement_refs"]:
                    errors.append(f"{kind} {item['id']} does not cite story {story_id!r}; in "
                                  "single-story mode all planned work must belong to that story")

    if plan["stack"]["conflicts"] and not plan["open_questions"]:
        errors.append("stack.conflicts is not empty, so at least one open question is required")

    if loop_def.get("requires_openapi_path") and not plan["runtime"].get("openapi_path"):
        errors.append("runtime.openapi_path is required for this loop")

    return errors


def _duplicates(ids, label):
    seen, dups = set(), []
    for i in ids:
        if i in seen and i not in dups:
            dups.append(i)
        seen.add(i)
    return [f"duplicate {label} {d!r}" for d in dups]


def validate_speckit(plan, phases, story_id=None):
    """The plan's coverage of a spec-kit `tasks.md` (002 FR-023a, FR-023d; research P-16).

    `phases` is `speckit.parse_tasks()` of the recorded `tasks.md`. Returns problems in the same
    form as `validate_plan`, so a violation fails the planning trial:
    - every referenced spec-kit task (`speckit_tasks`, `speckit_omitted`) must exist;
    - in single-story mode, no referenced task may belong to another story;
    - every in-scope task must be referenced by a planned task or omitted with a reason;
    - milestones follow the phases' order (`speckit_phase` never decreases).
    """
    tasks = speckit.tasks_by_id(phases)
    referenced, errors = [], []
    for m in plan["milestones"]:
        for t in m["tasks"]:
            for tid in t.get("speckit_tasks") or []:
                referenced.append(tid)
                if tid not in tasks:
                    errors.append(f"task {t['id']} cites spec-kit task {tid}, which is not in "
                                  "tasks.md")
    omitted = {}
    for item in plan.get("speckit_omitted") or []:
        if item["id"] not in tasks:
            errors.append(f"speckit_omitted lists {item['id']}, which is not in tasks.md")
        omitted[item["id"]] = item["reason"].strip()
    if story_id:
        for tid in dict.fromkeys(referenced):
            story = (tasks.get(tid) or {}).get("story")
            if story and story != story_id:
                errors.append(f"spec-kit task {tid} belongs to {story}; in single-story mode only "
                              f"{story_id} and the setup it needs are in scope")
    for tid in speckit.in_scope(phases, story_id, set(referenced)):
        if tid not in referenced and not omitted.get(tid):
            errors.append(f"spec-kit task {tid} is neither planned (speckit_tasks) nor listed in "
                          "speckit_omitted with a reason")
    known_phases = {str(p["n"]) for p in phases}
    last = None
    for m in plan["milestones"]:
        phase = m.get("speckit_phase")
        if phase is None:
            continue
        if str(phase) not in known_phases:
            errors.append(f"milestone {m['id']} has speckit_phase {phase}, which is not a phase "
                          "of tasks.md")
            continue
        if last is not None and speckit.phase_key(phase) < speckit.phase_key(last):
            errors.append(f"milestone {m['id']} (phase {phase}) comes after a phase-{last} "
                          "milestone; follow the phases' order")
        else:
            last = phase
    return errors
