"""The run behind `devloops run`: the loops a project includes, `backend-dev` then
`frontend-dev`, in one workspace (001 research R-15, FR-041-042, FR-052, FR-056; 003 FR-001-007).

Each loop runs through `engine.Engine`; the loops contain no run-specific code. This module only
chooses the loops (`select_loops`), sequences them, hands the backend's verified OpenAPI document
and runtime to the frontend, and records what happened in `<workspace>/run/{state.json,
progress.md}`. An `orchestrator/` folder left by an older devloops is neither read nor deleted
(003 FR-016a). The internal names (`Orchestrator`, this module) are kept (003 research R-1).
"""
import os
from dataclasses import dataclass

from . import engine, inputs, render, state
from . import workspace as workspace_mod
from .state import EXIT_CODES, DevloopsError, StopRun

LOOP_ORDER = ("backend-dev", "frontend-dev")
BACKEND_RUNTIME_KEYS = ("start_command", "cwd", "base_url", "ready_url")
TARGET_ROOT_NAMES = {"backend-dev": "backend", "frontend-dev": "frontend"}
TARGET_FLAGS = {"backend-dev": "--backend-target", "frontend-dev": "--frontend-target"}


def state_path(ws):
    """`<workspace>/run/state.json`, the run's record (003 FR-016)."""
    return os.path.join(ws.path, "run", "state.json")


def read_state(ws):
    """The run's record, or None before the first `devloops run` in this workspace."""
    return state.read_json(state_path(ws))


def select_loops(project, ws=None, backend_target=None, frontend_target=None, target_root=None):
    """The loops a run includes, `{loop: absolute target}` in `LOOP_ORDER` (003 FR-005, R-2).

    For each loop the first that applies wins: the target recorded in the workspace `ws` (once
    recorded, the loop stays included), the explicit flag, then the project's `targets.<loop>`
    when it is neither null nor missing, placed under `target_root` when one is given. A loop
    none of these gives a target is left out: `target_root` never adds one. A flag that names
    another folder than the recorded one is a usage error (FR-005a).
    """
    flags = {"backend-dev": backend_target, "frontend-dev": frontend_target}
    configured = project.targets if project is not None else {}
    selected = {}
    for loop in LOOP_ORDER:
        recorded = ws.target(loop) if ws is not None else None
        flag = os.path.abspath(flags[loop]) if flags[loop] else None
        if recorded:
            if flag and os.path.realpath(flag) != os.path.realpath(recorded):
                raise state.UsageError(
                    f"{loop}'s target is recorded as {recorded}; {TARGET_FLAGS[loop]} {flag} "
                    "differs (start a new workspace to change it)")
            selected[loop] = recorded
        elif flag:
            selected[loop] = flag
        elif configured.get(loop):
            selected[loop] = (os.path.join(os.path.abspath(target_root), TARGET_ROOT_NAMES[loop])
                              if target_root else configured[loop])
    return selected


def check_selection(selected, frontend_flag=False):
    """Stop before anything is written when the selection cannot run (003 FR-006, R-3).
    `frontend_flag`: the frontend came from `--frontend-target`, so `--backend-target` fixes it
    too."""
    if not selected:
        raise StopRun("stopped-on-input-error", "no-loop",
                      "no loop to run: set targets.backend-dev or targets.frontend-dev in "
                      ".devloops/devloops.json (or run devloops init)")
    if "frontend-dev" in selected and "backend-dev" not in selected:
        flag = " or pass --backend-target" if frontend_flag else ""
        raise StopRun("stopped-on-input-error", "frontend-needs-backend",
                      "frontend-dev needs backend-dev in the same run: set targets.backend-dev "
                      f"in .devloops/devloops.json{flag} (frontend-only runs are not supported "
                      "yet)")


@dataclass
class OrchestrateOptions:
    """What `devloops run` passes. `None` means the flag was not given."""

    requirements: str = None
    speckit_feature: str = None
    story_id: str = None
    story_file: bool = False
    config_path: str = None
    force_unlock: bool = False
    questions: str = None  # --accept-suggested or --review-plan (ask); None: as recorded, else
    #                        the config's
    max_trials: int = None  # --max-trials: every loop this command starts or resumes keeps it
    selected: dict = None  # {loop: target} from select_loops, checked by check_selection


