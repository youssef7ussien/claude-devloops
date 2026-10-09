# Feature Specification: One Command to Run Devloops

**Feature Branch**: `main` (no branch hook configured)

**Created**: 2026-10-08

**Status**: Draft

**Input**: User description: "003-single-run-command. Make `devloops run` (no loop name) the only
way to run devloops; it does what `devloops orchestrate` does today." The developer confirmed every
decision below in conversation before this spec was written.

## Scope and Source Classification

**Problem**: devloops has three ways to start work: `run backend-dev`, `run frontend-dev
--api-spec ...`, and `orchestrate`. A frontend run started on its own can skip the backend handoff.
It then has no backend to test against and spends every trial failing (seen on a real project:
milestone M02 exhausted its trials with "no backend is configured"). Developers also have to know
which of the three commands applies and which loop name each decision command needs.

**In scope**:
- one command, `devloops run`, that runs the loops the project has, in order, with the handoff;
- choosing the loops from the project's targets, including backend-only projects;
- checking that choice before anything runs;
- decision commands (`approve`, `replan`, `retry`) without a loop name;
- `init` support for a project without a backend or without a frontend;
- renaming "orchestrator" to "run" in everything a developer sees;
- skills, README, and the 001/002 contracts updated to match.

**Out of scope**:
- frontend-only runs against an API devloops did not build (a later feature; see FR-019);
- any change to how a loop plans, implements, validates, retries, or hands off;
- migrating existing workspaces or keeping the removed commands as aliases. devloops is in
  development; old workspaces and commands are not supported.

Every requirement is tagged with its source:

| Tag | Meaning |
|-----|---------|
| **[E]** | **Explicit**: a decision the developer confirmed for this feature |
| **[I]** | **Implied**: needed to satisfy an explicit requirement; the reason is given inline |
| **[K]** | **Kept**: an existing guarantee from 001 or 002 this feature must not weaken (item cited) |

## Clarifications

### Session 2026-10-08

- Q: Keep `orchestrate` and `run <loop>`? → A: Remove both. No aliases, no deprecation notes, no
  migration.
- Q: Removing `run frontend-dev --api-spec` drops frontend-only runs. OK? → A: Yes, for now. A
  later feature brings them back through the project configuration.
- Q: How does a project say it has no frontend (or no backend)? → A: `init` accepts `none` at the
  target prompt, and new flags `--no-frontend` / `--no-backend`. Both write `null` for that target.
- Q: Where is this specified? → A: A new spec, 003. The 001 and 002 contracts are edited in place to
  match, with a note pointing here.
- Q: Do `approve`, `replan`, `retry` keep a loop name? → A: No. devloops finds the waiting loop.
- Q: What does `devloops run --max-trials N` do? → A: It overrides `max_trials` for every loop the
  command runs.
- Q: What if `init` gets `none` for both targets? → A: It refuses; a project always has at least one
  loop.
- Q: Keep `--no-continue` on decisions? → A: Yes; the run continues on the next `devloops run`.
- Q: A target that is `null` or missing in `devloops.json`? → A: Both mean that loop does not run.
- Q: Keep the target flags on `run`? → A: Yes: `--target-root`, `--backend-target`,
  `--frontend-target`. No `--no-*` flags on `run`.
- Q: Rename "orchestrator" in output, JSON, and the workspace folder? → A: Yes, to "run".
- Q: The project sets the frontend to `null`, and the first run gets `--target-root`. Does the
  frontend run? → A: No. Only an explicit `--frontend-target` (or `--backend-target`) turns on a
  loop the project sets to `null`.
- Q: Keep the optional loop name on `status`? → A: Yes.
- Q: Skills `devloops-run` and `devloops-orchestrate`? → A: Keep `devloops-run` (it runs
  `devloops run`); delete `devloops-orchestrate`.
