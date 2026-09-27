"""Next unit of work (FR-026, plan "Iteration model" step 4)."""


def counted_trials(milestone_state):
    """Trials that count toward the limit: every trial except `void` ones (FR-067)."""
    return [t for t in milestone_state.get("trials", []) if t.get("status") != "void"]


def trial_limit(run_state, milestone_id):
    config = run_state.get("effective_config") or {}
    extra = sum(g.get("extra_trials", 0) for g in run_state.get("grants") or []
                if g.get("milestone_id") == milestone_id)
    return config.get("max_trials", 3) + extra


def mark_failed(milestone_state):
    """A failed milestone: every task that is not achieved becomes failed (data-model.md)."""
    milestone_state["status"] = "failed"
    for task_id, status in milestone_state.get("tasks", {}).items():
        if status != "achieved":
            milestone_state["tasks"][task_id] = "failed"


def next_unit(run_state, plan):
    """Return `"complete"`, `("stop", code, milestone_id)`, or `("trial", milestone_id, n)`.

    Takes the first milestone, in stored plan order, whose status is not `achieved`. When the
    trial budget is used up, the milestone is marked failed in `run_state` (the caller persists it).
    """
    milestones = run_state.get("milestones") or {}
    for milestone in plan["milestones"]:
        mid = milestone["id"]
        ms = milestones[mid]
        if ms["status"] == "achieved":
            continue
        if ms["status"] == "failed":
            return ("stop", "trials-exhausted", mid)
        n = len(counted_trials(ms)) + 1
        if n > trial_limit(run_state, mid):
            mark_failed(ms)
            return ("stop", "trials-exhausted", mid)
        config = run_state.get("effective_config") or {}
        if run_state.get("invocation_count", 0) >= config.get("max_invocations_per_run", 60):
            return ("stop", "invocation-cap", mid)
        return ("trial", mid, n)
    return "complete"
