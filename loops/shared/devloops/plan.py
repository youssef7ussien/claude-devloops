"""Plan validation: schema plus semantic rules (research R-5, data-model.md "Plan")."""
from . import schema

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
