"""Optional orchestration: `backend-dev`, then `frontend-dev`, in one workspace (plan.md,
"Optional orchestration"; research R-15; FR-040-042, FR-052, FR-056).

Each loop runs through `engine.Engine`, the same code path as `devloops run <loop>`; the loops
contain no orchestrator-specific code. This module only sequences them, hands the backend's
verified OpenAPI document and runtime to the frontend, and records what happened in
`workspaces/<ws>/orchestrator/{state.json, progress.md}`.
"""
import os
from dataclasses import dataclass

from . import engine, inputs, render, state
from .state import EXIT_CODES, DevloopsError

LOOP_ORDER = ("backend-dev", "frontend-dev")
BACKEND_RUNTIME_KEYS = ("start_command", "cwd", "base_url", "ready_url")


@dataclass
class OrchestrateOptions:
    """What `devloops orchestrate` passes. `None` means the flag was not given."""

    requirements: str = None
    speckit_feature: str = None
    story_id: str = None
    story_file: bool = False
    backend_target: str = None
    frontend_target: str = None
    config_path: str = None
    force_unlock: bool = False


class Orchestrator:
    def __init__(self, workspace, options=None, kit=None, env=None):
        self.ws = workspace
        self.opts = options or OrchestrateOptions()
        self.kit = kit or workspace.kit
        self.env = env
        self.dir = os.path.join(workspace.path, "orchestrator")
        self.state_path = os.path.join(self.dir, "state.json")
        self.state = None
        self.message = ""
        self.last_run = None  # the loop this command ran last; None if it ran none
        self.on_progress = None  # passed to each loop's engine (Engine.on_progress)

    def run(self):
        """Run or resume both loops in order; return the exit code of the loop that stopped, or 0."""
        # Record both targets now, so a later `orchestrate` without flags still has the
        # frontend's, and a bad frontend target stops before the backend runs.
        for loop, target in (("backend-dev", self.opts.backend_target),
                             ("frontend-dev", self.opts.frontend_target)):
            if target:
                self.ws.set_target(loop, os.path.abspath(target))
        self.state = state.read_json(self.state_path) or {"status": "running", "steps": [],
                                                           "handoff": None}
        old_root = self.state.get("project_root")
        if old_root:  # a moved or cloned project: the handoff's paths follow it (FR-013)
            self.state = self.ws.project.relocate(self.state, old_root)
        self.state["project_root"] = self.ws.project.root
        self.state["status"] = "running"
        self._save()
        code = self._run_loop("backend-dev", self._loop_options("backend-dev"))
        if code != EXIT_CODES["completed"]:
            return code
        # FR-042, FR-056: the frontend starts only after the backend is completed.
        self.state["handoff"] = self._handoff()
        self._save()
        code = self._run_loop("frontend-dev", self._loop_options("frontend-dev"))
        if code != EXIT_CODES["completed"]:
            return code
        self.state["status"] = "completed"
        self._save()
        self.message = "both loops completed; see orchestrator/progress.md"
        return code

    # --- steps ---------------------------------------------------------------------------------------

    def _run_loop(self, loop, options):
        step = self._step(loop)
        if step["status"] == "completed" and \
                engine.status_object(self.ws, loop)["status"] == "completed":
            # Nothing to resume: keep the step's record, so its times stay those of the real run.
            return EXIT_CODES["completed"]
        self.last_run = loop
        step.update(status="running", reason=None, ended_at=None)
        step["started_at"] = step.get("started_at") or state.now_iso()
        self._save()  # written before the action it records
        eng = None
        try:
            eng = engine.Engine(loop, self.ws, options, kit=self.kit, env=self.env)
            eng.on_progress = self.on_progress
            code = eng.run()
        except DevloopsError as e:  # usage error or lock held: nothing ran; record and re-raise
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

        A loop's first start can come on a later `orchestrate` (the frontend starts after the
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
        if loop == "frontend-dev":
            handoff = self.state["handoff"]
            opts.api_spec = handoff["api_spec"]["path"]
            opts.cli_overrides = {"backend": dict(handoff["backend_runtime"])}
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
        state.write_json_atomic(self.state_path, self.state)
        state.write_text_atomic(os.path.join(self.dir, "progress.md"),
                                render.render_orchestrator_progress(self.ws.name, self.state))
