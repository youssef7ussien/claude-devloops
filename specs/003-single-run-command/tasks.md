---

description: "Task list for 003: one command to run devloops"
---

# Tasks: One Command to Run Devloops

**Input**: Design documents from `specs/003-single-run-command/` (spec.md, plan.md, research.md,
data-model.md, contracts/cli.md, contracts/skills.md, quickstart.md)

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Included. The spec gives an independent test per story and SC-006 requires the full
suite to pass. Run the suite with `VISUAL=true EDITOR=true timeout 900 python3 -m unittest discover
-s loops/shared/tests` (589 tests and about 7 minutes before this feature).

**Organization**: Tasks are grouped by user story. Paths are repository-relative. Code is in
`loops/shared/devloops/` and tests are in `loops/shared/tests/`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: The user story the task belongs to (US1–US4)

## Test migration rule (used by several tasks)

The default test project (`tests/helpers.py`, `make_project`) has no `targets`.

**Converting a test:**
- `["run", "backend-dev", …, "--target", X]` becomes `["run", …, "--backend-target", X]`. The run
  then includes only backend-dev (backend-only), so the test behaves as before.
- `["run", "backend-dev"]` on a resume becomes `["run"]`.
- `["approve"|"replan"|"retry", "<loop>", …]` drops the loop.
- `["orchestrate", …]` becomes `["run", …]`.

**Updating assertions:**
- Paths `orchestrator/state.json` and `orchestrator/progress.md` become `run/…`.
- The JSON key `orchestrator` becomes `run`.
- The text `orchestrator: <status>` becomes `run: <status>`.

---

## Phase 1: Setup

**Purpose**: The governance change the feature depends on (FR-019) and schema wording.

**⚠️ GATE**: Finish T001 before any code task. Until Principle VI is amended, the spec conflicts with
a constitution MUST (analysis C1).

- [X] T001 Amend Principle VI in `.specify/memory/constitution.md` to version 2.0.0 (MAJOR), as in research R-12:
  - replace the bullet "Backend and frontend loops SHOULD remain independently executable; orchestration MUST be optional…" with the R-12 wording;
  - add a Sync Impact Report entry at the top: motivation, affected Principle VI, migration impact on spec 001 FR-039/FR-040 and the spec 002 commands, and the temporary deviation for frontend-only runs until feature 004;
  - set `**Version**: 2.0.0` and `**Last Amended**: 2026-10-09`.
- [X] T002 [P] Update the `targets.backend-dev` / `targets.frontend-dev` property descriptions in `loops/shared/schemas/project-config.schema.json` to say "a folder, or null / missing: the project does not use this loop". Copy the file byte-identically to `specs/002-devloops-init/contracts/project-config.schema.json` (`tests/test_schemas_sync.py` checks this).

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: Loop selection and the run record. Every story depends on these.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 Add `select_loops(project, ws, backend_target=None, frontend_target=None, target_root=None)` to `loops/shared/devloops/orchestrator.py` (research R-2, spec FR-005, FR-005a). It returns an ordered `{loop: absolute target}` for `LOOP_ORDER`. For each loop, the first rule that applies wins:
  1. `ws.target(loop)` when `ws` is not None. If the explicit flag for that loop names a different real path, raise `state.UsageError` (exit 2) with `"<loop>'s target is recorded as <recorded>; --<backend|frontend>-target <given> differs (start a new workspace to change it)"`.
  2. The explicit flag (absolute path).
  3. `project.targets[loop]` when not None, replaced by `<target_root>/backend` or `<target_root>/frontend` when `target_root` is given.

  A loop matched by none of these is omitted. `--target-root` never adds a loop the project leaves out.
- [X] T004 Add `check_selection(selected)` to `loops/shared/devloops/orchestrator.py`, which raises `state.StopRun("stopped-on-input-error", code, message)` (exit 30):
  - empty selection: code `no-loop`, message `no loop to run: set targets.backend-dev or targets.frontend-dev in .devloops/devloops.json (or run devloops init)`;
  - `frontend-dev` without `backend-dev`: code `frontend-needs-backend`, message `frontend-dev needs backend-dev in the same run: set targets.backend-dev in .devloops/devloops.json (frontend-only runs are not supported yet)`.

  These are spec FR-006 and contracts/cli.md.
