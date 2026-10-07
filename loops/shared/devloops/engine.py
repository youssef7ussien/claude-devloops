"""The loop engine (plan.md, "Iteration model", steps 1–10).

One `Engine` drives one loop run in one workspace: lock, preflight, the terminal-state
short-circuit, input fingerprints, planning, the approval pause, then milestone trials until the
run completes or stops. Every state write is atomic and happens before the action it records.

It also keeps the run safe to leave unattended (US3): interrupted trials fail and count (T051),
service failures void the trial and stop resumably (T052), `needs_input` stops the milestone at
once (T053), and `retry` grants a failed milestone more trials (T056).
"""
import importlib
import os
import re
import subprocess
import types
from dataclasses import dataclass, field

from . import (boundary, config, inputs, preflight, prompts, render, schema, selector, speckit,
               state)
from . import plan as plan_mod
from .claude import CallFailed, ClaudeRunner
from .kit import Kit
from .redact import Redactor
from .runtime import RuntimeStartFailed
from .state import EXIT_CODES, TERMINAL_STATUSES, StopRun, input_error

ADAPTER_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def load_loop_def(kit, loop):
    path = kit.path(loop, "loop.json")
    loop_def = state.read_json(path)
    if loop_def is None:
        raise state.UsageError(f"loop definition {path} not found")
    return loop_def


@dataclass
class Options:
    """What the CLI passes to a run. `None` means the flag was not given."""

    requirements: str = None
    speckit_feature: str = None   # "active" or a folder (002 FR-023); excludes `requirements`
    story_id: str = None
    story_file: bool = False
    target: str = None
    api_spec: str = None
    config_path: str = None
    cli_overrides: dict = field(default_factory=dict)
    force_unlock: bool = False


def _is_inside(path, root):
    path, root = os.path.realpath(path), os.path.realpath(root)
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def compute_pass(milestone, result, trial_dir):
    """The data-model pass rule; return `(passed, problems)`. The model's claim is never used.

    Every acceptance criterion needs a passing entry (a missing one fails, FR-068); every cited
    evidence path must exist; `playwright` entries also need a non-empty `observed` and at least
    one evidence item (FR-023); the contract and boundary must pass; enabled unit tests must exit
    0 (FR-008).
    """
    problems = []
    entries = {c.get("criterion_id"): c for c in result.get("criteria") or []}
    for criterion in milestone["acceptance_criteria"]:
        cid = criterion["id"]
        entry = entries.get(cid)
        if entry is None:
            problems.append(f"{cid}: no result")
            continue
        if not entry.get("passed"):
            problems.append(f"{cid}: failed ({(entry.get('observed') or '').strip()[:200]})")
        if result.get("kind") == "playwright":
            if not (entry.get("observed") or "").strip():
                problems.append(f"{cid}: nothing observed")
            if not entry.get("evidence"):
                problems.append(f"{cid}: no evidence")
        for path in entry.get("evidence") or []:
            if not _is_inside(os.path.join(trial_dir, path), trial_dir):
                problems.append(f"{cid}: evidence {path} is outside the trial directory")
            elif not os.path.exists(os.path.join(trial_dir, path)):
                problems.append(f"{cid}: evidence {path} does not exist")
    contract = result.get("contract") or {}
    if not contract.get("passed"):
        problems.append("contract check failed: "
                        + (", ".join(contract.get("unmatched_operations") or []) or "no detail"))
    bound = result.get("boundary") or {}
    if not bound.get("passed"):
        problems.append("boundary violated: " + ", ".join(bound.get("violations") or []))
    unit = result.get("unit_tests") or {}
    if unit.get("enabled") and unit.get("exit_code") != 0:
        problems.append(f"unit tests failed (exit code {unit.get('exit_code')}, log "
                        f"{unit.get('log_path')})")
    return not problems, problems