- Q: Constitution Principle VI says orchestration MUST NOT be a prerequisite for running either
  loop; without frontend-only runs, the frontend needs the backend in the same run. How is this
  handled? → A: Amend Principle VI (one run command; the project chooses its loops; each loop
  runnable without the other once its inputs exist) and record frontend-only as a temporary,
  documented deviation until the follow-up feature.
- Q: In a backend-only project, what does `devloops check` report for frontend tools? → A: Only the
  loops the project runs are checked; the frontend is reported as not used.
- Q: A workspace started backend-only; the project later gains a frontend target. Next `devloops
  run`? → A: It runs the new loop, from the recorded handoff. Loops are chosen on every `devloops
  run`; a loop that already started in a workspace keeps running there.

### Session 2026-10-09

Requirements-quality review (`checklists/run-command.md`):
- Q: On a later `devloops run`, a target flag names a different folder for a loop already recorded
  in the workspace. What happens? → A: Usage error (exit 2). Target flags only set a loop that is
  not yet recorded.
- Q: What does `devloops run` do in a workspace with an old `orchestrator/` folder? → A: It
  continues and ignores that folder: it creates `run/`, skips completed loops, and records the
  handoff. No migration code.
- Q: Apply the review's other recommendations? → A: Yes:
  - a loop counts as included once its target is recorded;
  - status and dashboards omit unused loops;
  - only living documents are updated;
  - wording fixes (CHK002, 003, 006, 009, 011–013, 017, 019, 021, 024, 027).

Code review of the US1 implementation:
- Q: Is `--max-trials N` kept after the command that passes it? → A: Yes. Each loop the command
  starts or resumes keeps it in its frozen configuration, like any command-line override (FR-004
  revised; it previously said "this command only").
- Q: Which loops does `check` check when the default workspace recorded a loop the project now sets
  to `null`? → A: The recorded loop too, as `devloops run` still runs it (FR-015 revised).
- Q: What does `check` report for a project with no loop? → A: A `missing` `loops` item (exit 30),
  as `devloops run` stops there (FR-015 revised).
- Q: Does `unused` also replace an item that is ready? → A: Yes, as in the contract's example.
- Q: What does the `frontend-needs-backend` message advise when the frontend came from
  `--frontend-target`? → A: Also `--backend-target` (FR-006 revised).

## User Scenarios & Testing *(mandatory)*

Every story has the same actor: a **developer** running devloops in an initialized project.

### User Story 1 - Run everything with one command (Priority: P1)

The developer types `devloops run`. devloops builds the backend, hands its API contract and start
command to the frontend, and builds the frontend. When a plan waits for approval or a milestone
fails, devloops stops and prints the one command that continues (`devloops approve`, `devloops
retry --milestone M02 --reason "..."`). That command records the decision and continues the whole
run to the end.

**Why this priority**: This is the feature. It removes the choice between three commands and makes
skipping the handoff impossible.

**Independent Test**: In a temporary project with both targets, using the offline test double for
Claude Code, run `devloops run`, approve each plan with `devloops approve`, and confirm both loops
complete with the frontend given the backend's contract and start command.

**Acceptance Scenarios**:

1. **Given** a project with both targets, **When** the developer runs `devloops run`, **Then**
   backend-dev runs first, and frontend-dev starts only after it completes, with the backend's API
   contract and how to start the backend.
2. **Given** a run paused for plan approval, **When** the developer runs `devloops approve`,
   **Then** the waiting loop's plan is approved and the run continues, through the frontend if
   needed, without naming a loop.
3. **Given** a run stopped because milestone M02 failed, **When** the developer runs `devloops
   retry --milestone M02 --reason "..."`, **Then** that loop gets more trials with the guidance, and
   the run continues.
4. **Given** a completed backend and a stopped frontend, **When** the developer runs `devloops run`
   again, **Then** the backend is not run again.
5. **Given** a decision recorded with `--no-continue`, **When** the developer later runs `devloops
   run`, **Then** the run continues from that decision.
6. **Given** the developer types `devloops orchestrate` or `devloops run backend-dev`, **Then**
   devloops reports a usage error and runs nothing.