- [X] T005 Rework `Orchestrator` in `loops/shared/devloops/orchestrator.py` (research R-5, R-9; spec FR-001–FR-003, FR-007, FR-016, FR-016a):
  - **Folder:** `self.dir` becomes `<ws>/run`. An `orchestrator/` folder is never read or deleted.
  - **Options:** `OrchestrateOptions` gains `max_trials` and `selected` (the `{loop: target}` from T003).
  - **`run(action)`:**
    - records each selected target with `ws.set_target`;
    - checks tools only for selected loops with work left (`_check_tools`);
    - runs the selected loops in order;
    - after `backend-dev` completes, always records `state["handoff"]`, even when `frontend-dev` is not selected;
    - sets `status` to `completed` only when every selected loop is completed, and back to `running` when a newly selected loop has work.
  - **Steps:** `_step` creates steps only for selected loops.
  - **Loop options:** `_loop_options` adds `cli_overrides["max_trials"]` when given.
  - **Messages:** `resume_command` becomes `"devloops run"`. Update the module docstring to describe the single run command.
  - **Decision guard:** keep the existing check "frontend-dev has not started: backend-dev is not completed" for decisions.
- [X] T006 [P] Update the run progress text in `loops/shared/devloops/render.py`. Keep the function name `render_orchestrator_progress`, because internal names stay (research R-1). Change only what it renders:
  - the title becomes "Run";
  - "Run `devloops orchestrate` again to resume" becomes "Run `devloops run` again to resume";
  - the next-step line around line 585 says `devloops approve` with no loop.
- [X] T007 [P] Unit tests for `select_loops` and `check_selection` in a new `loops/shared/tests/test_select_loops.py`. Build the project and workspace with `tests/helpers.py`. Cover:
  - both targets; backend only; `null` and missing keys;
  - a recorded target that wins over the project;
  - the same flag accepted, and a different flag raising UsageError;
  - an explicit flag turning on a `null` loop;
  - `--target-root` placing only the project's loops;
  - the `no-loop` and `frontend-needs-backend` codes.

**Checkpoint**: selection and the run record are ready. The CLI still needs wiring (US1).

---

## Phase 3: User Story 1 – Run everything with one command (Priority: P1) 🎯 MVP

**Goal**: `devloops run` (no loop) runs backend-dev, the handoff, then frontend-dev. `approve`,
`replan`, and `retry` take no loop name and continue the whole run. "Orchestrator" becomes "run"
everywhere a developer sees it.

**Independent Test**:
1. In a temporary project with both targets, using the fake Claude, run `devloops run`.
2. Run `devloops approve` at each plan pause.
3. Confirm:
   - both loops complete;
   - `run/state.json` has the handoff;
   - `orchestrate` and `run backend-dev` exit 2.

### Tests for User Story 1

- [X] T008 [US1] Rename `loops/shared/tests/test_orchestrator.py` to `loops/shared/tests/test_run_command.py` and apply the test migration rule. Rewrite its module docstring for `devloops run`. Add tests for:
  - `run backend-dev` and `orchestrate` exiting 2 with nothing written (FR-008);
  - `--json` returning the `run` key, and text output showing `run: <status>`;
  - `--max-trials 1` applying to both loops (a `config-override` event in each `run.json`);
  - a workspace holding an old `orchestrator/state.json` continuing with a new `run/` and skipping a completed backend (FR-016a).
- [X] T009 [P] [US1] Migrate `loops/shared/tests/test_continue.py` with the test migration rule. Add tests for:
  - `approve` / `replan` with no loop applying to the loop in `awaiting-approval`;
  - `retry --milestone M01` with no loop applying to the loop in `stopped-on-failure`;
  - `approve` when nothing awaits approval exiting 2 with `nothing awaits approval (run: <status>)` and nothing changed;
  - `retry` when no loop is stopped on failure exiting 2 with `no loop is stopped on failure (run: <status>)`;
  - `--no-continue` recording the decision only, and the next `devloops run` continuing (FR-009, FR-010).