class Orchestrator:
    def __init__(self, workspace, options=None, kit=None, env=None):
        self.ws = workspace
        self.opts = options or OrchestrateOptions()
        self.kit = kit or workspace.kit
        self.env = env
        self.state_path = state_path(workspace)
        self.dir = os.path.dirname(self.state_path)
        self.state = None
        self.message = ""
        self.last_run = None  # the loop this command ran last; None if it ran none
        self.selected = []  # the loops this run includes, in order (set by run)
        # While a decision (`run(action)`) is not recorded yet, nothing is written: a refused
        # decision, or one that meets another driver's lock, leaves state.json to its owner.
        self.deciding = False
        self.on_progress = None  # passed to each loop's engine (Engine.on_progress)
        self.progress = None  # likewise (Engine.progress)

    def run(self, action=None):
        """Run or resume the selected loops in order; return the exit code of the loop that
        stopped, or 0.

        `action` is `(loop, fn)`: a decision (`approve`, `retry`, `replan` in an orchestrated
        workspace) that resumes that loop instead of `Engine.run`; `fn(engine)` returns its exit
        code. Until the decision is recorded nothing is written here, so a refused one (or one
        that meets another driver's lock) leaves the orchestrator's record as it was.
        """
        if action and action[0] == "frontend-dev" and \
                engine.status_object(self.ws, "backend-dev")["status"] != "completed":
            raise state.UsageError("frontend-dev has not started: backend-dev is not completed")
        selected = self.opts.selected
        if selected is None:
            raise ValueError("OrchestrateOptions.selected is required (see select_loops)")
        self.selected = list(selected)
        self.targets = {loop: os.path.abspath(target) for loop, target in selected.items()}
        if action is None:
            # Record every selected target now, so a later `devloops run` without flags still has
            # the frontend's, and a bad frontend target stops before the backend runs.
            for loop, target in self.targets.items():
                self.ws.set_target(loop, target)
        else:
            # A decision changes nothing until it is recorded (FR-010): targets not recorded yet
            # are only checked here, and recorded when their loop starts.
            for loop, target in self.targets.items():
                if not self.ws.target(loop):
                    workspace_mod.check_target(target, self.ws.project, self.kit, self.ws.path, [
                        (other, path) for other, path in self.targets.items() if other != loop])
        self.state = state.read_json(self.state_path) or {"status": "running", "steps": [],
                                                           "handoff": None}
        self.state["loops"] = self.selected
        self.deciding = action is not None
        # --review-plan or --accept-suggested holds for the whole orchestrated run, so the
        # frontend's first start, on a later command without the flag, keeps it.
        if self.opts.questions:
            self.state["questions"] = self.opts.questions
        self.opts.questions = self.state.get("questions") or self._backend_questions()
        self._check_tools()  # before anything is spent: a missing frontend tool stops it now
        old_root = self.state.get("project_root")
        if old_root:  # a moved or cloned project: the handoff's paths follow it (FR-013)
            self.state = self.ws.project.relocate(self.state, old_root)
        self.state["project_root"] = self.ws.project.root
        self.state["status"] = "running"
        self._save()
        code = EXIT_CODES["completed"]
        for loop in self.selected:
            if not self.ws.target(loop):  # a decision's later loop: recorded once decided
                self.ws.set_target(loop, self.targets[loop])
            code = self._run_loop(loop, self._loop_options(loop), action)
            if code != EXIT_CODES["completed"]:
                return code
            if loop == "backend-dev":
                # FR-042, FR-056: the frontend starts only after the backend is completed. The
                # handoff is recorded even without a frontend, so one added later starts from it
                # (003 FR-007).
                self.state["handoff"] = self._handoff()
                self._save()
        self.state["status"] = "completed"
        self._save()
        self.message = (f"{' and '.join(self.selected)} completed" if len(self.selected) > 1
                        else f"{self.selected[0]} completed") + "; see run/progress.md"
        return code

    # --- steps ---------------------------------------------------------------------------------------

    def _backend_questions(self):
        """The backend's frozen `questions`, for a workspace orchestrated before the mode was
        recorded here: its frontend keeps the backend's mode, not a newer default. A run frozen
        before the setting existed paused at every plan (`ask`)."""
        rs = state.read_json(os.path.join(self.ws.loop_dir("backend-dev"), "state", "run.json"))
        return (rs["effective_config"].get("questions") or "ask") if rs else None

    def sync_step(self, loop):
        """After a decision recorded with --no-continue, show the loop's new status (the run
        continues on the next `devloops run`). Nothing else changes."""
        self.state = state.read_json(self.state_path)
        if not self.state:
            return
        loop_status = engine.status_object(self.ws, loop)
        step = self._step(loop)
        step.update(status=loop_status["status"],
                    reason=(loop_status.get("status_reason") or {}).get("code"))
        self._save()

    def _check_tools(self):
        """Each selected loop with work left checks its tools, with no handoff yet (nothing is
        written)."""
        self.tools_checked = set()
        for loop in self.selected:
            opts = engine.Options(config_path=self.opts.config_path,
                                  cli_overrides={"questions": self.opts.questions})
            try:
                if engine.Engine(loop, self.ws, opts, kit=self.kit, env=self.env).check_tools():
                    self.tools_checked.add(loop)
            except StopRun as e:
                raise StopRun(e.status, e.code, f"{loop}: {e.message}; nothing was run (see "
                              "`devloops check`)", **e.details)

    def _run_loop(self, loop, options, action=None):
        step = self._step(loop)
        fn = action[1] if action and action[0] == loop else None
        if fn is None and engine.status_object(self.ws, loop)["status"] == "completed":
            # Nothing to resume: keep the step's record, so its times stay those of the real run.
            # A step this record lacks (a workspace from an older devloops, 003 FR-016a) only
            # takes the loop's status.
            if step["status"] != "completed":
                step.update(status="completed", reason=None)
                self._save()
            return EXIT_CODES["completed"]
        self.last_run = loop
        step.update(status="running", reason=None, ended_at=None)
        step["started_at"] = step.get("started_at") or state.now_iso()
        self._save()  # written before the action it records
        eng = None
        try:
            eng = engine.Engine(loop, self.ws, options, kit=self.kit, env=self.env)
            eng.on_progress = self.on_progress
            eng.progress = self.progress
            eng.resume_command = "devloops run"
            eng.tools_checked = loop in self.tools_checked  # by _check_tools, this command
            if fn:
                eng.on_decided = self._decided
            code = fn(eng) if fn else eng.run()
        except DevloopsError as e:  # usage error or lock held: nothing ran; record and re-raise
            if self.deciding:  # the decision was not recorded: neither is anything here
                self.last_run = None
                raise
            self._finish_step(step, loop, e.message)
            self.state["status"] = "stopped"
            self._save()
            raise
        self.message = f"{loop}: {eng.message}" if eng.message else ""
        self._finish_step(step, loop)
        if code != EXIT_CODES["completed"]:
            self.state["status"] = "paused" if code == EXIT_CODES["awaiting-approval"] \
                else "stopped"
        self._save()
        return code

    def _decided(self):
        """The engine recorded the decision: from now on this run is recorded as usual."""
        self.deciding = False
        self._save()

    def _finish_step(self, step, loop, error=None):
        loop_status = engine.status_object(self.ws, loop)
        reason = (loop_status.get("status_reason") or {}).get("code")
        step.update(status=loop_status["status"], reason=error or reason,
                    ended_at=state.now_iso())

    def _step(self, loop):
        for step in self.state["steps"]:
            if step["loop"] == loop:
                return step
        step = {"loop": loop, "status": "not-started", "reason": None, "started_at": None,
                "ended_at": None}
        self.state["steps"].append(step)
        self.state["steps"].sort(key=lambda s: LOOP_ORDER.index(s["loop"]))
        return step

    # --- inputs -------------------------------------------------------------------------------------------

    def _requirements_selection(self):
        """The requirements and story options, falling back to what the workspace recorded.

        A loop's first start can come on a later `devloops run` (the frontend starts after the
        backend's approval pause), where the developer only resumes and passes no flags. Given
        flags still win, and the engine checks them against the recorded ones.
        """
        recorded = self.ws.data.get("requirements") or {}
        path, feature = self.opts.requirements, self.opts.speckit_feature
        if not path and not feature:
            feature = self.ws.speckit_feature()
            path = None if feature else self.ws.requirements_path()
        story_id, story_file = self.opts.story_id, self.opts.story_file
        if story_id is None and not story_file and recorded:
            story_id = recorded.get("story_id")
            story_file = recorded.get("mode") == "story-file"
        return path, feature, story_id, story_file

    def _loop_options(self, loop):
        requirements, feature, story_id, story_file = self._requirements_selection()
        opts = engine.Options(
            requirements=requirements, speckit_feature=feature, story_id=story_id,
            story_file=story_file, config_path=self.opts.config_path,
            force_unlock=self.opts.force_unlock,
            target=self.ws.target(loop))
        opts.cli_overrides = {"questions": self.opts.questions}
        if self.opts.max_trials:
            opts.cli_overrides["max_trials"] = self.opts.max_trials
        if loop == "frontend-dev":
            handoff = self.state["handoff"]
            opts.api_spec = handoff["api_spec"]["path"]
            opts.cli_overrides["backend"] = dict(handoff["backend_runtime"])
        return opts

    def _handoff(self):
        """The backend's verified contract and how to start it (R-15), from its own state."""
        loop_dir = self.ws.loop_dir("backend-dev")
        api_spec = os.path.join(loop_dir, "outputs", "openapi.json")
        plan = state.read_json(os.path.join(loop_dir, "state", "plan.json")) or {}
        run = state.read_json(os.path.join(loop_dir, "state", "run.json")) or {}
        # The backend's effective runtime: its plan, overlaid by its frozen config.
        runtime = dict(plan.get("runtime") or {})
        runtime.update((run.get("effective_config") or {}).get("runtime") or {})
        backend = {k: runtime[k] for k in BACKEND_RUNTIME_KEYS if runtime.get(k)}
        backend["cwd"] = os.path.normpath(os.path.join(run.get("target_dir") or "",
                                                       runtime.get("cwd") or "."))
        return {"api_spec": {"path": api_spec,
                             "sha256": inputs._hash_or_none(api_spec)},
                "backend_runtime": backend}

    def _save(self):
        if self.deciding:
            return
        state.write_json_atomic(self.state_path, self.state)
        state.write_text_atomic(os.path.join(self.dir, "progress.md"),
                                render.render_orchestrator_progress(self.ws.name, self.state))