7. **Given** any pause or stop, **When** devloops prints what to do next (text, JSON, dashboard, or
   the terminal review prompt), **Then** the commands it names carry no loop name, and the run is
   called "run" (`run: paused`, the `run` JSON key, `<workspace>/run/`).
8. **Given** a workspace created before this feature (it has an `orchestrator/` folder), **When**
   the developer runs `devloops run`, **Then** the old folder is ignored, `run/` is created,
   completed loops are skipped, and the run continues.

---

### User Story 2 - A project with only a backend (Priority: P1)

A developer building an API with no UI answers `none` for the frontend during `init` (or passes
`--no-frontend`). `devloops run` builds only the backend, and the run completes when the backend
does.

**Why this priority**: Without it, a single command would force every project to have a frontend.

**Independent Test**: Initialize a temporary project with `--no-frontend`, run `devloops run` with
the test double, and confirm only backend-dev runs and the run ends completed.

**Acceptance Scenarios**:

1. **Given** `init --no-frontend`, **Then** `devloops.json` records the frontend target as `null`.
2. **Given** a terminal `init`, **When** the developer answers `none` at the frontend prompt,
   **Then** the same is recorded.
3. **Given** a backend-only project, **When** `devloops run` completes the backend, **Then** the run
   is completed, the backend handoff is recorded, and no frontend work starts.
4. **Given** that completed workspace, **When** the project later gets a frontend target and the
   developer runs `devloops run`, **Then** the frontend runs from the recorded handoff.
5. **Given** a backend-only project, **When** the developer runs `devloops check`, **Then** the
   frontend's tools are not checked and the frontend is reported as not used by the project.

---

### User Story 3 - A wrong setup stops before anything runs (Priority: P1)

If the project has no loop to run, or only a frontend, `devloops run` says so and stops before any
Claude call, without leaving a stopped run behind. The developer fixes `devloops.json` and runs the
same command again.

**Why this priority**: This is the failure that motivated the feature: a frontend with no backend
spent trials it could never pass.

**Independent Test**: In a temporary project, set both targets to `null`, run `devloops run`, and
confirm exit code 30, the message, and that no workspace run state was written. Repeat with only
the frontend set.

**Acceptance Scenarios**:

1. **Given** both targets `null` or missing, **When** the developer runs `devloops run`, **Then** it
   exits with code 30, says there is no loop to run and how to set a target, and writes no run
   state.
2. **Given** only a frontend target, **When** the developer runs `devloops run`, **Then** it exits
   with code 30, says the frontend needs the backend in the same run (frontend-only runs are not
   supported yet), and writes no run state.
3. **Given** `init` with `none` (or `--no-*`) for both targets, **Then** init refuses: in a
   terminal it asks again; with flags it is a usage error and nothing is written.

---

### User Story 4 - Drive it from Claude Code (Priority: P2)

The developer asks Claude Code to run the loops or to approve a plan. The skills run the new
commands, without loop names.

**Why this priority**: Skills are a main entry point (002 User Story 4), but they follow the CLI.

**Independent Test**: Render the skills into a temporary project and confirm `devloops-run` runs
`devloops run`, the decision skills run their command without a loop name, and there is no
`devloops-orchestrate` skill.

**Acceptance Scenarios**:

1. **Given** an initialized project, **When** its skills are installed or upgraded, **Then**
   `devloops-orchestrate` is absent and `devloops-run` runs `devloops run`.
2. **Given** the approve, replan, and retry skills, **Then** none of them passes a loop name.

### Edge Cases

- **No loop is waiting** when the developer runs `approve`, `replan`, or `retry`: usage error
  (exit 2) that says what the run's status is; nothing changes.
- **`retry --milestone M05`** when the waiting loop has no failed M05: usage error, as today; the
  milestone is checked against the stopped loop only.