- [X] T010 [P] [US1] Add a frontend-engine test helper to `loops/shared/tests/helpers.py`, research R-11. `run_frontend_engine(t, *, requirements, target, api_spec, config, workspace, extra_env)` runs `python3 -c` in a subprocess with `t.env`, which imports `devloops.engine` from `t.root/loops/shared` and runs `engine.Engine("frontend-dev", ws, engine.Options(requirements=…, target=…, api_spec=…, config_path=…))`. It returns `(exit_code, stdout, stderr)` like `run_cli`, printing the engine's message on stdout.
- [X] T011 [US1] Migrate `loops/shared/tests/test_frontend_loop.py` (`first_run` and every frontend run) and the frontend part of `loops/shared/tests/test_reusability.py` (about lines 205–240) to `helpers.run_frontend_engine` from T010. Keep every assertion about missing or invalid API specs and input changes; where they asserted the `--api-spec` flag name, assert the `api-spec` input name instead. Depends on T010.
- [X] T012 [P] [US1] Migrate the remaining tests that call `run <loop>`, `orchestrate`, or decisions with a loop, using the test migration rule:
  - `test_backend_loop.py`, `test_engine_core.py`, `test_project_runs.py`, `test_speckit.py`, `test_suggested_answers.py`, `test_full_dashboard.py`, `test_prompt_overrides.py`, `test_limits.py`, `test_recovery.py`, `test_dashboard.py`, `test_needs_input.py`, `test_service_errors.py`;
  - `test_reusability.py` (backend part, about lines 190–199), `test_progress.py`, `test_story_input.py`, `test_project.py`, `test_no_app_specifics.py`, `test_git_commit.py`, `test_status_evidence.py`, `test_serve.py`, `test_init.py`, `test_export.py`, `test_conversations.py`, and `stub_loop.py`.

  All are under `loops/shared/tests/`. Use `grep -rn '"run", "\(backend\|frontend\)-dev"\|"orchestrate"\|orchestrator' loops/shared/tests` to find each site.

### Implementation for User Story 1

- [X] T013 [US1] Replace the `run` and `orchestrate` subparsers in `build_parser` (`loops/shared/devloops/cli.py`), contracts/cli.md:
  - **`run`:** no positional argument. Options: `--requirements` / `--speckit-feature`, the story options, `--target-root`, `--backend-target`, `--frontend-target`, `--max-trials`, the questions options, the progress options, `--force-unlock`. Help text: "start or resume the run: backend-dev, then frontend-dev, as the project configures".
  - **Removed:** the `orchestrate` subparser, and the `--target` and `--api-spec` options.
  - **Decisions:** remove the `loop` positional from `approve`, `replan`, and `retry`.
  - **`--no-continue` help:** "the run continues on the next `devloops run`".
  - **`status`:** keep its optional loop.
- [X] T014 [US1] Rewrite `_orchestrate` in `loops/shared/devloops/cli.py` as `_run(args, kit, project, env, action=None)`:
  1. Open the workspace without creating it (`workspace.open_workspace(..., create=False)`); when it does not exist, use `ws=None`.
  2. Fill requirements and story with `_project_defaults`.
  3. Compute the selection with `orchestrator.select_loops`, then call `orchestrator.check_selection`. That check raises before anything is created; FR-006 requires that no workspace exists.
  4. Only then create the workspace.
  5. Build `OrchestrateOptions(selected=…, max_trials=args.max_trials, …)` and run.
  6. Output: print `run: <status>` instead of `orchestrator: <status>`. Print only selected loops (FR-016b). In `--json`, use the key `run` instead of `orchestrator`. On a decision, keep `decision: {command, loop}`. The full-dashboard trigger becomes `"run"`.

  The exit-30 `--json` shape is exactly `{"exit_code": 30, "status_reason": {"code", "message"}}` (FR-006). Make the top-level `StopRun` handler in `main` print this when no workspace exists.
- [X] T015 [US1] Rewrite `_loop_command` in `loops/shared/devloops/cli.py` as `_decide(args, kit, project, env)` for `approve`, `replan`, and `retry` (research R-4):
  1. Open the workspace (it must exist).
  2. Find the waiting loop among `orchestrator.select_loops(project, ws)` (FR-005, no flags) in `LOOP_ORDER`, using `engine.status_object`:
     - `approve` / `replan`: `awaiting-approval`;
     - `retry`: `stopped-on-failure`.
  3. If none waits, raise `state.UsageError`: `nothing awaits approval (run: <run status>)` or `no loop is stopped on failure (run: <run status>)`. `<run status>` is read from `run/state.json`, or `not started`.
  4. Without `--no-continue`, call `_run(args, …, action=(loop, decide))`. With `--no-continue`, run `decide` on a single `Engine` and then `Orchestrator.sync_step(loop)`, as today.
  5. Delete `_orchestrated`, the single-loop continue path, and every `"devloops orchestrate"` string. Keep the `--review-plan` / `--accept-suggested` + `--no-continue` refusal, with its text saying "pass them to the next `devloops run`".
