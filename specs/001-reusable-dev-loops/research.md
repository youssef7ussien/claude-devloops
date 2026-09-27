# Research: Reusable Development Loops

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**: 2026-09-27

Each decision is classified as follows:

- **[ER]** Explicit requirement: required by the task description or the approved spec (FR/D
  reference given).
- **[RD]** Repository-derived: inferred from the repository or the verified local environment.
- **[RC]** Recommendation: a design choice where other valid options exist. It can be changed
  without amending the spec.

Decisions U-1 to U-6 were open when the plan was first written. The spec review of 2026-09-27
settled all of them (spec items tagged [R]). They are kept at the end as a record, now classified
[ER].

## Environment facts verified on 2026-09-27 [RD]

- Claude Code `2.1.283` is installed.
- `claude -p --output-format json` returns one JSON object with these fields: `session_id`,
  `usage` (`input_tokens`, `output_tokens`, `cache_creation_input_tokens`,
  `cache_read_input_tokens`), `total_cost_usd`, `num_turns`, `duration_ms`, `is_error`, `subtype`,
  `permission_denials`, `result`, and `structured_output` (populated when `--json-schema` is used).
- These flags are available: `--session-id <uuid>`, `--json-schema`, `--settings <file|json>`,
  `--mcp-config`, `--strict-mcp-config`, `--allowedTools`, `--disallowedTools`,
  `--permission-mode {acceptEdits,auto,bypassPermissions,manual,dontAsk,plan}`, `--add-dir`,
  `--append-system-prompt`, `--max-budget-usd`, `--model`, and `--no-session-persistence`.
- The JSON result also carries `api_error_status` (null on success), which the driver uses to tell
  service failures apart from failures of the work itself (R-19).