- **The project sets a loop to `null` after its target was recorded** in a workspace: the
  workspace keeps that loop, because its target is recorded there. For example, a completed backend
  still gives its handoff to a frontend added later.
- **A target flag that differs from the workspace's recorded target** on a later run: usage error
  (exit 2); nothing changes. The same value is accepted.
- **`--backend-target X --frontend-target Y`** in a project whose targets are both `null`: both
  loops run in that workspace. `--frontend-target` alone in a project without a backend: exit 30 as
  in User Story 3.
- **`--target-root DIR`** places only the loops the project has, at `DIR/backend` and
  `DIR/frontend`.
- **`--max-trials N` on a resumed run**: applied to each loop the command starts or resumes,
  recorded as a configuration override as today, and kept by that loop for later commands.
- **`--no-backend` together with `--backend-target`** (or the frontend pair) on `init`: usage
  error.
- **A workspace from before this feature** (an `orchestrator/` folder, or loops run separately):
  the old folder is ignored. `devloops run` creates `run/`, skips completed loops, and continues
  (FR-016a). No other migration is done.
- **Other stops**: `stopped-on-service-error` resumes with `devloops run`; `stopped-on-input-error`
  is final, as in 001. `retry` applies only to `stopped-on-failure`, and its 001 refusals (for
  example `planning-trials-exhausted`) are unchanged.

## Requirements *(mandatory)*

### Functional Requirements

#### The run command

- **FR-001** [E]: `devloops run` MUST take no loop name. It MUST start or resume the workspace's run
  and run, in order, each loop the run includes (FR-005): backend-dev first, then frontend-dev.
- **FR-002** [K — 001 FR-041, FR-042, FR-056]: Within a run, frontend-dev MUST start only after
  backend-dev completed, and MUST receive the backend's verified API contract and how to start the
  backend. A plan pause or a stopped loop MUST stop the run there.
- **FR-003** [K — 001 FR-056a, FR-056b]: A loop already completed in the workspace MUST NOT run
  again. Before anything runs, the tools of every loop with work left MUST be checked, as
  `orchestrate` did.
- **FR-004** [E]: `devloops run` MUST accept `--requirements` / `--speckit-feature`, `--story-id` /
  `--story-file`, `--target-root`, `--backend-target`, `--frontend-target`, `--review-plan` /
  `--accept-suggested`, `--max-trials N`, `--quiet` / `--verbose`, `--force-unlock`, and the common
  options (`--workspace`, `--config`, `--json`). `--max-trials N` MUST override `max_trials` for
  every loop the command starts or resumes. As with any command-line override, the value is
  recorded in each such loop's frozen configuration (a `config-override` event when the loop was
  already started), so later commands keep it; a loop the command does not reach is not changed.
  `--api-spec` and `--target` MUST NOT exist.
- **FR-005** [E]: The loops a run includes MUST be chosen on every `devloops run` and every
  decision command. A loop is included when any of these gives it a target, in this order:
  1. the workspace: its target is recorded there (once recorded, it stays included);
  2. an explicit `--backend-target` / `--frontend-target`;
  3. the project configuration: `targets.<loop>` that is neither `null` nor missing.

  `--target-root DIR` MUST replace the project's folder with `DIR/backend` or `DIR/frontend` only
  for loops the project configuration includes and the workspace has not recorded. It MUST NOT
  include a loop the project leaves out.
- **FR-005a** [E]: A target flag for a loop whose target is already recorded in the workspace MUST
  be accepted when it names the same folder. When it names a different folder, it MUST be a usage
  error (exit 2) that changes nothing.
- **FR-006** [E]: Before any Claude call, lock, or run state is written, `devloops run` MUST stop
  with exit code 30 when the chosen loops are:
  - none: the message MUST say there is no loop to run and name `targets.backend-dev` /
    `targets.frontend-dev` in `devloops.json` (or `devloops init`);
  - frontend-dev without backend-dev: the message MUST say the frontend needs the backend in the
    same run and that frontend-only runs are not supported yet. When the frontend came from
    `--frontend-target`, it MUST also name `--backend-target` as a fix.

  No workspace MUST be created. With `--json`, the output MUST be `{"exit_code": 30,
  "status_reason": {"code", "message"}}` with no `run` or `loops` key. The codes are `no-loop` and
  `frontend-needs-backend` (contracts/cli.md).