- [X] T016 [US1] Update the terminal review prompt in `loops/shared/devloops/cli.py`: `_review` prints ``The plan awaits approval: `devloops approve` approves it and continues.`` and its synthesized `argparse.Namespace` drops `loop` and calls `_decide`. Update `main`'s dispatch: `run` → `_run`; `approve` / `replan` / `retry` → `_decide`; no `orchestrate`.
- [X] T017 [P] [US1] Remove loop names from the command hints in `loops/shared/devloops/engine.py` (research R-10, FR-011):
  - `self.resume_command` defaults to `"devloops run"` (line about 131);
  - `devloops approve {self.loop}`, `devloops replan {self.loop}`, and `devloops retry {self.loop} --milestone …` (lines about 220, 577, 635, 752, 881) drop `{self.loop}`;
  - update the comments that mention `devloops orchestrate`.
- [X] T018 [P] [US1] Remove loop names from the hints in `loops/shared/devloops/render.py`: the plan-summary hint at about line 354 becomes `devloops approve --workspace <ws>` / `devloops replan --workspace <ws>`.
- [X] T019 [US1] Update `loops/shared/devloops/dashboard.py` (research R-9, R-10; FR-011, FR-016, FR-016b):
  - **State:** `collect` reads `<ws>/run/state.json` into `data["run"]` (the key was `orchestrator`).
  - **View:** `orchestrator_view` → `run_view`, with the view id `run` and the title "Run". The nav link and `views` list follow.
  - **Next-step hints** (about lines 519–533): `devloops approve`, `devloops replan`, `devloops retry --milestone <id> --reason "…"`, `devloops run`, all without a loop.
  - **Shown loops:** only `orchestrator.select_loops(project, ws)` with no flags (FR-016b, research R-9). A loop the project does not use is never listed as not started. `collect` needs the project, so pass `ws.project`.
  - **Docstring:** the module docstring names `run/state.json`.
- [X] T020 [US1] Update the `status` handler in `loops/shared/devloops/cli.py`, in `main` around line 884 (FR-016b, contracts/cli.md `status`):
  - **Without a loop:** list `orchestrator.select_loops(project, ws)` (no flags) instead of `LOOPS`.
  - **Run status:** when `<ws>/run/state.json` exists, text output first prints `run: <status>`, and `--json` adds `"run": <state>`.
  - **With a loop:** unchanged.

  Add tests to `loops/shared/tests/test_run_command.py`:
  - in a backend-only workspace, `status` lists only backend-dev and starts with `run: completed`;
  - `status --json` has `run` and `loops` with only `backend-dev`.
- [X] T021 [P] [US1] Update `loops/shared/devloops/fulldash.py`:
  - the file-tree group `orchestrator` becomes `run`, with `top == "run"` (about lines 420–427);
  - it uses `dashboard.run_view` (about line 709);
  - trigger labels name `run`.

  Depends on T019 for the name.
- [X] T022 [US1] Run `VISUAL=true EDITOR=true timeout 900 python3 -m unittest discover -s loops/shared/tests` and fix every failure caused by Phase 2 and US1 until the suite passes.

**Checkpoint**: MVP. `devloops run` is the only run path; decisions need no loop; naming is "run".

---

## Phase 4: User Story 2 – A project with only a backend (Priority: P1)

**Goal**: `init --no-frontend` (or `none` at the prompt) gives a backend-only project. `devloops
run` completes after the backend, and `check` does not need frontend tools.

**Independent Test**:
1. `init --no-prompt --no-frontend --requirements prd.md`.
2. `devloops run`.
3. Confirm only backend-dev ran, the run completed, and the handoff was recorded.
4. `devloops check --json` without a browser reports `ready: true` and the browser item `unused`.

### Tests for User Story 2