class Engine:
    def __init__(self, loop_name, workspace, options=None, kit=None, project=None, env=None):
        self.loop = loop_name
        self.ws = workspace
        self.opts = options or Options()
        self.kit = kit or getattr(workspace, "kit", None) or Kit.resolve()
        self.project = project or workspace.project
        self.env = dict(os.environ if env is None else env)
        self.loop_dir = workspace.loop_dir(loop_name)
        self.state_dir = os.path.join(self.loop_dir, "state")
        self.run_path = os.path.join(self.state_dir, "run.json")
        self.plan_path = os.path.join(self.state_dir, "plan.json")
        self.answers_path = os.path.join(self.loop_dir, "outputs", "open-questions.md")
        self.rs = None          # run.json
        self.plan = None
        self.config = None
        self.redactor = Redactor()
        self.message = ""
        self.loop_def = load_loop_def(self.kit, loop_name)
        # Called after each recorded event, so a view (the lightweight dashboard) can follow the
        # run; it must never raise or change the run.
        self.on_progress = None
        # `replan --no-continue` pauses at its new plan, even under questions: accept-suggested:
        # the developer asked to see it.
        self.review_plan = False
        # The command that resumes this run, for the messages: `devloops orchestrate` when the
        # workspace is orchestrated (the CLI sets it).
        self.resume_command = f"devloops run {loop_name}"
        # Set once `approve`, `replan`, or `retry` has saved its decision: an error after that is
        # not a refusal (the orchestrator keeps its record of the run).
        self.decided = False
        self.on_decided = None  # called once the decision is saved (the orchestrator records)
        # Set by the orchestrator once it has checked this loop's tools for this command.
        self.tools_checked = False

    # --- commands ----------------------------------------------------------------------------------

    def run(self):
        """Start or resume the run; return its exit code (contracts/cli.md)."""
        with self._lock():
            try:
                self._load_run()
                return self._first_start() if self.rs is None else self._resume()
            except StopRun as stop:
                return self._stop(stop)

    def approve(self, continue_run=False):
        """Accept the stored plan and the current answers (FR-053, FR-054), then, with
        `continue_run`, implement it under the same lock, like `run`."""
        with self._lock():
            self.rs = self._require_status("approve", "awaiting-approval")
            self._use_config(self.rs["effective_config"])
            if continue_run:  # a missing tool refuses the decision, rather than ending the run
                self._check_tools(self.config)
            accepted = self._approve("approve", "by `devloops approve`")
            self._mark_decided()
            self._event("approved", "plan approved with the answers in outputs/open-questions.md"
                        + self._accepted_note(accepted))
            self._render()
            if continue_run:
                return self._continue()
            self.message = f"plan approved; run `{self.resume_command}` to implement it"
            return 0

    def _continue(self):
        """Resume the run after a recorded decision, as `run` would: the same checks, then on."""
        try:
            return self._resume()
        except StopRun as stop:
            return self._stop(stop)

    def _approve(self, action, how):
        """Record the approval of the stored plan with the current answers; status `implementing`.

        An empty answer with a suggested answer accepts the suggestion: it is copied into the
        answer first, so the file the approval fingerprints says what the run will use.
        """
        if not os.path.exists(self.answers_path):
            self._render(questions=state.read_json(self.plan_path)["open_questions"])
        with open(self.answers_path, encoding="utf-8") as f:
            text, accepted = render.accept_suggestions(f.read(), how)
        if accepted:
            state.write_text_atomic(self.answers_path, text)
        sha = inputs.sha256_file(self.answers_path)
        self.rs["approval"] = {
            "approved_at": state.now_iso(), "action": action,
            "answers_path": self.answers_path, "answers_sha256": sha,
            "accepted_suggestions": accepted,
        }
        self.rs["answers_sha256"] = sha
        self.rs["status"] = "implementing"
        self._save()
        return accepted

    def _mark_decided(self):
        self.decided = True
        if self.on_decided:
            self.on_decided()

    @staticmethod
    def _accepted_note(accepted):
        return (f"; suggested answer(s) accepted for {', '.join(accepted)}, review them"
                if accepted else "")

    def replan(self, continue_run=False):
        """Plan again with the answers (research R-6). With `continue_run`, the new plan is
        handled like a first plan: approved and implemented under questions: accept-suggested,
        paused under `ask`. Without it, the run pauses at the new plan."""
        with self._lock():
            try:
                self.rs = self._require_status("replan", "awaiting-approval")
                self._use_config(self.rs["effective_config"])
                used = len(self._counted_planning_trials())
                if used >= self.config["max_trials"]:
                    raise state.UsageError(
                        f"no planning trials left ({used} of {self.config['max_trials']} used); "
                        f"approve the current plan with `devloops approve {self.loop}` or start "
                        "a new workspace")
                self._check_tools(self.config)
                self._check_fingerprints()
                if continue_run:  # a --review-plan or --accept-suggested given to this command
                    self._use_config(self._resolved_config())
                self.rs["status"] = "planning"
                self._save()
                self._mark_decided()
                self.review_plan = not continue_run
                return self._planning("replan")
            except StopRun as stop:
                return self._stop(stop)

    def retry(self, milestone_id, reason=None, trials=None, continue_run=False):
        """Grant a failed milestone more trials and move the run back to `implementing` (FR-063).

        Allowed only in `stopped-on-failure` with that milestone `failed`, and never after
        `planning-trials-exhausted`, which is final (FR-061). The grant records the current
        answers' fingerprint, which later starts compare against (T055). With `continue_run`,
        the run then resumes under the same lock, like `run`.
        """
        with self._lock():
            self._load_run()
            status = self.rs["status"] if self.rs else "not started"
            stop_reason = (self.rs or {}).get("status_reason") or {}
            if status == "stopped-on-failure" and \
                    stop_reason.get("code") == "planning-trials-exhausted":
                raise state.UsageError("`retry` cannot resume a run whose planning trials are "
                                       "exhausted; that stop is final, start a new workspace")
            if status != "stopped-on-failure":
                raise state.UsageError(f"`retry` is allowed only when the run is "
                                       f"stopped-on-failure (it is {status})")
            ms = self.rs["milestones"].get(milestone_id)
            if ms is None or ms["status"] != "failed":
                failed = [m for m, s in self.rs["milestones"].items() if s["status"] == "failed"]
                raise state.UsageError(
                    f"milestone {milestone_id} has not failed "
                    f"({'unknown' if ms is None else ms['status']}); retry "
                    + (f"--milestone {', '.join(failed)}" if failed else "has nothing to grant"))
            self._use_config(self.rs["effective_config"])
            if continue_run:  # a missing tool refuses the decision, rather than ending the run
                self._check_tools(self.config)
            accepted = []
            needs_input = stop_reason.get("code") == "needs-input" and \
                stop_reason.get("milestone_id") == milestone_id
            reason = reason or ""  # no guidance: nothing is passed to the fix prompt
            if needs_input:
                text, accepted = self._require_answers(milestone_id)
                if accepted:
                    state.write_text_atomic(self.answers_path, text)
            answers = inputs._hash_or_none(self.answers_path)
            grant = {"milestone_id": milestone_id, "granted_at": state.now_iso(),
                     "reason": reason, "extra_trials": trials or self.config["max_trials"],
                     "answers_sha256": answers}
            if accepted:
                grant["accepted_suggestions"] = accepted
            self.rs.setdefault("grants", []).append(grant)
            if answers:
                self.rs["answers_sha256"] = answers
            ms["status"] = "in-progress"
            ms["tasks"] = {t: ("pending" if s == "failed" else s) for t, s in ms["tasks"].items()}
            self.rs["status"] = "implementing"
            self.rs["status_reason"] = None
            self._save()
            self._mark_decided()
            self._event("retry-granted", f"{milestone_id}: {grant['extra_trials']} more trial(s): "
                                         f"{reason or 'no reason given'}"
                        + self._accepted_note(accepted),
                        milestone=milestone_id)
            self._render()
            if continue_run:
                return self._continue()
            self.message = (f"granted {grant['extra_trials']} more trial(s) to {milestone_id}; run "
                            f"`{self.resume_command}` to continue")
            return 0

    def _require_answers(self, milestone_id):
        """Refuse `retry` while a question of the `needs-input` stop has neither an answer nor a
        suggested answer; return `(text, accepted)`, the answers file with the suggestions of
        those questions accepted, for the caller to write.

        The grant fingerprints the answers file; answering after `retry` would change it, and the
        next `run` would then stop for good with `input-changed` (FR-051a). Questions are matched
        by their text to the stopping trial's `needs_input`.
        """
        ms = self.rs["milestones"][milestone_id]
        last = next(t for t in reversed(ms["trials"]) if t["status"] == "failed")
        doc = state.read_json(os.path.join(self._trial_dir(milestone_id, last["n"]), "trial.json"),
                              default={})
        asked = {q["question"].strip() for q in doc.get("needs_input") or []}
        try:
            with open(self.answers_path, encoding="utf-8") as f:
                text = f.read()
        except FileNotFoundError:
            text = ""
        ids = [qid for qid, q in render.parse_questions(text).items() if q["question"] in asked]
        text, accepted = render.accept_suggestions(text, "by `devloops retry`", ids)
        answers = render.parse_answers(text)
        answered = {q.strip() for q, a in answers.values() if a.strip()}
        missing = sorted(qid for qid, (q, a) in answers.items()
                         if q.strip() in asked and not a.strip())
        if missing or not asked <= answered:
            raise state.UsageError(
                f"answer {', '.join(missing) or 'the needs-input questions'} in "
                f"outputs/open-questions.md before `retry`: the grant records the answers, so "
                f"answering afterwards would stop the next run with input-changed")
        return text, accepted

    # --- start ---------------------------------------------------------------------------------------

    def check_tools(self):
        """Raise `missing-tool` now for a loop that still has work: with its frozen configuration,
        or the one its first start would freeze. Nothing is written (`orchestrate` checks both
        loops before the backend spends anything). True if it checked (a stopped or completed run
        is not)."""
        rs = state.read_json(self.run_path)
        if rs and rs["status"] in TERMINAL_STATUSES:
            return False
        if rs and rs.get("project_root") and \
                os.path.normpath(rs["project_root"]) != self.project.root:
            rs = self.project.relocate(rs, rs["project_root"])  # as the run will (not saved)
        cfg = rs["effective_config"] if rs else config.load_effective(
            self.kit.path("shared", "config", "defaults.json"),
            os.path.abspath(self.opts.config_path) if self.opts.config_path
            else self.ws.config_path(),
            self.opts.cli_overrides, self.project.run_config_layers())
        preflight.check_tools(self.loop_def, cfg, self.env)
        return True

    def _check_tools(self, cfg):
        """FR-013b, unless the orchestrator already checked this loop for this command."""
        if not self.tools_checked:
            preflight.check_tools(self.loop_def, cfg, self.env)

    def _first_start(self):
        self._event("run-started", "first run")
        workspace_config = self._workspace_config_path()
        cfg = config.load_effective(self.kit.path("shared", "config", "defaults.json"),
                                    workspace_config, self.opts.cli_overrides,
                                    self.project.run_config_layers())
        self._use_config(cfg)
        self._check_tools(cfg)
        requirements = self._requirements_input()
        req_path = requirements["path"]
        api_spec = None
        if "api_spec" in self.loop_def.get("required_inputs", []) or self.opts.api_spec:
            api_spec = inputs.check_api_spec(self.opts.api_spec, self.loop)
        self.ws.attach_requirements(requirements)
        if not self.opts.target:
            raise input_error("target-unwritable",
                              f"no target directory given; pass --target for {self.loop}")
        target = self.ws.set_target(self.loop, os.path.abspath(self.opts.target))
        self.rs = {
            "loop": self.loop, "status": "planning", "status_reason": None,
            "inputs": {"requirements": requirements, "api_spec": api_spec},
            "target_dir": target, "effective_config": cfg,
            "planning": {"trials": [], "status": "pending"}, "approval": None,
            "milestones": {}, "invocation_count": 0, "ui_url": None, "openapi_artifact": None,
            "resume_status": None, "grants": [],
            "project_root": self.project.root,
            "config_sources": config.config_sources(self.project, workspace_config),
            "config_cli_keys": config.dotted_keys(self.opts.cli_overrides),
            "prompt_sources": self._prompt_sources(),
        }
        self._save()
        if api_spec:
            inputs.freeze_api_spec(api_spec, self.state_dir)
        block = requirements.get("speckit")
        if block:
            self._event("input-check", f"spec-kit feature {block['feature_dir']}: "
                        + ", ".join(f"{key.replace('_', '.')} (sha256 {item['sha256']})"
                                    for key, item in (("plan_md", block["plan_md"]),
                                                      ("tasks_md", block["tasks_md"])) if item))
        self._event("input-check", f"requirements {req_path} (sha256 {requirements['sha256']}, "
                                   f"mode {requirements['mode']}"
                                   + (f", story {requirements['story_id']}"
                                      if requirements["story_id"] else "") + "), "
                                   + (f"API spec {api_spec['path']} (sha256 {api_spec['sha256']}), "
                                      if api_spec else "") + f"target {target}")
        self._render()
        return self._advance()

    def _requirements_input(self):
        """The requirements file, or the spec-kit feature, of a first start (002 FR-023)."""
        if self.opts.speckit_feature:
            if self.opts.requirements or self.opts.story_file:
                raise state.UsageError("--speckit-feature cannot be combined with "
                                       "--requirements or --story-file")
            feature = speckit.resolve_feature(self.opts.speckit_feature, self.project)
            return inputs.speckit_requirements(feature, self.opts.story_id)
        return inputs.requirements_input(self.opts.requirements, self.opts.story_id,
                                         self.opts.story_file)

    def _resume(self):
        status = self.rs["status"]
        self._use_config(self.rs["effective_config"])
        terminal = status in TERMINAL_STATUSES
        try:
            self._check_tools(self.config)
        except StopRun as stop:
            if not terminal:
                raise
            self.message = f"{stop.message} (the run is {status}; nothing was changed)"
            return stop.exit_code
        if terminal:
            self.message = f"the run is {status}; nothing to do"
            return EXIT_CODES[status]
        self._check_fingerprints()
        self._check_given_inputs()
        if self.rs["inputs"].get("api_spec"):
            # Byte-identical to the recorded spec (the fingerprints just matched); restores a
            # copy lost since the first start.
            inputs.freeze_api_spec(self.rs["inputs"]["api_spec"], self.state_dir)
        self._restore_after_service_error()
        self._recover_interrupted()
        self._event("run-started", f"resumed in status {self.rs['status']}")
        self._check_prompt_sources()
        self._use_config(self._resolved_config())
        self._save()
        return self._advance()

    def _resolved_config(self):
        """The frozen configuration with this start's command-line overrides (recorded)."""
        return config.resolve_for_run(
            self.rs, self.loop_dir, self.opts.cli_overrides,
            defaults_path=self.kit.path("shared", "config", "defaults.json"),
            redactor=self.redactor, project_layers=self.project.run_config_layers())

    def _prompt_sources(self):
        return prompts.sources(self.kit, self.project.root, prompts.loop_parts(self.kit, self.loop))

    def _check_prompt_sources(self):
        """Record the prompt parts that changed since the configuration was frozen (FR-032).

        Overrides are not frozen: the calls from this start use the current files. The frozen
        sources stay as they are, so `status` keeps reporting the drift until the run ends.
        """
        frozen = self.rs.get("prompt_sources")
        if frozen is None:
            return  # a run started before 002
        changed = prompts.drift(frozen, self._prompt_sources())
        if changed:
            self._event("prompt-sources-changed",
                        "prompt parts changed since the first start (used from now on): "
                        + ", ".join(changed))

    def _relocate(self):
        """Rewrite the recorded paths when the project was moved or cloned (FR-013)."""
        old = self.rs.get("project_root")
        if old and os.path.normpath(old) != self.project.root:
            self.rs = self.project.relocate(self.rs, old)
            self.rs["project_root"] = self.project.root
            self._save()
            self._event("input-check", f"project moved from {old} to {self.project.root}; "
                                       "recorded paths under it were updated")

    def _check_fingerprints(self):
        # Editing answers is expected until an approval records them (FR-051a, T055).
        skip = ("answers",) if self.rs["status"] in ("planning", "awaiting-approval") else ()
        inputs.compare_fingerprints(self.rs, inputs.current_fingerprints(self.rs), skip=skip)

    def _check_given_inputs(self):
        """Inputs passed again on a later start must match the recorded ones (D-8)."""
        recorded = self.rs["inputs"]
        req = recorded["requirements"]
        if self.opts.story_id is not None or self.opts.story_file:
            # A different selection is a mistyped command, not changed input: refuse it before
            # anything is recorded, so the run stays resumable. Omitting the flags keeps the
            # recorded selection.
            mode, story_id = inputs.story_selection(self.opts.story_id, self.opts.story_file)
            if (mode, story_id) != (req["mode"], req.get("story_id")):
                raise state.UsageError(
                    f"this run was started with mode={req['mode']} story_id="
                    f"{req.get('story_id')}, not mode={mode} story_id={story_id}; repeat the "
                    "original story options or omit them (a different story needs a new "
                    "workspace)")
        if self.opts.speckit_feature:
            # Like the story options: a different feature is a mistyped command (or another
            # feature became active), not changed input, so the run stays resumable.
            recorded_dir = (req.get("speckit") or {}).get("feature_dir")
            try:
                given = speckit.resolve_feature(self.opts.speckit_feature, self.project)
                given_dir = given["feature_dir"]
            except StopRun as e:
                given_dir, problem = None, e.message
            else:
                problem = None
            if not recorded_dir or given_dir is None or \
                    os.path.realpath(recorded_dir) != os.path.realpath(given_dir):
                raise state.UsageError(
                    "this run was started with "
                    + (f"spec-kit feature {recorded_dir}" if recorded_dir
                       else f"requirements {req['path']}")
                    + (f", but --speckit-feature gives {given_dir}" if given_dir
                       else f", and --speckit-feature cannot be used: {problem}")
                    + "; omit --speckit-feature to resume the recorded input (another feature "
                      "needs a new workspace)")
        if self.opts.requirements:
            path = inputs.check_requirements(self.opts.requirements)
            if inputs.sha256_file(path) != req["sha256"]:
                raise input_error("input-changed", f"--requirements {path} differs from the "
                                  "recorded requirements", input="requirements")
        if self.opts.api_spec and recorded.get("api_spec"):
            path = os.path.abspath(self.opts.api_spec)
            if inputs._hash_or_none(path) != recorded["api_spec"]["sha256"]:
                raise input_error("input-changed", f"--api-spec {path} differs from the recorded "
                                  "API spec", input="api-spec")
        if self.opts.target:
            self.ws.set_target(self.loop, os.path.abspath(self.opts.target))

    def _restore_after_service_error(self):
        """A service stop is resumable: restore the pre-stop status (FR-067; completed by T052)."""
        if self.rs["status"] == "stopped-on-service-error":
            self.rs["status"] = self.rs.get("resume_status") or "implementing"
            self.rs["status_reason"] = None
            self.rs["resume_status"] = None

    def _recover_interrupted(self):
        """Fail every trial left `in-progress` by a driver that died mid-trial (FR-030a, R-4).

        It becomes `failed` with reason `interrupted` and counts toward the limit, so the next
        trial of the milestone is a fix with the interruption as its previous failure.
        """
        now = state.now_iso()
        detail = "the driver stopped before the trial finished (interrupted or killed)"
        for trial in (self.rs.get("planning") or {}).get("trials", []):
            if trial["status"] == "in-progress":
                trial.update(status="failed", failure={"reason": "interrupted", "detail": detail},
                             ended_at=now)
                self._event("validation-failed", f"planning trial {trial['n']} failed: "
                                                 f"interrupted: {detail}", trial=trial["n"])
        for mid, ms in (self.rs.get("milestones") or {}).items():
            for summary in ms.get("trials", []):
                if summary["status"] != "in-progress":
                    continue
                path = os.path.join(self._trial_dir(mid, summary["n"]), "trial.json")
                doc = state.read_json(path, default={"n": summary["n"]})
                doc.update(status="failed", failure={"reason": "interrupted", "detail": detail},
                           ended_at=now)
                state.write_json_atomic(path, doc)
                summary.update(status="failed", reason="interrupted", ended_at=now)
                ms["ended_at"] = now
                self._event("validation-failed", f"trial {summary['n']} failed: interrupted: "
                                                 f"{detail}", milestone=mid, trial=summary["n"])

    # --- state machine ----------------------------------------------------------------------------------

    def _advance(self):
        while True:
            status = self.rs["status"]
            if status == "planning":
                return self._planning()
            if status == "awaiting-approval":
                if self._auto_approve():
                    continue
                self.message = (f"plan stored; review outputs/plan-summary.md, answer "
                                f"outputs/open-questions.md, then run `devloops approve "
                                f"{self.loop}` or `devloops replan {self.loop}`"
                                + self._unsuggested_note())
                return EXIT_CODES["awaiting-approval"]
            if status == "implementing":
                return self._implementing()
            return EXIT_CODES[status]

    # --- open questions ------------------------------------------------------------------------------

    def _accepts_suggested(self):
        return self.config.get("questions") == "accept-suggested"

    def _unanswerable(self):
        """IDs of questions with neither an answer nor a suggested answer."""
        try:
            with open(self.answers_path, encoding="utf-8") as f:
                questions = render.parse_questions(f.read())
        except FileNotFoundError:
            return []
        return [qid for qid, q in questions.items() if not render.effective_answer(q)[1]]

    def _unsuggested_note(self):
        missing = self._unanswerable() if self._accepts_suggested() else []
        return (f" ({', '.join(missing)} has no suggested answer, so questions: accept-suggested "
                "cannot approve it)" if missing else "")

    def _auto_approve(self):
        """Under `questions: accept-suggested`, approve the stored plan with Claude's suggested
        answers, unless a question has neither an answer nor a suggestion, or this is the
        `replan` command. True if it approved."""
        if not self._accepts_suggested() or self.review_plan or self._unanswerable():
            return False
        accepted = self._approve("auto-approve", "automatically (questions: accept-suggested)")
        self._event("approved", "plan approved automatically (questions: accept-suggested)"
                    + self._accepted_note(accepted))
        self._render()
        return True

    # --- planning -----------------------------------------------------------------------------------------

    def _planning(self, kind=None):
        kind = kind or ("replan" if os.path.exists(self.plan_path) else "plan")
        planning = self.rs.setdefault("planning", {"trials": [], "status": "pending"})
        limit = self.config["max_trials"]
        while True:
            counted = self._counted_planning_trials()
            n = len(counted) + 1
            if n > limit and kind == "replan" and os.path.exists(self.plan_path):
                # The stored plan is still valid: go back to the approval pause, don't stop.
                planning["status"] = "done"
                self.rs["status"] = "awaiting-approval"
                self._save()
                self._event("paused", f"replan used the last planning trial ({limit} of {limit}) "
                                      "without a valid plan; the previous plan still awaits "
                                      "approval")
                self._render()
                self.message = ("replan found no valid plan within the planning trials; the "
                                f"previous plan still awaits approval (`devloops approve "
                                f"{self.loop}`)")
                return EXIT_CODES["awaiting-approval"]
            if n > limit:
                planning["status"] = "failed"
                raise StopRun("stopped-on-failure", "planning-trials-exhausted",
                              f"planning failed {limit} time(s); this stop is final, start a new "
                              "workspace")
            self._check_cap()
            trial = {"n": n, "kind": kind, "status": "in-progress", "failure": None,
                     "invocations": [], "started_at": state.now_iso(), "ended_at": None}
            planning["trials"].append(trial)
            planning["status"] = "in-progress"
            self._save()
            self._event("trial-started", f"planning trial {n} ({kind})", trial=n)
            out = self._runner().call(kind, self._plan_context(kind, counted),
                                      self.rs["target_dir"], trial=n, add_dirs=self._input_dirs())
            trial["invocations"].append(out.record["session_id"])
            if not out.ok and out.failure_class == "service":
                trial.update(status="void", failure={"reason": out.failure_reason,
                                                     "detail": out.failure_detail},
                             ended_at=state.now_iso())
                self._stop_on_service_error("planning", out.failure_reason, out.failure_detail,
                                            f"planning trial {n}", trial=n)
            if not out.ok:
                self._fail_planning(trial, out.failure_reason, out.failure_detail)
                continue
            req = self.rs["inputs"]["requirements"]
            errors = plan_mod.validate_plan(out.structured_output, self.loop_def, req["mode"],
                                            req.get("story_id"))
            phases = speckit.load_phases(req.get("speckit"))
            if not errors and phases is not None:
                errors = plan_mod.validate_speckit(out.structured_output, phases,
                                                   req.get("story_id"))
            if errors:
                self._fail_planning(trial, "invalid-output", "; ".join(errors))
                continue
            plan, _ = self.redactor.redact_obj(out.structured_output)
            state.write_json_atomic(self.plan_path, plan)
            self.plan = plan
            self.rs["milestones"] = {
                m["id"]: {"status": "pending", "tasks": {t["id"]: "pending" for t in m["tasks"]},
                          "trials": [], "started_at": None, "ended_at": None}
                for m in plan["milestones"]}
            trial.update(status="passed", ended_at=state.now_iso())
            planning["status"] = "done"
            self.rs["approval"] = None
            self.rs["answers_sha256"] = None
            self.rs["status"] = "awaiting-approval"
            self._save()
            self._event("plan-stored", f"{len(plan['milestones'])} milestone(s), "
                                       f"{len(plan['open_questions'])} open question(s)", trial=n)
            self._event("paused", "awaiting approval")
            self._render(questions=plan["open_questions"])
            return self._advance()

    def _counted_planning_trials(self):
        return [t for t in (self.rs.get("planning") or {}).get("trials", [])
                if t["status"] != "void"]

    def _fail_planning(self, trial, reason, detail):
        trial.update(status="failed", failure={"reason": reason, "detail": detail},
                     ended_at=state.now_iso())
        self._save()
        self._event("validation-failed", f"planning trial {trial['n']} failed: {reason}: "
                                         f"{detail[:500]}", trial=trial["n"])
        self._render()

    def _plan_context(self, kind, counted_trials):
        req = self.rs["inputs"]["requirements"]
        ctx = {
            "loop": self.loop, "step": kind, "workspace": self.ws.name,
            "requirements": {"path": req["path"], "mode": req["mode"],
                             "story_id": req.get("story_id")},
            "api_spec": (self.rs["inputs"].get("api_spec") or {}).get("path"),
            "target_dir": self.rs["target_dir"],
            "configuration": {"runtime": self.config.get("runtime"),
                              "backend": self.config.get("backend")},
        }
        if self.loop_def.get("requires_openapi_path"):
            ctx["requires_openapi_path"] = True
        if req.get("speckit"):
            ctx["speckit"] = speckit.context(req)
        self._add_story_scope(ctx)
        self._add_frontend_block(ctx)
        failed = [t for t in counted_trials if t["status"] == "failed"]
        if failed and failed[-1] is counted_trials[-1]:
            ctx["previous_attempt"] = {"trial": failed[-1]["n"], **failed[-1]["failure"]}
        if kind == "replan":
            ctx["answers_path"] = self.answers_path
            ctx["answers"] = self._read_answers()
            ctx["previous_plan_path"] = self.plan_path
        return ctx

    # --- implementation ------------------------------------------------------------------------------------

    def _implementing(self):
        self.plan = self.plan or state.read_json(self.plan_path)
        while True:
            unit = selector.next_unit(self.rs, self.plan)
            self._save()
            if unit == "complete":
                return self._complete()
            if unit[0] == "stop":
                _, code, mid = unit
                raise StopRun("stopped-on-failure", code, self._stop_message(code, mid),
                              milestone_id=mid)
            _, mid, n = unit
            self._trial(mid, n)

    def _stop_message(self, code, mid):
        if code == "invocation-cap":
            return (f"reached max_invocations_per_run="
                    f"{self.config['max_invocations_per_run']} before milestone {mid} finished")
        ms = self.rs["milestones"][mid]
        return (f"milestone {mid} failed after {len(selector.counted_trials(ms))} of "
                f"{selector.trial_limit(self.rs, mid)} trial(s); read the last trial's "
                f"validation.json and evidence/, then run `devloops retry {self.loop} --milestone "
                f"{mid}`, with --reason to guide the fix")

    def _trial(self, mid, n):
        milestone = self._milestone(mid)
        ms = self.rs["milestones"][mid]
        kind = "implement" if n == 1 else "fix"
        trial_dir = self._trial_dir(mid, n)
        now = state.now_iso()
        trial = {"n": n, "kind": kind, "status": "in-progress", "failure": None,
                 "needs_input": [], "assumptions": [], "invocations": [], "validation": None,
                 "started_at": now, "ended_at": None}
        state.write_json_atomic(os.path.join(trial_dir, "trial.json"), trial)
        ms["status"] = "in-progress"
        ms["started_at"] = ms.get("started_at") or now
        ms["trials"].append({"n": n, "status": "in-progress", "reason": None, "started_at": now,
                             "ended_at": None})
        self._save()
        self._event("trial-started", f"trial {n} ({kind})", milestone=mid, trial=n)

        phase = "claude-error"
        try:
            adapter = self._adapter()
            if hasattr(adapter, "prepare"):
                # Runs before the implement/fix call, so whatever it freezes (e.g. the curl
                # checks) cannot be shaped by this trial's implementation (FR-069).
                phase = "invalid-output"
                adapter.prepare(self._adapter_context(milestone, n, trial_dir))
                phase = "claude-error"
            out = self._runner().call(kind, self._milestone_context(milestone, n),
                                      self.rs["target_dir"], milestone_id=mid, trial=n,
                                      trial_dir=trial_dir, snapshot=self._snapshot,
                                      add_dirs=self._input_dirs(mid, n))
            trial["invocations"].append(out.record["session_id"])
            if out.ok:
                self._record_implementation(milestone, trial, out.structured_output)
            # Audit every call, including failed ones: a write outside the target is always
            # recorded, and it outranks the call's own failure reason (R-11).
            violations = boundary.diff(out.snapshot_before, out.snapshot_after,
                                       [self.rs["target_dir"]],
                                       (self.config.get("boundary") or {}).get("allowed_extra", []))
            if violations:
                detail = "changed outside the target: " + ", ".join(violations)
                if not out.ok:
                    detail += f" (the call also failed: {out.failure_reason}: {out.failure_detail})"
                self._event("boundary-violation", detail, milestone=mid, trial=n)
                return self._finish(milestone, trial, "boundary-violation", detail)
            if not out.ok and out.failure_class == "service":
                self._void(milestone, trial, out.failure_reason, out.failure_detail)
            if not out.ok:
                return self._finish(milestone, trial, out.failure_reason, out.failure_detail)
            if self._on_needs_input(milestone, trial):
                return
            phase = "validation-failed"
            self._validate(milestone, trial, trial_dir)
        except StopRun:
            raise
        except Exception as e:  # every exception in a trial is a recorded trial failure
            if trial["status"] != "in-progress":
                raise  # the trial was already closed; this is not a trial failure
            if isinstance(e, RuntimeStartFailed):
                self._finish(milestone, trial, "runtime-start-failed", str(e))
            elif isinstance(e, CallFailed) and e.failure_class == "service":
                self._void(milestone, trial, e.reason, e.detail)  # e.g. author-checks hit a 429
            elif isinstance(e, CallFailed):  # a validator's own call, e.g. a validate-ui timeout
                self._finish(milestone, trial, e.reason, str(e))
            else:
                self._finish(milestone, trial, phase, f"driver error: {type(e).__name__}: {e}")

    def _record_implementation(self, milestone, trial, result):
        ms = self.rs["milestones"][milestone["id"]]
        for entry in result["tasks"]:
            tid = entry["task_id"]
            if entry["status"] == "implemented" and ms["tasks"].get(tid) not in (None, "achieved"):
                ms["tasks"][tid] = "implemented"
                self._event("task-implemented", f"{tid}: {entry.get('note', '')}",
                            milestone=milestone["id"], trial=trial["n"])
        # Redacted here, once: trial.json and open-questions.md both store these (FR-070).
        trial["assumptions"] = self.redactor.redact_obj(result["assumptions"])[0]
        trial["needs_input"] = self.redactor.redact_obj(result["needs_input"])[0]
        self._write_trial(milestone["id"], trial)
        self._save()

    def _on_needs_input(self, milestone, trial):
        """A non-empty `needs_input` fails the milestone at once, whatever trials remain.

        A question is not something a fix can answer (FR-055a, R-20): the questions are appended
        to `outputs/open-questions.md` for the developer, and `retry` resumes the milestone.

        Under `questions: accept-suggested`, when every question has a suggested answer and the
        milestone has a trial left to use them, the suggestions are accepted instead: only this
        trial fails, and the next trial sees the answers. Returns True then; False when there were
        no questions. On the last trial it stops as under `ask`, so the accepted answers are never
        left unused and `retry` (which accepts the suggestions) resumes the milestone.
        """
        questions = trial["needs_input"]  # redacted by _record_implementation
        if not questions:
            return False
        mid, n = milestone["id"], trial["n"]
        try:
            with open(self.answers_path, encoding="utf-8") as f:
                existing = f.read()
        except FileNotFoundError:
            existing = None
        text, ids = render.append_open_questions(existing, questions,
                                                 f"needs-input from {mid} trial {n}")
        detail = "; ".join(f"{qid}: {q['question']}" for qid, q in zip(ids, questions))
        ms = self.rs["milestones"][mid]
        if self._accepts_suggested() and all(q.get("suggested_answer") for q in questions) \
                and len(selector.counted_trials(ms)) < selector.trial_limit(self.rs, mid):
            return self._auto_answer(milestone, trial, text, ids, detail)
        state.write_text_atomic(self.answers_path, text)
        self._finish(milestone, trial, "needs-input", detail)
        selector.mark_failed(self.rs["milestones"][mid])
        self._save()
        self._event("needs-input", f"{mid} trial {n} asked {len(ids)} question(s): {detail}",
                    milestone=mid, trial=n)
        raise StopRun("stopped-on-failure", "needs-input",
                      f"milestone {mid} needs input: answer {', '.join(ids)} in "
                      f"outputs/open-questions.md (an empty answer accepts Claude's suggested "
                      f"answer), then run `devloops retry {self.loop} --milestone {mid}`",
                      milestone_id=mid)

    def _auto_answer(self, milestone, trial, text, ids, detail):
        """Accept the suggestions of `ids` in `text` (the answers file with them appended).

        The file is written once and its fingerprint saved right after, so the window in which
        a killed driver leaves them apart (and the next start sees `input-changed`) stays small.
        """
        mid, n = milestone["id"], trial["n"]
        text, accepted = render.accept_suggestions(
            text, f"automatically (questions: accept-suggested) after {mid} trial {n}", ids)
        state.write_text_atomic(self.answers_path, text)
        sha = inputs.sha256_file(self.answers_path)
        self.rs.setdefault("auto_answers", []).append({
            "milestone_id": mid, "trial": n, "question_ids": accepted,
            "answered_at": state.now_iso(), "answers_sha256": sha})
        self.rs["answers_sha256"] = sha
        self._save()
        self._finish(milestone, trial, "needs-input", detail)
        self._event("needs-input", f"{mid} trial {n} asked {len(ids)} question(s): {detail}",
                    milestone=mid, trial=n)
        self._event("answers-accepted", f"suggested answer(s) accepted automatically for "
                                        f"{', '.join(accepted)} (questions: accept-suggested); "
                                        "the next trial uses them, review them",
                    milestone=mid, trial=n)
        return True

    def _validate(self, milestone, trial, trial_dir):
        mid = milestone["id"]
        ctx = self._adapter_context(milestone, trial["n"], trial_dir)
        adapter = self._adapter()
        result = adapter.validate(ctx)
        result["boundary"] = {"passed": True, "violations": []}  # the implement audit was clean
        result.setdefault("unit_tests", {"enabled": False})
        passed, problems = compute_pass(milestone, result, trial_dir)
        errors = schema.validate(dict(result, passed=passed), "validation-result.schema.json")
        if errors:
            passed = False
            problems.append("the validation result does not match its schema: " + "; ".join(errors))
        result["passed"] = passed
        result, _ = self.redactor.redact_obj(result)
        state.write_json_atomic(os.path.join(trial_dir, "validation.json"), result)
        trial["validation"] = "validation.json"
        if not passed:
            return self._finish(milestone, trial, "validation-failed", "; ".join(problems))
        ms = self.rs["milestones"][mid]
        ms["status"] = "achieved"
        for tid in ms["tasks"]:
            ms["tasks"][tid] = "achieved"
        self._finish(milestone, trial, None, "")
        self._event("validation-passed", f"trial {trial['n']} passed", milestone=mid,
                    trial=trial["n"])
        self._event("milestone-achieved", f"{mid} {milestone['title']}", milestone=mid)
        if hasattr(adapter, "on_achieved"):
            adapter.on_achieved(ctx)
            self._save()
            self._render()
        if (self.config.get("git") or {}).get("commit_per_milestone"):
            self._commit_milestone(milestone)

    def _commit_milestone(self, milestone):
        """Commit the target's changes after an achieved milestone (A-6; off by default).

        Only paths under the target are staged and committed (`git commit -- .` from the target),
        so anything else in the repository, staged or not, is left alone. A failure, including git
        that cannot be run at all, is recorded and never fails the achieved milestone.
        """
        mid = milestone["id"]
        try:
            outcome = self._git_commit(f"feat({self.loop}): complete {mid} {milestone['title']}")
        except OSError as e:  # git missing from PATH, or the target gone
            outcome = f"failed: git could not be run: {e}"
        self._event("git-commit", outcome, milestone=mid)

    def _git_commit(self, message):
        """Commit the target's changes as `message`; return the outcome text for the event."""
        target = self.rs["target_dir"]

        def git(*args):
            return subprocess.run(["git", "-C", target, *args], capture_output=True, text=True,
                                  env=self.env)

        if git("rev-parse", "--is-inside-work-tree").stdout.strip() != "true":
            return f"skipped: target {target} is not in a git repository"
        if not git("status", "--porcelain", "--", ".").stdout.strip():
            return "skipped: the target has no changes"
        for args in (("add", "-A", "--", "."), ("commit", "-q", "-m", message, "--", ".")):
            proc = git(*args)
            if proc.returncode != 0:
                return f"failed: git {args[0]}: {(proc.stderr or proc.stdout).strip()[:500]}"
        return f"{git('rev-parse', '--short', 'HEAD').stdout.strip()} {message}"

    def _void(self, milestone, trial, reason, detail):
        """Close a trial as `void` (not counted; its number is reused) and stop resumably."""
        mid = milestone["id"]
        now = state.now_iso()
        trial.update(status="void", failure={"reason": reason, "detail": detail}, ended_at=now)
        self._write_trial(mid, trial)
        for summary in self.rs["milestones"][mid]["trials"]:
            if summary["n"] == trial["n"] and summary["status"] == "in-progress":
                summary.update(status="void", reason=reason, ended_at=now)
        self._stop_on_service_error("implementing", reason, detail, f"{mid} trial {trial['n']}",
                                    milestone=mid, trial=trial["n"])

    def _stop_on_service_error(self, resume_status, reason, detail, what, milestone=None,
                               trial=None):
        """Record the void and stop as `stopped-on-service-error`, remembering where to resume."""
        self.rs["resume_status"] = resume_status
        self._save()
        self._event("trial-voided", f"{what} voided: {reason}", milestone=milestone, trial=trial)
        self._event("service-error", f"{reason}: {detail[:500]}", milestone=milestone,
                    trial=trial)
        raise StopRun("stopped-on-service-error", reason,
                      f"Claude Code service failure ({reason}): {detail[:300]}; no trial was "
                      f"used, run `{self.resume_command}` again to resume",
                      milestone_id=milestone)

    def _finish(self, milestone, trial, reason, detail):
        """Close a trial: `reason=None` means passed. Updates trial.json, run.json, and the views."""
        mid = milestone["id"]
        now = state.now_iso()
        trial["status"] = "passed" if reason is None else "failed"
        trial["failure"] = None if reason is None else {"reason": reason, "detail": detail}
        trial["ended_at"] = now
        self._write_trial(mid, trial)
        ms = self.rs["milestones"][mid]
        for summary in ms["trials"]:
            if summary["n"] == trial["n"] and summary["status"] == "in-progress":
                summary.update(status=trial["status"], reason=reason, ended_at=now)
        ms["ended_at"] = now
        self._save()
        if reason is not None:
            self._event("validation-failed", f"trial {trial['n']} failed: {reason}: "
                                             f"{detail[:500]}", milestone=mid, trial=trial["n"])
        self._render()

    def _complete(self):
        adapter = self._adapter()
        if hasattr(adapter, "on_complete"):
            adapter.on_complete(self._adapter_context(None, None, None))
        self.rs["status"] = "completed"
        self.rs["status_reason"] = None
        self._save()
        self._event("completed", f"all {len(self.plan['milestones'])} milestone(s) achieved")
        self._render(final=True)
        self.message = "completed; see outputs/final-report.md"
        return EXIT_CODES["completed"]

    # --- stop --------------------------------------------------------------------------------------------------

    def _stop(self, stop):
        self.message = stop.message
        if self.rs is None:  # a first start that never recorded a run: nothing to protect
            self._event("stopped", f"{stop.status}: {stop.code}: {stop.message}")
            return stop.exit_code
        if self.rs["status"] in TERMINAL_STATUSES:
            return stop.exit_code  # a terminal run is never moved (T025)
        self.rs["status"] = stop.status
        self.rs["status_reason"] = stop.status_reason()
        self._save()
        self._event("stopped", f"{stop.status}: {stop.code}: {stop.message}",
                    milestone=stop.details.get("milestone_id"))
        self._render(final=stop.status in TERMINAL_STATUSES)
        return stop.exit_code

    # --- contexts ------------------------------------------------------------------------------------------------

    def _effective_runtime(self):
        runtime = dict((self.plan or {}).get("runtime") or {})
        runtime.update({k: v for k, v in (self.config.get("runtime") or {}).items()
                        if k != "ready_timeout_seconds"})
        return runtime

    def _milestone_context(self, milestone, n):
        mid = milestone["id"]
        ms = self.rs["milestones"][mid]
        req = self.rs["inputs"]["requirements"]
        ctx = {
            "loop": self.loop, "step": "implement" if n == 1 else "fix", "trial": n,
            "workspace": self.ws.name,
            "requirements": {"path": req["path"], "mode": req["mode"],
                             "story_id": req.get("story_id")},
            "api_spec": (self.rs["inputs"].get("api_spec") or {}).get("path"),
            "target_dir": self.rs["target_dir"],
            "answers_path": self.answers_path,
            "answers": self._read_answers(),
            "stack": self.plan["stack"],
            "runtime": self._effective_runtime(),
            "milestone": {
                "id": mid, "title": milestone["title"], "goal": milestone["goal"],
                "depends_on": milestone["depends_on"],
                "tasks": [t for t in milestone["tasks"] if ms["tasks"].get(t["id"]) != "achieved"],
                "acceptance_criteria": milestone["acceptance_criteria"],
            },
            "achieved_milestones": [m for m, s in self.rs["milestones"].items()
                                    if s["status"] == "achieved"],
        }
        previous = [t for t in ms["trials"] if t["n"] < n and t["status"] == "failed"]
        if n > 1 and previous:
            prev_dir = self._trial_dir(mid, previous[-1]["n"])
            doc = state.read_json(os.path.join(prev_dir, "trial.json"), default={})
            ctx["previous_failure"] = {
                "trial": previous[-1]["n"], **(doc.get("failure") or {}),
                "validation_path": os.path.join(prev_dir, "validation.json"),
                "evidence_dir": os.path.join(prev_dir, "evidence"),
            }
        guidance = [g["reason"] for g in self.rs.get("grants") or []
                    if g.get("milestone_id") == mid and g.get("reason")]
        if guidance:
            ctx["developer_guidance"] = guidance
        self._add_story_scope(ctx)
        self._add_frontend_block(ctx)
        return ctx

    def _add_story_scope(self, ctx):
        """The single-story rule, in story modes (FR-010, FR-010a; common.md "Single-story scope")."""
        req = self.rs["inputs"]["requirements"]
        if req["mode"] == "prd":
            return
        story_id = req.get("story_id")
        if story_id:
            rule = (f"Plan and implement only story `{story_id}`. Other PRD sections are context "
                    "only. If the story depends on another story that is not implemented, raise "
                    "an open question; never implement the other story. Every requirement_refs "
                    f"list must include `{story_id}`.")
        else:
            rule = ("The requirements file is one standalone story: plan and implement only that "
                    "story. If it depends on another story that is not implemented, raise an "
                    "open question; never implement the other story.")
        ctx["story_scope"] = {"mode": req["mode"], "story_id": story_id, "rule": rule}

    def _add_frontend_block(self, ctx):
        """The backend contract, for loops that take an API spec (FR-011, FR-024, FR-039)."""
        api_spec = self.rs["inputs"].get("api_spec")
        if not api_spec:
            return
        ctx["frontend"] = {
            "api_spec_path": api_spec["path"],
            "backend_base_url": config.backend_base_url(self.config),
            "rule": "Call the backend only through the operations declared in the API spec at "
                    "api_spec_path, with the methods and paths it declares. Never call an "
                    "undocumented endpoint; raise a missing operation as a question. "
                    "backend_base_url is null when no backend is configured.",
        }

    def _adapter_context(self, milestone, n, trial_dir):
        return types.SimpleNamespace(
            loop=self.loop, loop_dir=self.loop_dir, kit=self.kit, project=self.project, workspace=self.ws,
            run_state=self.rs, plan=self.plan, milestone=milestone, trial=n, trial_dir=trial_dir,
            evidence_dir=os.path.join(trial_dir, "evidence") if trial_dir else None,
            target_dir=self.rs["target_dir"], config=self.config,
            runtime=self._effective_runtime(), runner=self._runner(), redactor=self.redactor,
            env=self.env, api_spec_path=(self.rs["inputs"].get("api_spec") or {}).get("path"),
            input_dirs=self._input_dirs(),
            context=self._milestone_context(milestone, n) if milestone else None)

    def _input_dirs(self, mid=None, n=None):
        """Directories a read-only step may read outside the target: the inputs and answers."""
        dirs = [os.path.dirname(self.rs["inputs"]["requirements"]["path"]),
                os.path.dirname(self.answers_path)]
        if self.rs["inputs"].get("api_spec"):
            dirs.append(os.path.dirname(self.rs["inputs"]["api_spec"]["path"]))
        if os.path.exists(self.plan_path):
            dirs.append(self.state_dir)
        if mid and n and n > 1:
            dirs.append(os.path.join(self.state_dir, "milestones", mid, "trials"))
        return dirs

    # --- helpers -----------------------------------------------------------------------------------------------

    def _lock(self):
        from .workspace import locked
        return locked(self.loop_dir, self.opts.force_unlock)

    def _adapter(self):
        name = self.loop_def.get("validator", "")
        if not ADAPTER_NAME_RE.match(name):
            raise state.UsageError(f"invalid validator name {name!r} in loop.json")
        return importlib.import_module(f".validators.{name}", __package__)

    def _workspace_config_path(self):
        if self.opts.config_path:
            path = os.path.abspath(self.opts.config_path)
            if self.ws.config_path() != path:
                self.ws.data["config_path"] = self.project.relative_or_absolute(path)
                self.ws.save()
            return path
        return self.ws.config_path()

    def _load_run(self):
        """Read `run.json` into `self.rs` (None before the first start), relocating its paths
        when the project was moved or cloned (FR-013). Every command that reads it uses this."""
        self.rs = state.read_json(self.run_path)
        if self.rs is not None:
            self._relocate()
        return self.rs

    def _require_status(self, command, expected):
        rs = self._load_run()
        status = rs["status"] if rs else "not started"
        if status != expected:
            raise state.UsageError(f"`{command}` is allowed only when the run is {expected} "
                                   f"(it is {status})")
        return rs

    def _use_config(self, cfg):
        self.config = cfg
        self.redactor = Redactor(cfg, environ=self.env)

    def _runner(self):
        return ClaudeRunner(self.kit, self.loop, self.loop_dir, self.config, self.redactor,
                            self.rs, env=self.env, project_root=self.project.root)

    def _snapshot(self):
        targets = [self.rs["target_dir"]] + [p for loop, p in self.ws.targets().items()
                                             if loop != self.loop]
        return boundary.snapshot(self.kit, self.loop_dir, targets, self.project.root)

    def _check_cap(self):
        cap = self.config["max_invocations_per_run"]
        if self.rs.get("invocation_count", 0) >= cap:
            raise StopRun("stopped-on-failure", "invocation-cap",
                          f"reached max_invocations_per_run={cap}")

    def _milestone(self, mid):
        return next(m for m in self.plan["milestones"] if m["id"] == mid)

    def _trial_dir(self, mid, n):
        return os.path.join(self.state_dir, "milestones", mid, "trials", str(n))

    def _write_trial(self, mid, trial):
        state.write_json_atomic(os.path.join(self._trial_dir(mid, trial["n"]), "trial.json"),
                                trial)

    def _read_answers(self):
        try:
            with open(self.answers_path, encoding="utf-8") as f:
                return self.redactor.redact(f.read())[0]
        except FileNotFoundError:
            return None

    def _save(self):
        state.write_json_atomic(self.run_path, self.rs)

    def _event(self, type, message, milestone=None, trial=None):
        state.record_event(self.loop_dir, type, message, milestone=milestone, trial=trial,
                           redactor=self.redactor)
        if self.on_progress:
            self.on_progress()

    def _render(self, final=False, questions=None):
        render.render_all(self.loop_dir, self.loop, self.ws.name, self.kit, final=final,
                          questions=questions)