- `--max-turns` is **not** listed in `claude --help` for this version.
- These tools are available: `python3` 3.14, `curl`, `jq`, `node`/`npx`, and `git`.
- The repository contains Spec Kit (`.specify/`, with bash scripts under `.specify/scripts/bash/`),
  Spec Kit skills under `.claude/skills/`, `specs/`, and `quickflow/PRD.md` (the reference
  application's PRD). It has no commits and no application code.

---

## R-1 How the loops run: a deterministic driver around headless Claude Code

- **Decision [RC]**: Each loop is a *driver* program. The driver owns everything that must be
  deterministic: state, choosing the next unit of work, trial counting, stop conditions, input
  fingerprints, rendering progress, and recording sessions and tokens. For each step that needs
  judgement or code changes (plan, implement, fix, author validation checks, UI validation), the
  driver calls Claude Code once in headless mode (`claude -p`).
- **Rationale**:
  - The spec needs hard bounds (FR-005/006, D-1), token and session records per milestone
    (FR-004, FR-033), and the rule "never mark achieved without validation" (FR-027). A driver
    guarantees these regardless of what the model does.
  - Headless JSON output gives the session ID, token usage, and cost for each call, which settles
    Q-8.
  - `--session-id` lets the driver assign the session ID *before* a call. The ID therefore survives
    a crash in the middle of a call.
- **Alternatives considered**:
  - (a) A single interactive session that self-paces with `/loop` or a Stop hook. Bounds and
    completion then depend on the model following instructions, and per-milestone token accounting
    is not available.
  - (b) Only a Claude Code skill or slash command, with no driver. Same weakness as (a).
  - (c) The Agent SDK. It adds a dependency, while the CLI already exposes everything needed
    (constitution VII, X).

## R-2 Driver language: Python 3 standard library only

- **Decision [RC]**: The driver is written in Python ≥ 3.10 using only the standard library
  (`json`, `hashlib`, `subprocess`, `argparse`, `uuid`, `pathlib`, `unittest`). It has no
  third-party dependencies.
- **Rationale**:
  - State and plans are structured JSON, and deterministic checks (DAG validation, JSON-path
    assertions, OpenAPI path matching) are far simpler and easier to test in Python than in
    bash + jq.
  - The standard library keeps dependencies at zero (constitution VII, X).
  - `unittest` makes the infrastructure testable independently of any application
    (constitution VIII).
- **Alternatives considered**:
  - bash + jq. This matches Spec Kit's scripts [RD], but complex state logic and assertions in jq
    are fragile and hard to unit test.
  - Node/TypeScript. Needs a package manager and a build step.
- **Note [RD]**: The repository's only existing scripts are bash (Spec Kit). The driver keeps a
  single entry point, `bin/devloops`, which behaves like those scripts (a CLI with `--json`
  output). This follows the repository's CLI style without adopting bash for complex logic.

## R-3 What counts as a unit of work, a trial, and a step

- **Decision [ER: FR-005, D-1; RC for granularity]**:
  - The unit that trials are counted against is the **milestone**. "Milestone" is the spec's
    canonical term; the task description calls it a phase (A-2).
  - One **trial** is one implementation step (or a *fix* step on trials 2 and later), followed by
    one full validation of the milestone.
  - The implementation step runs **one** Claude call per milestone. That call covers all tasks in
    the milestone that are not yet achieved.
- **Rationale**:
  - The task description measures time and tokens per milestone, and D-1 counts trials per
    milestone. A per-milestone call maps each trial to one implementation session, which makes
    accounting and the prompts/session-ID spreadsheet straightforward.
- **Alternatives considered**:
  - One call per task, with validation per milestone. This gives smaller contexts, but more
    sessions per trial and ambiguous trial accounting.
  - Allowing more than one milestone per call. This breaks per-milestone accounting.

## R-4 Interrupted trials

- **Decision [ER: FR-030a (was U-2); RC for the `in-progress` marker]**:
  - A trial is recorded as `in-progress` in state *before* its first Claude call.
  - If a run later finds a trial still `in-progress`, it marks that trial `interrupted`.
  - The interrupted trial **counts** toward the trial limit.
- **Rationale**: This keeps the bound absolute (constitution V). With a configurable limit (FR-006),
  a developer who expects interruptions can raise it.
- **Alternative**: Do not count interrupted trials. The bound would then be escapable by repeated
  crashes.

## R-5 Planning output: structured output, not files written by the model

- **Decision [RC]**: The planning step returns the plan through `--json-schema` structured output
  ([contracts/plan.schema.json](./contracts/plan.schema.json)). The driver checks the plan against
  the schema and against semantic rules, stores it in `state/plan.json`, and *renders* the milestone
  files in `outputs/` from it.
- **Rationale**:
  - FR-003/FR-034 require the milestone files, `progress.md`, and state to agree. A single source
    (state) plus generated Markdown views guarantees they agree.
  - The planning call needs no write access at all.
- **Semantic checks** done by the driver:
  - IDs are unique.
  - Milestone dependencies form a DAG.
  - Every milestone has at least one acceptance criterion.
  - Every task cites at least one requirement reference.
  - In single-story mode, every task cites the story ID (FR-010, D-6).
  - The stack source is one of the four allowed values (D-5).
- **Bound**: Planning is bounded by the same trial limit. An invalid plan counts as a failed
  planning trial.

## R-6 Approval pause and open questions (D-4)

- **Decision [ER: FR-053–056]**: After a valid plan is stored, the run status becomes
  `awaiting-approval` and the driver exits. `outputs/open-questions.md` lists the questions, each
  with an empty `Answer:` field.
- **Commands [RC]**:
  - `approve`: the developer accepts the plan as it is. Any answers typed into
    `open-questions.md` become part of the authoritative context for every later step.
  - `replan`: runs planning again with the answers, then pauses again. It uses up planning trials.
- **Recorded**: The approval (time, answers file fingerprint) is stored in state, so a restart goes
  straight to implementation (FR-054).
- **After approval**: Any new ambiguity is returned by the implement step in its structured result
  as `assumptions[]`. It is rendered into the milestone file and into the final report under
  "Assumptions for review" (FR-055).

## R-7 Stack selection (D-5)

- **Decision [ER: FR-057–060]**: The planning prompt tells Claude to apply the priority order and
  return a `stack` object with `source` ∈ {`existing-code`, `requirements`, `configuration`,
  `proposed`}, together with any conflict as an open question.
- **Driver enforcement [RC]**:
  - If `source = proposed`, the driver refuses to go past `awaiting-approval` without an explicit
    `approve`. This is true of every plan anyway.
  - The plan also declares **runtime commands** for the chosen stack (install, start, base URL,
    ready check, optional unit-test command, OpenAPI output path). The driver uses them for
    validation. This keeps the driver itself stack-agnostic (FR-059).
  - Commands and paths can be overridden in configuration.

## R-8 Backend validation: frozen curl checks executed by the driver

- **Decision [ER: FR-017/018; RC for mechanism]**: Backend validation for a milestone has these
  steps:
  1. **Author the checks.** This happens once per milestone, on its first trial. A separate
     Claude call with read-only tools (`Read`, `Grep`, `Glob`) turns the milestone's acceptance
     criteria, together with the current OpenAPI document, into a checks file
     ([contracts/checks.schema.json](./contracts/checks.schema.json)). Every acceptance criterion
     must be covered by at least one check.
  2. **Freeze the checks.** They are stored in `state/milestones/<id>/checks.json` and are not
     regenerated on later trials, so a fix step cannot weaken its own tests.
  3. **Run the checks.** The driver starts the backend (`runtime.start_command`), waits for the
     ready check, then runs each check with `curl` as a subprocess. It records the exact command
     line, status, headers, and body as evidence and evaluates the expectations
     (status, `body_contains`, JSON-path equality, and variable capture for chained requests).
  4. **Check OpenAPI consistency** (FR-019):
     - Every `(method, path)` exercised must exist in the OpenAPI document.
     - At every milestone validation, before the document is published, every operation in it
       must be exercised by a check of this milestone or of an earlier achieved milestone. The
       same check is repeated at loop completion. The published `outputs/openapi.json` therefore
       never lists an unverified endpoint.
  5. **Run unit tests** (optional, FR-008). This happens only if `unit_tests.enabled`, and the
     command's exit code must be 0.
- **Rationale**:
  - The evidence comes from real curl executions by the driver, not from the model's description
    of them (SC-002, FR-032).
  - Tests written by a separate, read-only call and then frozen guard against the implementer
    grading its own work.
- **Alternatives considered**:
  - Claude runs curl through its Bash tool and reports the results. The evidence cannot then be
    checked independently.
  - The checks are fixed at planning time. Exact paths are often not known before the API exists.

## R-9 Swagger/OpenAPI artifact

- **Decision [ER: FR-016; RC for format]**:
  - The backend writes an OpenAPI 3.x document **in JSON** at `runtime.openapi_path` in the
    target directory.
  - After each achieved milestone, the driver copies it to `backend-dev/outputs/openapi.json` and
    records its fingerprint. That copy is the contract that `frontend-dev` consumes.
  - JSON is chosen so the driver can parse it with the standard library.
- **Swagger UI [ER: FR-016, was U-1]**: A machine-readable OpenAPI 3 document is required. Serving
  an interactive Swagger page is optional; the plan step records whether the chosen stack serves one.

## R-10 Frontend validation: Playwright MCP in a restricted validation call

- **Decision [ER: FR-022/023, D-2; RC for mechanism]**: Frontend validation for a milestone has
  these steps:
  1. The driver starts the frontend (and the backend, if configured; see R-12), waits for
     `runtime.ready_url`, and records the **UI URL** as an output (D-2).
  2. A validation call runs with only Playwright MCP tools plus `Read` (no `Edit`, `Write`, or
     `Bash`). It gets `--mcp-config` pointing at a driver-generated Playwright MCP config with
     `--strict-mcp-config`, and screenshots go to the trial's evidence directory. It returns a
     structured result ([contracts/validation-result.schema.json](./contracts/validation-result.schema.json))
     with one entry per acceptance criterion: the steps taken, the observed result, pass or fail,
     and paths to the evidence.
  3. The driver checks the result:
     - Every criterion is present and passes.
     - Every cited evidence file exists.
     - The call used Playwright tools (at least one `mcp__playwright__*` tool call in the stream).
     - No disallowed tool was attempted.
  4. **API contract check** (FR-024): The validator also returns the backend requests the page made
     (from the Playwright network log). The driver checks that each one matches an operation in the
     supplied OpenAPI document.
  5. Optional unit tests run, as in R-8.
- **Rationale**: Playwright MCP runs *inside* Claude, so the evidence cannot be re-executed by the
  driver. Restricting tools to read-only plus the browser, requiring an entry for every criterion,
  and requiring evidence files is the strongest check available.
- **Evidence of tool use [RC]**: To prove Playwright was actually used, validation calls run with
  `--output-format stream-json`. The driver keeps the stream in the trial directory and counts
  tool-use events. It rebuilds the same summary fields (`session_id`, `usage`, `total_cost_usd`,
  `structured_output`) from the final `result` event.

## R-11 Write boundary and change safeguards (D-7)

- **Decision [ER: FR-035–035d; RC for mechanism]**: The boundary is enforced in three layers.
  1. **Tool restriction per step.** Each step type gets an explicit tool list
     ([contracts/claude-invocation.md](./contracts/claude-invocation.md)). Plan, author-checks, and
     validate steps have no write tools.
  2. **PreToolUse guard hook.** The driver writes a per-call `--settings` JSON that registers
     `loops/shared/hooks/guard_writes.py` for `Edit|Write|MultiEdit|NotebookEdit`. The hook
     resolves the target path and blocks it (exit code 2, with the reason) unless it lies inside
     the allowed roots passed in the environment. For implement and fix steps, the only allowed
     root is the target directory.
  3. **Post-call audit.** This catches writes made through `Bash`, which the hook cannot inspect
     reliably. Before and after each call the driver takes snapshots of:
     - a hash manifest of `loops/` (the reusable infrastructure) and of the workspace's `state/`;
     - `git status --porcelain` of every git repository that contains the target or the workspace.

     A change outside the allowed roots is a **boundary violation**. The trial is marked `failed`
     with reason `boundary-violation`, and the offending paths are listed. The driver does not
     revert anything automatically; it only reports.
- **Rationale**: No single mechanism covers every tool. Blocking catches most cases and the audit
  catches the rest, and every violation is recorded, never ignored.
- **Alternative**: A container or OS sandbox for each call. This is stronger, but it is heavy
  infrastructure (constitution X). It is listed as a future option only.

## R-12 How frontend-dev gets a running backend

- **Decision [ER: FR-039 (was U-3); RC for the config keys]**: `frontend-dev` configuration may include `backend.base_url` (an
  already-running backend) or `backend.start_command` + `backend.cwd` + `backend.ready_url` (the
  driver starts it for validation).
  - When the loop runs directly, the developer supplies these values.
  - Under the orchestrator, they are filled in from the backend loop's plan runtime.
  - If neither is given, the loop can still plan and implement, and validation runs without a live
    backend. Any criterion that needs a live backend then fails, which is expected; it never
    passes silently.

## R-13 Recording sessions, prompts, tokens, and time

- **Decision [ER: FR-004, FR-033; RC for format]**:
  - **Invocation records.** Every Claude call gets a UUID assigned by the driver (`--session-id`).
    Its composed prompt is saved to `state/prompts/<seq>-<step>.md`, and a record is appended to
    `state/invocations.jsonl` ([contracts/invocation-record.schema.json](./contracts/invocation-record.schema.json)).
    The record holds the session ID, step, milestone, trial, start and end timestamps, all four
    token counters, cost, duration, turns, `is_error`, `subtype`, and permission denials.
  - **Per-milestone figures in `progress.md`.** Start time is the start of the first trial. End
    time is the end of the last validation. Tokens and cost are summed over the milestone's calls.
    Any call without usage data is shown as `unavailable` (Edge Case).
  - **Export.** `devloops export-sessions` writes a CSV of prompts and session IDs, which Excel
    can open. The spreadsheet deliverable itself remains out of scope (A-5).

## R-14 `task.md` (resolves Q-7)

- **Decision [RC]**: `loops/<loop>/task.md` is the loop's **standing assignment**: its purpose,
  accepted inputs, and outputs, taken from the task description. It is a template. Each run renders
  a `task.md` into its workspace (`workspaces/<ws>/<loop>/task.md`) that states *this* run's
  assignment: input paths and fingerprints, story ID, target directory, and effective
  configuration.
- **Rationale**: FR-001 wants `task.md` per loop, and D-3 wants per-run artifacts in the workspace.
  The template-plus-rendered-copy split satisfies both without duplicating any logic.

## R-15 Orchestration order (resolves Q-6)

- **Decision [RC; FR-041–043 constrain it]**: The orchestrator runs the loops **sequentially**:
  `backend-dev` to `completed`, then `frontend-dev` with
  `--api-spec workspaces/<ws>/backend-dev/outputs/openapi.json` and the backend runtime settings.
  - It stops (and records why) when a loop is `awaiting-approval` or stopped.
  - Running it again resumes. Each loop resumes from its own state.
- **Rationale**:
  - The frontend depends on the final backend contract, so sequential order is the simplest order
    that meets FR-041/042 (constitution X).
  - Running a frontend milestone in parallel against a partial backend contract would conflict
    with D-8: any contract change after frontend planning would stop the frontend loop.
- **Alternative**: A dependency graph with parallel backend and frontend milestones. It was
  deferred because of the D-8 conflict and the added complexity.

## R-16 Where the loops interact with Claude Code (FR-044–046)

- **Decision [RD + RC]**: There are two entry points.
  - **CLI** (`bin/devloops`). This is the canonical way to run the loops, and it works from any
    shell.
  - **Optional thin skills** in `.claude/skills/` (`loops-backend-dev`, `loops-frontend-dev`,
    `loops-orchestrate`). Each one only runs the CLI through Bash and summarizes the status. This
    follows the repository's existing convention of Claude Code skills in `.claude/skills/` [RD],
    so a developer can start a loop "with one instruction to Claude Code" (SC-001).
  - The skills contain no loop logic, so nothing is duplicated (constitution VI).
- **Prompt composition [ER: FR-046]**: Each call's prompt is built from these parts, in order:
  1. the shared rules in `loops/shared/prompts/common.md`;
  2. the loop's `Loop-instructions.md` (the authoritative loop instructions);
  3. the step template in `loops/shared/prompts/steps/<step>.md`;
  4. a context block generated by the driver (inputs, milestone, tasks, prior evidence, answers,
     assumptions).

## R-17 Permission mode for headless steps

- **Decision [ER: FR-071 (was U-4) sets least privilege; RC for the specific modes]**:
  - Implement and fix steps use `--permission-mode acceptEdits` together with an `--allowedTools`
    list from configuration. The default list is `Read Edit Write Glob Grep Bash`.
  - Read-only steps keep the default permission mode, with a list that has no write tools, and
    they name `Edit`, `Write`, `MultiEdit`, `NotebookEdit`, and `Bash` in `--disallowedTools`.
    Plan mode is avoided because its exit-plan flow could interfere with structured output
    (not verified).
  - `bypassPermissions` is never used by default.
- **Rationale**: Headless calls cannot prompt the developer, so allowed tools must be listed
  explicitly. The guard hook and the audit (R-11) contain the risk that broad `Bash` access brings.

## R-18 Iteration safeguards beyond the trial limit

- **Decision [ER: FR-005/006, constitution V; RC for extra limits]**: Besides `max_trials`, these
  configurable limits apply:
  - `invocation_timeout_seconds`: the driver kills the call and the trial fails with reason
    `timeout`.
  - `max_budget_usd_per_invocation`: passed as `--max-budget-usd`.
  - `max_invocations_per_run`: a hard ceiling. Reaching it stops the run with outcome
    `stopped-on-failure` and reason `invocation-cap`.
  - A workspace **lock file** that prevents two drivers from running on the same workspace at once.
    A stale lock (its process ID is dead) is reported, and it can be cleared with `--force-unlock`.
- **Why these are needed**: `--max-turns` is not available [RD], so the timeout and the budget
  flag stand in for a per-call turn cap.
- **Classification now [ER]**: FR-061 (planning trials), FR-062 (time limit and call cap), and
  FR-065 (one active run per workspace). The lock mechanism and the specific values remain [RC].

## R-19 Service failures versus work failures (FR-067)

- **Decision [ER: FR-067; RC for the classification rule]**: After each call, the driver classifies
  a failed call as a **service failure** when any of these holds:
  - `api_error_status` is set to 401, 403, 429, or 5xx;
  - the process exits non-zero before producing a result, with an authentication or connection
    error on stderr (the matched patterns live in `claude.py` and are unit-tested);
  - the network is unreachable.

  A service failure marks the trial `void` (not counted), records the reason (`service-unavailable`,
  `rate-limited`, or `auth-failed`), and ends the run as `stopped-on-service-error`. Starting the
  loop again later resumes the same milestone with the same trial number.
- **Everything else** (a result with `is_error`, invalid structured output, or a timeout) is a
  **work failure**. It counts as a failed trial.
- **Rationale**: Outages must not use up trial budget (FR-067), but the rule must be deterministic
  so that a model error cannot be relabelled as an outage. Unknown errors default to work
  failures, which keeps execution bounded.

## R-20 Assumptions that would change scope (FR-055a)

- **Decision [ER: FR-055a; RC for the mechanism]**: The implement and fix result schema has a
  `needs_input[]` list (`{question, requirement_refs}`). The step prompt tells Claude to use it,
  and not `assumptions[]`, whenever proceeding would add, remove, or contradict a requirement.
- **Effect**: If `needs_input` is not empty, the driver fails the milestone immediately (reason
  `needs-input`, remaining trials not used), ends the run as `stopped-on-failure`, and writes the
  questions to `outputs/open-questions.md`.
- **Continuing**: The developer answers there and runs
  `retry --milestone <id> --reason "<text>"` (FR-063). The answers are fingerprinted like the
  approval answers (FR-051a).

## R-21 Secrets (FR-070)

- **Decision [ER: FR-070; RC for the mechanism]**: The configuration key `secrets.env` lists
  environment variable names, and `secrets.literals` lists literal values. Before writing any
  prompt, invocation record, stream log, curl response, or evidence file, the driver replaces every
  occurrence of those values with `***`. This lives in the shared `redact.py`.
- **Review before commit**: The README tells developers to review a workspace before committing it,
  and `status` lists any evidence files larger than 1 MB, since those are the likeliest place for a
  secret to hide.

## R-22 Input and tool checks (FR-013a, FR-013b)

- **Decision [ER; RC for the checks]**:
  - **API spec**: `--api-spec` must parse as JSON, have an `openapi` field that starts with `3.`,
    and have a `paths` object. Otherwise the run stops with `invalid-api-spec`.
  - **Tools**: `claude --version` must succeed. `curl --version` must succeed for backend-dev. The
    first element of `playwright.mcp_command` must be on `PATH` for frontend-dev. Otherwise the run
    stops with `missing-tool`, naming the tool.
- **When**: Both checks run before planning and again on every start, since tools can disappear
  between runs.

## R-23 Write-boundary exceptions (FR-035b)

- **Decision [ER: FR-035b; RC for the rule]**: The post-call audit (R-11) looks only at the loop
  repository and any git repository that contains a target or the workspace. So tool caches under
  the home directory (`~/.npm`, `~/.cache`, and similar) and system temporary directories are
  naturally outside its scope.
- **Caches inside an audited repository**: A cache directory that lies inside an audited repository
  but outside the target is still a violation, unless it is listed in `boundary.allowed_extra`
  (default: empty). Such an entry must be named explicitly and is recorded in the run's effective
  configuration.

---

## Decisions settled by the spec review (formerly unresolved)

| ID | Question | Decision | Now |
|----|----------|----------|-----|
| U-1 | Must the backend serve a Swagger UI, or is the OpenAPI document enough? | Document required; UI optional | [ER] FR-016 |
| U-2 | Do interrupted trials count toward the limit? | Yes, as failed with reason *interrupted* | [ER] FR-030a |
| U-3 | How does a direct `frontend-dev` run get a live backend? | The address of a running backend, or start instructions; without either, backend-dependent criteria fail | [ER] FR-039 (config keys [RC], R-12) |
| U-4 | What permission posture do headless steps get? | Least privilege; writes only in the target | [ER] FR-071 (modes [RC], R-17) |
| U-5 | How can work continue after `stopped-on-failure`? | An explicit, recorded trial-budget grant for one milestone | [ER] FR-063 (`retry` command [RC]) |
| U-6 | Do loops commit to git? | Not unless configured; off by default | [ER] A-6 (`git.commit_per_milestone` [RC]) |

No unresolved decisions remain.