- [ ] T023 [P] [US2] Add tests to `loops/shared/tests/test_init.py`:
  - `--no-frontend` and `--no-backend` write `null`;
  - `--no-backend` with `--backend-target` exits 2;
  - `--no-backend --no-frontend` exits 2 and writes no `.devloops/`;
  - at the pseudo-terminal prompt, `None ` (any case, trimmed) gives `null`, `./none` gives a folder, and answering none twice is refused with `a project needs at least one loop` before asking again;
  - the final hint names `devloops run`.
- [ ] T024 [P] [US2] Add tests to `loops/shared/tests/test_check.py`:
  - in a backend-only project, `playwright-mcp`, `browser`, and `display` are `unused` with detail `not used by this project (frontend-dev)` and no fix;
  - `ready` stays true and the exit code is 0 with no browser;
  - `--json` has `"loops": ["backend-dev"]`;
  - outside a project, both loops are listed.
- [ ] T025 [P] [US2] Add backend-only tests to `loops/shared/tests/test_run_command.py`:
  - a project with `targets: {"backend-dev": "backend", "frontend-dev": null}` completes with exit 0 after backend-dev, with `run: completed`, the handoff in `run/state.json`, no `frontend-dev/` folder, and `status` / the dashboard data listing only backend-dev (FR-007, FR-016b);
  - after the project sets `targets.frontend-dev`, the next `devloops run` starts frontend-dev from the recorded handoff without re-running the backend (US2 scenario 4).

### Implementation for User Story 2

- [ ] T026 [US2] Implement the init options in `loops/shared/devloops/initcmd.py` and `loops/shared/devloops/cli.py` (FR-013, FR-014, research R-7):
  - **Flags:** `--no-backend` and `--no-frontend`, each in a mutually exclusive group with its `--*-target` flag. `InitOptions` gains `no_backend` and `no_frontend`. Add both to the `--upgrade` "does not change the project configuration" list.
  - **Prompt:** in `_ask_answers` (about lines 251–266), the answer `none` (`answer.strip().lower() == "none"`) records `None` without calling `check_targets`. If both end up `None`, print `a project needs at least one loop` and ask for that target again.
  - **No-prompt:** with `--no-prompt`, both none raises `state.UsageError` before anything is written.
  - **Writing:** `default_project_config` writes `null` for a `None` target.
  - **Next line:** at about line 670 it reads ``Next: `devloops check`, then `devloops run` ``, and the requirements hint at about line 457 says "to run".
- [ ] T027 [US2] Implement the check changes in `loops/shared/devloops/checkcmd.py` (FR-015, research R-8):
  - `run_checks` computes the project's loops: `[loop for loop, t in project.targets.items() if t]`, or both when there is no project.
  - Any item whose `needed_for` contains no included loop and is not `all` becomes `{"status": "unused", "detail": "not used by this project (<loops>)", "fix": None}`.
  - `ready` ignores `unused`.
  - The result gains `"loops"`.
  - `print_result` prints `unused` in the status column.

**Checkpoint**: backend-only projects work end to end.

---

## Phase 5: User Story 3 – A wrong setup stops before anything runs (Priority: P1)

**Goal**: No loop, or a frontend without a backend, exits 30 before any workspace, lock, or Claude
call.

**Independent Test**:
1. Set both targets to `null` and run `devloops run --json`.
2. Confirm exit 30, code `no-loop`, and no `workspaces/<name>` folder.
3. Repeat with only the frontend set, expecting `frontend-needs-backend`.

### Tests for User Story 3

- [ ] T028 [P] [US3] Add tests to `loops/shared/tests/test_run_command.py` (FR-006, SC-003):
  - **Both `null`:** `devloops run --json` exits 30, prints exactly `{"exit_code": 30, "status_reason": {"code": "no-loop", "message": …}}`, creates no workspace folder, and makes no fake-Claude calls (the fake log is empty).
  - **Missing `targets`:** the same.
  - **Frontend only:** code `frontend-needs-backend`.
  - **Text mode:** prints the message lines from contracts/cli.md.
  - **Explicit flag:** `--frontend-target X` in a backend-less project gives `frontend-needs-backend`.
  - **Timing:** each stop takes under 1 s (measured around `run_cli`).

### Implementation for User Story 3