# --- status (read-only) ------------------------------------------------------------------------------------

def status_object(workspace, loop):
    """The `status --json` object for one loop (contracts/cli.md); reads state only."""
    loop_dir = workspace.loop_dir(loop)
    rs = state.read_json(os.path.join(loop_dir, "state", "run.json"))
    out = {"workspace": workspace.name, "loop": loop, "status": "not-started",
           "status_reason": None, "next_milestone": None, "trials_used": None,
           "trial_limit": None, "last_failure": None, "ui_url": None, "openapi_artifact": None,
           "invocation_count": 0, "progress": os.path.join(loop_dir, "progress.md"),
           "config_drift": [], "prompt_drift": [], "full_dashboards": full_dashboards(workspace)}
    if rs is None:
        return out
    out["config_drift"] = _config_drift(workspace, rs)
    out["prompt_drift"] = _prompt_drift(workspace, loop, rs)
    plan = state.read_json(os.path.join(loop_dir, "state", "plan.json"))
    block = ((rs.get("inputs") or {}).get("requirements") or {}).get("speckit")
    if block:
        out["speckit_feature"] = block.get("feature_dir")  # the folder used (002 FR-024)
    out.update(status=rs["status"], status_reason=rs.get("status_reason"),
               ui_url=rs.get("ui_url"), openapi_artifact=rs.get("openapi_artifact"),
               invocation_count=rs.get("invocation_count", 0))
    failures = [dict(milestone_id=None, trial=t["n"], **(t.get("failure") or {}))
                for t in (rs.get("planning") or {}).get("trials", []) if t["status"] == "failed"]
    for m in (plan or {}).get("milestones", []):
        ms = rs["milestones"].get(m["id"], {})
        if out["next_milestone"] is None and ms.get("status") != "achieved":
            out.update(next_milestone=m["id"], trials_used=len(selector.counted_trials(ms)),
                       trial_limit=selector.trial_limit(rs, m["id"]))
        for t in ms.get("trials", []):
            if t["status"] == "failed":
                doc = state.read_json(os.path.join(loop_dir, "state", "milestones", m["id"],
                                                   "trials", str(t["n"]), "trial.json"), default={})
                failures.append(dict(milestone_id=m["id"], trial=t["n"],
                                     **(doc.get("failure") or {"reason": t.get("reason")})))
    if plan is None and rs.get("planning"):
        counted = [t for t in rs["planning"]["trials"] if t["status"] != "void"]
        out.update(trials_used=len(counted), trial_limit=rs["effective_config"]["max_trials"])
    out["last_failure"] = failures[-1] if failures else None
    return out


def full_dashboards(workspace):
    """`{count, bytes, latest}` of the workspace's full dashboards (002 FR-036a); read-only."""
    from .dashboard import list_full_dashboards
    found = list_full_dashboards(workspace)
    return {"count": len(found), "bytes": sum(i["bytes"] for i in found),
            "latest": found[0]["path"] if found else None}


def _prompt_drift(workspace, loop, rs):
    """Prompt parts changed since the configuration was frozen, until the run ends (FR-032)."""
    project = getattr(workspace, "project", None)
    if project is None or rs.get("prompt_sources") is None or rs.get("status") == "completed":
        return []
    try:
        now = prompts.sources(workspace.kit, project.root, prompts.loop_parts(workspace.kit, loop))
    except OSError:
        return []  # status stays read-only and never fails on this
    return prompts.drift(rs["prompt_sources"], now)


def _config_drift(workspace, rs):
    """Keys whose value would differ if this run started now (FR-015); read-only."""
    project = getattr(workspace, "project", None)
    if project is None:
        return []
    return config.drift(rs, project, workspace.config_path(),
                        workspace.kit.path("shared", "config", "defaults.json"))