- **FR-007** [E]: A run that includes only backend-dev MUST be completed when backend-dev
  completes, and MUST still record the backend handoff, so a frontend added later (FR-005) starts
  from it.
- **FR-008** [E]: `devloops orchestrate` and `devloops run <loop>` MUST NOT exist: either is a
  usage error (exit 2) that runs nothing. No alias, deprecation notice, or migration is provided.

#### Decisions

- **FR-009** [E]: `approve`, `replan`, and `retry` MUST NOT take a loop name. Each MUST apply to the
  loop that waits: for `approve` and `replan`, the loop awaiting approval; for `retry`, the loop
  stopped on failure. When no loop is in that status, the command MUST be a usage error (exit 2)
  that states the run's status, and MUST change nothing. Decisions use the workspace's included
  loops (FR-005) and need no exit-30 check: a waiting loop exists only in a valid run. The 001
  refusals of `retry` (for example after `planning-trials-exhausted`) are unchanged.
- **FR-010** [K — 001 FR-056a]: After recording the decision, the command MUST continue the whole
  run (FR-001) unless `--no-continue` is given. With `--no-continue`, the decision is only recorded
  and the run continues on the next `devloops run`. A refused decision MUST change nothing. The
  one-run-per-workspace lock (exit 40) is unchanged [K — 001 FR-065].
- **FR-011** [I — FR-009]: Every message that tells the developer what to do next (pause and stop
  messages, the terminal review prompt, dashboard hints) MUST name the new commands without a loop
  name: `devloops run`, `devloops approve`, `devloops replan`, `devloops retry --milestone <id>`.
- **FR-012** [E]: `devloops status [loop]` MUST keep its optional loop name.

#### Initialization and readiness

- **FR-013** [E]: `devloops init` MUST accept `--no-backend` and `--no-frontend`, and MUST accept
  `none` as the answer to a target prompt. Each MUST write `null` for that target in
  `devloops.json`. `--no-backend` with `--backend-target` (or `--no-frontend` with
  `--frontend-target`) MUST be a usage error. `none` is matched case-insensitively after trimming
  spaces. A folder named `none` is entered as `./none`.
- **FR-014** [E]: `init` MUST refuse to leave both targets `null`: a terminal prompt MUST ask again;
  flags that set both to none MUST be a usage error, and nothing MUST be written.
- **FR-015** [E]: `devloops check` MUST check only the loops the project includes (FR-005, without
  flags, with the project's default workspace when it exists, so a loop recorded there stays
  checked). Each item needed only by loops the project does not include MUST get the status
  `unused`, with the detail `not used by this project (<loop>)`. An `unused` item MUST NOT make
  `ready` false or change the exit code. When the project includes no loop, a `loops` item MUST be
  `missing` (fix: set `targets.backend-dev` or `targets.frontend-dev`), so `check` fails like
  `devloops run` (exit 30). `--json` MUST list the included loops (`loops`).

#### Naming and records

- **FR-016** [E]: Everything user-visible MUST say "run" where it said "orchestrator": the status
  line (`run: paused`), the `--json` key (`run`), the workspace folder (`<workspace>/run/`, holding
  its state and progress files), dashboards, and progress files.
- **FR-016a** [E]: An `orchestrator/` folder left by an older devloops MUST be ignored, neither read
  nor deleted. `devloops run` in such a workspace MUST create `run/`, skip loops already completed,
  record the handoff from a completed backend, and continue.
- **FR-016b** [E]: `status` and the dashboards MUST show only the loops the run includes. A loop
  the project does not use MUST NOT be shown, not even as "not started".

#### Skills and documentation