- [ ] T029 [US3] T014 owns the exit-30 handling. This task only closes the gaps the T028 tests reveal in `loops/shared/devloops/cli.py`:
  - the `StopRun` from `orchestrator.check_selection` arrives before `workspace.open_workspace(create=True)` or any lock;
  - text mode prints `devloops: <message>` on stderr;
  - `--json` prints only the FR-006 object.

**Checkpoint**: a wrong setup never spends a trial or leaves a run behind.

---

## Phase 6: User Story 4 – Drive it from Claude Code (Priority: P2)

**Goal**: the skills run the new commands without loop names; `devloops-orchestrate` is gone.

**Independent Test**: render the skills into a temporary project and confirm:
- `devloops-run` runs `devloops run $ARGUMENTS --json`;
- no decision skill passes a loop;
- there is no `devloops-orchestrate`.

### Tests for User Story 4

- [ ] T030 [P] [US4] Update `loops/shared/tests/test_skills.py` and `loops/shared/tests/test_repo_skills.py`:
  - the expected skill set no longer contains `devloops-orchestrate`;
  - `devloops-run`'s argument hint has no `<backend-dev|frontend-dev>`;
  - approve, replan, and retry argument hints have no `<loop>`.

  Add a test to `loops/shared/tests/test_upgrade.py`: an unchanged installed `devloops-orchestrate/SKILL.md` is removed by `init --upgrade`, and a changed one is reported as "no longer part of devloops" (FR-017).

### Implementation for User Story 4

- [ ] T031 [US4] Delete `loops/shared/skills/devloops-orchestrate/`. Rewrite `loops/shared/skills/devloops-run/SKILL.md` per contracts/skills.md:
  - description: "Start or resume the devloops run in this project (backend-dev, then frontend-dev, as the project configures), then summarize its status";
  - argument hint without a loop;
  - body that runs `{{DEVLOOPS}} run $ARGUMENTS --json` and summarizes the `run` and `loops` keys.
- [ ] T032 [P] [US4] Update `loops/shared/skills/devloops-approve/SKILL.md`, `loops/shared/skills/devloops-replan/SKILL.md`, and `loops/shared/skills/devloops-retry/SKILL.md`:
  - descriptions say "the waiting loop";
  - argument hints and bodies pass no loop name (contracts/skills.md);
  - no prose asks the user for a loop.
- [ ] T033 [US4] Run `VISUAL=true EDITOR=true bin/devloops init --upgrade` at the repository root to re-render `.claude/skills/` and `.devloops/manifest.json`. Confirm `.claude/skills/devloops-orchestrate/` is removed. If it is reported as changed, delete it by hand and say so.

**Checkpoint**: Claude Code drives the single command.

---

## Phase 7: Polish & cross-cutting concerns

- [ ] T034 [P] Update `loops/README.md`, adding notes pointing to spec 003 (FR-018):
  - **Commands table:** `run` (no loop) replaces `run <loop>` and `orchestrate`; decisions take no loop.
  - **New "Backend-only projects" text:** `init --no-frontend`, `none`, `null` targets.
  - **The "frontend-dev on its own" section:** replace it with a note that frontend-only runs come in a later feature.
  - **Exit-30 setup errors:** document them.
  - **Renaming:** `run/` instead of `orchestrator/` in the workspace layout and the "Run" dashboard view.
  - **`check`:** the `unused` status.
  - **Examples:** remove every `orchestrate`, `run backend-dev`, `run frontend-dev`, and `--api-spec` example.
- [ ] T035 [P] Update spec 001's living documents in place, each changed passage with a note "Revised by specs/003-single-run-command":
  - `specs/001-reusable-dev-loops/spec.md`: FR-039, FR-040, the FR-056a/FR-056b wording, and User Story 5 scenario 3;
  - `specs/001-reusable-dev-loops/contracts/cli.md`:
    - the `run` section (no loop, the new options);
    - remove the `orchestrate` section;
    - `approve`, `replan`, and `retry` without a loop;
    - "Continuing after a decision" (always the whole run);
    - the skills paragraph;
  - `specs/001-reusable-dev-loops/contracts/workspace-layout.md`: `orchestrator/` becomes `run/`.

  Do not edit tasks.md, validation-results.md, research.md, plan.md, data-model.md, or earlier clarification sessions (spec FR-018).
