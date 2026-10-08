# Research: One Command to Run Devloops

Every decision below implements a requirement the developer confirmed (spec.md, Clarifications,
Session 2026-10-08). Where the spec left a detail open, the decision is marked **[open detail]** and
listed again in the plan's summary, so the developer can overrule it.

## R-1: Where the single command lives

**Decision**: `devloops run` runs through the existing sequencing code in
`loops/shared/devloops/orchestrator.py` (today's `orchestrate`). The engine is unchanged. The CLI
handler for `run <loop>` (`_loop_command`'s run branch) and the `orchestrate` subparser are
deleted. The module, the class, and its helpers keep their internal names (`orchestrator.py`,
`Orchestrator`, `render.render_orchestrator_progress`) **[open detail]**: every user-visible name changes (R-9), and renaming the module would only add churn.

**Rationale**: The orchestrator already does everything `devloops run` must do: ordering, handoff,
skipping completed loops, checking tools first, continuing after decisions. Making it the only path
removes code rather than adding it.

**Alternatives considered**: Keep per-loop `run` internally and add a new sequencer (two paths
again); rename the module to `runner.py` (rejected for churn; can be done separately).

## R-2: Choosing the loops (FR-005)

**Decision**: One function, `select_loops(project, ws, backend_target, frontend_target,
target_root)`, returns `{loop: target}` for the included loops, in `LOOP_ORDER`. For each loop, the
first that applies wins:

1. the workspace's recorded target. Once a target is recorded (today both are recorded when the
   run starts), the loop stays included. A flag naming a different folder is a usage error (exit
   2; spec FR-005a); the same folder is accepted;
2. the explicit flag (`--backend-target` / `--frontend-target`);
3. the project's `targets.<loop>`, when neither `null` nor missing; `--target-root DIR` then
   replaces it with `DIR/backend` or `DIR/frontend`.

A loop with none of these is not included. The orchestrator runs only the included loops; its
`_check_tools` checks only them.

**Rationale**: Matches the confirmed rules: a started loop keeps running, an explicit flag turns a
loop on, `--target-root` only places loops the project has, and the choice is made on every run so
a target added later is picked up.

**Alternatives considered**: Store the selection in `run/state.json` at the first run (rejected:
the developer chose "runs the new loop" over "frozen at first run").

## R-3: Checking the selection before anything is written (FR-006)

**Decision**: `devloops run` computes the selection before opening the workspace for writing. It
opens an existing workspace read-only for its recorded targets, and creates nothing when the
workspace does not exist. It then stops with `StopRun("stopped-on-input-error", ...)`, exit 30,
before the workspace is created, the lock is taken, or `run/state.json` is written:

| Selection | `status_reason.code` | Message (first line) |
|-----------|---------------------|----------------------|
| empty | `no-loop` | `no loop to run: set targets.backend-dev or targets.frontend-dev in .devloops/devloops.json (or run devloops init)` |
| frontend-dev only | `frontend-needs-backend` | `frontend-dev needs backend-dev in the same run: set targets.backend-dev in .devloops/devloops.json (frontend-only runs are not supported yet)` |

The code names are **[open detail]**. They follow the existing kebab-case `status_reason.code`
style.

`--json` prints exactly `{"exit_code": 30, "status_reason": {"code", "message"}}` (spec FR-006).

**Rationale**: The spec requires no run state. Checking before workspace creation also leaves no
empty workspace behind. `--json` prints `{exit_code, status_reason: {code, message}}`, the shape
errors already use.

## R-4: Decisions without a loop name (FR-009, FR-010)

**Decision**: `approve`, `replan`, and `retry` lose their positional `loop`. The CLI finds the
waiting loop by reading each loop's status (`engine.status_object`) in `LOOP_ORDER`:

- `approve` / `replan`: the loop in `awaiting-approval`;
- `retry`: the loop in `stopped-on-failure`.

When there is none, it raises a usage error (exit 2) **[open detail: wording]**: `nothing awaits
approval (run: <status>)` or `no loop is stopped on failure (run: <status>)`. The decision is then
passed to `Orchestrator.run(action=(loop, decide))` as today, so it always continues the whole run.
The single-loop decision path (`_loop_command` without an orchestrated workspace) is removed: every
workspace is a run.

`--no-continue` keeps today's behavior: the engine records the decision, and
`Orchestrator.sync_step` updates `run/state.json`.

**Rationale**: The loops run in sequence, so at most one loop waits. Reusing the action path keeps
"a refused decision changes nothing" (001 FR-056a) without new code.

## R-5: Backend-only runs and loops added later (FR-007)

**Decision**: `Orchestrator.run` iterates the selected loops instead of the fixed pair. After
backend-dev completes, the handoff is recorded whether or not frontend-dev is selected. When
frontend-dev is selected later, the next `devloops run` finds the backend step completed (skipped,
as today) and starts the frontend from the recorded handoff. A run whose `status` is `completed`
goes back to `running` when a newly selected loop has work left. `steps` lists only the loops
that have been selected at least once.

## R-6: `--max-trials` on `run` (FR-004)

**Decision**: `--max-trials N` becomes a `max_trials` entry in each loop's `cli_overrides` in
`Orchestrator._loop_options`, the mechanism `run <loop> --max-trials` used. A resumed loop records
it as a `config-override` event, as today. It is not stored in `run/state.json`, but each loop the
command starts or resumes keeps it in its frozen configuration (`run.json`), so later commands use
it too; a loop the command does not reach is not changed. This matches today's per-loop behavior
(revised 2026-10-09 after code review: the earlier "this command only" reading did not match how
command-line overrides are frozen).

## R-7: `init` without a backend or frontend (FR-013, FR-014)

**Decision**:
- **Flags:** `--no-backend` and `--no-frontend` are added. Each is mutually exclusive with its
  `--*-target` flag (argparse mutually exclusive group, exit 2).
- **Prompt:** at a target prompt, the answer `none` (case-insensitive, after trimming) means no
  target **[open detail]**. A folder literally named `none` is entered as `./none`.
- **Recorded value:** `targets.<loop>` is written as `null`.
- **Both none:** the terminal prompt says `a project needs at least one loop` and asks for the
  second target again. Flags that leave both none (`--no-backend --no-frontend`, or `--no-prompt`
  with the other answered `none`) are a usage error (exit 2) before anything is written.
- **Next step:** init's final line now names `devloops run`.

## R-8: `check` for the loops the project includes (FR-015)

**Decision**:
- **Which loops are checked:** `run_checks` computes the project's loops with R-2's rule for the
  project only (no workspace, no flags). Outside a project, both loops count.
- **Items only an unused loop needs:** an item whose `needed_for` lists only unused loops gets the
  new status `unused`, with detail `not used by this project (<loop>)` and no fix. `ready` ignores
  it.
- **JSON:** `--json` adds `"loops": [<included loops>]`. The text report prints `unused` in the
  status column.
- **Which items:** the existing `needed_for` values decide which items an unused loop drops
  (`playwright-mcp`, `browser`, and `display` for the frontend; `curl` for the backend).

## R-9: Renaming "orchestrator" to "run" (FR-016)

**Decision**:

| Where | Before | After |
|-------|--------|-------|
| Workspace folder | `<ws>/orchestrator/{state.json, progress.md}` | `<ws>/run/{state.json, progress.md}` |
| Text output | `orchestrator: <status>` | `run: <status>` |
| `--json` | `"orchestrator": {...}` | `"run": {...}` |
| Dashboard view and nav | "Orchestrator" (`orchestrator` view id) | "Run" (`run` view id) |
| Full dashboard file tree | `orchestrator/` group | `run/` group |
| Progress file title | "Orchestrator" | "Run" |
| Full-dashboard trigger | `orchestrate` | `run` |

`cli._orchestrated(ws)` is deleted: every workspace is a run.

**Old workspaces** (spec FR-016a): an `orchestrator/` folder is neither read nor deleted.
`devloops run` creates `run/state.json`. Completed loops are skipped by the existing rule, which
reads each loop's own `run.json`. A completed backend's handoff is recorded as usual. No
migration code is needed.

**Only included loops are shown** (spec FR-016b): `status` without a loop and the dashboards
(summary, served, and exported) list the loops the workspace's run includes. These come from
`select_loops(project, ws)` with no flags, the same rule as R-2, which every caller uses. A loop the project does not use is never shown as
"not started".

The decision `--json` object keeps `decision: {command, loop}`, so a caller still learns which loop
was decided.

## R-10: Messages that name a command (FR-011)

**Decision**: the commands named in messages drop the loop:
- `Engine.resume_command` defaults to `devloops run` (the orchestrator sets the same).
- Every `devloops approve {loop}`, `devloops replan {loop}`, and `devloops retry {loop} --milestone`
  string in `engine.py`, `render.py`, `dashboard.py`, and `cli.py` drops the loop, including the
  terminal review prompt and the dashboard's next-step hints.
- Messages that include `--workspace <name>` keep it.

## R-11: Frontend-loop and backend-loop tests (test strategy)

**Decision**: the engine keeps its per-loop API (`engine.Options.api_spec`, `target`), which the
orchestrator uses for the handoff. Tests change as follows:

- **Frontend-loop tests** (`test_frontend_loop.py`, part of `test_reusability.py`) can no longer
  start frontend-dev alone through the CLI. They drive `engine.Engine("frontend-dev", ...)` in a
  subprocess through a small test helper. The helper uses the same fake Claude, which keeps
  testing the frontend loop's own rules, such as the missing or invalid API spec cases.
- **Backend-focused tests** that ran `run backend-dev` use a project whose frontend target is
  `null` (the existing `samples` config already does), and call `devloops run`.
- **Orchestrator tests** call `devloops run`.

**Rationale**: The constitution amendment (R-12) keeps each loop runnable on its own once its
inputs exist. The engine is where that stays true and testable, while the CLI no longer exposes
it.

## R-12: Constitution amendment (FR-019)

**Decision**: amend Principle VI in `.specify/memory/constitution.md`, version 1.0.1 → **2.0.0**
(MAJOR: a MUST is redefined).

- **Replacement for the second bullet:**
  > Backend and frontend loops MUST remain separate loops, each runnable without the other once its
  > own inputs exist. devloops MAY offer one command that runs the loops a project chooses, in
  > order; running one loop MUST NOT require running another, except to produce inputs the first
  > one needs.
- **Sync Impact Report:**
  - motivation: one run command after a frontend run without the backend handoff failed;
  - affected: Principle VI;
  - migration impact: spec 001 FR-039 and FR-040, and spec 002's commands, are revised by spec
    003;
  - temporary deviation: frontend-only runs, until a follow-up feature.
- **Plan record:** the deviation is in this plan's Complexity Tracking.

## R-13: Skills (FR-017)

**Decision**:
- **Removed skill:** delete `loops/shared/skills/devloops-orchestrate/` from the kit. `init
  --upgrade` already removes a file dropped from the kit when it is unchanged, and reports a
  changed one (`initcmd`, "removed"), so no new upgrade code is needed. The repository's own
  `.claude/skills/` copy is refreshed with `bin/devloops init --upgrade`.
- **`devloops-run`:** runs `{{DEVLOOPS}} run $ARGUMENTS --json`.
- **Decision skills:** approve, replan and retry pass no loop name.
- **Tests:** `test_skills.py` / `test_repo_skills.py` expectations change to match.