- **FR-017** [E]: The `devloops-orchestrate` skill MUST be removed. `devloops-run` MUST run
  `devloops run`. The `devloops-approve`, `devloops-replan`, and `devloops-retry` skills MUST NOT
  pass a loop name. `init --upgrade` MUST remove an unchanged installed `devloops-orchestrate` skill
  and report a changed one, as it does for other removed files.
  *Revised after spec 005: the approve, replan, retry, and dashboard skills are removed; the run
  skill asks for those decisions and runs them (loops/README.md "Claude Code skills").*
- **FR-018** [E]: The living documents MUST be updated in place, each changed passage with a note
  pointing to this spec:
  - the README and the skills;
  - the 001 and 002 contracts on commands, skills, or the workspace and project layout;
  - the 001 and 002 requirements this feature replaces (listed under Dependencies).

  Historical records MUST stay as written: tasks.md, validation-results.md, research.md, plan.md,
  data-model.md, and earlier clarification sessions.

#### Constitution

- **FR-019** [E]: Constitution Principle VI MUST be amended: devloops has one run command; a project
  chooses which loops run; each loop MUST be runnable without the other once its own inputs exist.
  Until a follow-up feature lets frontend-dev take an API contract and backend from the project
  configuration, frontend-dev runs only after backend-dev in the same run. This MUST be recorded as
  a temporary, documented deviation. Its exit condition is feature 004 (frontend-only runs). The
  wording is in research R-12.

### Key Entities

- **Run**: one workspace's progress through its loops, formerly "orchestrator". It holds each
  included loop's status and times, the backend handoff, and the questions mode. Its files live in
  `<workspace>/run/`.
- **Loop selection**: the loops a run includes, computed on each `devloops run` from the workspace,
  the target flags, and the project configuration (FR-005).
- **Target**: the folder a loop writes code into. `null` or missing in `devloops.json` means the
  project does not use that loop.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A developer can take a two-loop project from `init` to both loops completed using
  only `devloops run` and decision commands that name no loop.
- **SC-002**: In 100% of runs started through devloops commands, the frontend starts only with the
  backend's contract and start instructions. No project or flag setup lets a frontend trial start
  without them.
- **SC-003**: In an existing project with no workspace yet, a setup with no loop to run, or with
  only a frontend, is reported in under 1 second with exit code 30. No Claude call, workspace, or
  run state results.
- **SC-004**: A backend-only project completes with `devloops run`, and `devloops check` passes on a
  machine without the frontend's browser tools.
- **SC-005**: The living documents (FR-018) mention no removed command (`orchestrate`, `run <loop>`,
  `--api-spec`) except in notes that say it was removed.
- **SC-006**: The full test suite passes.

## Assumptions

- devloops is in development, so breaking the CLI, JSON output, and workspace layout is acceptable
  without migration (confirmed by the developer).
- At most one loop waits for a decision at a time, because the loops run in sequence.
- Exit codes keep their meaning: 0 completed, 10 awaiting approval, 20 stopped on failure, 30 input
  error, 40 lock held, 50 service error, 2 usage error.
- The engine's per-loop behavior (planning, trials, validation, handoff contents) is unchanged.

## Dependencies

- **Spec 001** (`specs/001-reusable-dev-loops`) is revised in place. Replaced:
  - FR-039 and FR-040 (each loop runnable directly through the CLI);
  - the wording of FR-056a and FR-056b (`orchestrate`, decisions with a loop name);
  - User Story 5's direct-use scenario;
  - `contracts/cli.md` and `contracts/workspace-layout.md`.
- **Spec 002** (`specs/002-devloops-init`) is revised in place. Replaced:
  - the command names in FR-007 (next command), FR-019, FR-020, FR-023, and FR-039a;
  - FR-018: check statuses, which gain `unused`;
  - `contracts/cli.md`, `contracts/skills.md`, and `contracts/project-layout.md`.
- Constitution amendment (FR-019).