- [ ] T036 [P] Update spec 002's living documents in place, with the same notes:
  - `specs/002-devloops-init/spec.md`: the command names in FR-007, FR-019, FR-020, FR-023, FR-039a, and the US2 scenarios naming `orchestrate`, plus FR-018's statuses, which gain `unused` (not used by the project's loops);
  - `specs/002-devloops-init/contracts/cli.md`:
    - the `run`/`orchestrate` section;
    - init's `--no-backend` / `--no-frontend` and `none`;
    - the next-command line;
    - check's `unused` status and `loops`;
  - `specs/002-devloops-init/contracts/skills.md`: the table, from contracts/skills.md in this feature;
  - `specs/002-devloops-init/contracts/project-layout.md`: the skills list without `orchestrate`, and the targets text;
  - `specs/002-devloops-init/contracts/full-dashboard.md`: "orchestrator" becomes "run".
- [ ] T037 Check SC-005 with `grep -rn "orchestrate\|run backend-dev\|run frontend-dev\|run <loop>\|--api-spec" loops/README.md loops/shared/skills .claude/skills specs/001-reusable-dev-loops/contracts specs/002-devloops-init/contracts`. Fix any match that is not inside a "removed" or "revised by 003" note.
- [ ] T038 Run the full suite: `VISUAL=true EDITOR=true timeout 900 python3 -m unittest discover -s loops/shared/tests`. All tests must pass (SC-006). Record the count and duration.
- [ ] T039 Walk through the scenarios in `specs/003-single-run-command/quickstart.md` (1–5) in a scratchpad project with the fake Claude (`DEVLOOPS_CLAUDE_BIN=loops/shared/tests/fake_claude.py`). Record each result, and fix any difference.

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: none. T001 and T002 are independent.
- **Foundational (Phase 2)**: T003 → T004 → T005; T006 and T007 can run in parallel after T003/T004. This phase blocks all stories.
- **US1 (Phase 3)**: needs Phase 2.
  - **CLI tasks:** T013 → T014 → T015 → T016 → T020 run in sequence (same file; T020 also needs T019's `select_loops` use).
  - **Message and dashboard tasks:** T017, T018, and T021 are [P], in different files. T019 comes before T021.
  - **Test migration:** T008, T009, and T012 can run in parallel with each other. T010 comes before T011.
  - **Last:** T022.
- **US2 (Phase 4)**: needs US1's CLI (T013–T016). T026 and T027 are in different files and can run in parallel; their tests are T023–T025.
- **US3 (Phase 5)**: needs T014. It can run in parallel with US2.
- **US4 (Phase 6)**: needs US1's CLI shape (T013) only. It can run in parallel with US2 and US3.
- **Polish (Phase 7)**: after all stories. T034–T036 are [P]; then T037, T038, and T039.

### Story dependencies

- US1 is the MVP and the base for every other story.
- US2, US3, and US4 depend only on US1 and are independent of each other.

### Parallel opportunities

```text
Phase 1:  T001 ‖ T002
Phase 2:  T003 → T004 → T005, then T006 ‖ T007
US1:      T013→T014→T015→T016→T020  ‖  T017 ‖ T018 ‖ (T019→T021)  ‖  T008 ‖ T009 ‖ T012 ‖ (T010→T011)
After US1: US2 (T023 ‖ T024 ‖ T025, T026 ‖ T027) ‖ US3 (T028, T029) ‖ US4 (T030, T031, T032, T033)
Polish:   T034 ‖ T035 ‖ T036 → T037 → T038 → T039
```

---

## Implementation Strategy

### MVP first (User Story 1)

1. Phase 1 (constitution, schema wording).
2. Phase 2 (selection, run record).
3. Phase 3 (US1). **Stop and validate**: the full suite passes (T022), and quickstart scenarios 1–2
   work.

### Incremental delivery

1. US1 → one command, decisions without loops, the "run" naming.
2. US2 → backend-only projects (`init --no-frontend`, `check` with `unused`).
3. US3 → exit-30 setup errors (most of it lands with T014; T028 and T029 prove it).
4. US4 → skills.
5. Polish → docs in place, SC-005 grep, full suite, quickstart.

### Notes

- Commit on `main` only when the developer asks (Conventional Commits, no co-author trailer).
- Never let tests open the real editor: always set `VISUAL=true EDITOR=true`.
- Temporary files go in the session scratchpad.
