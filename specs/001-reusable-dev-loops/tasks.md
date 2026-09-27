---

description: "Task list for implementing the reusable development loops (Goal #1)"
---

# Tasks: Reusable Development Loops

**Input**: Design documents from `specs/001-reusable-dev-loops/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Included. The constitution requires the loop infrastructure to be testable
independently of the applications it builds (constitution VIII), and
[quickstart.md §1](./quickstart.md) defines the offline scenarios. Tests use the stdlib `unittest`
module and a fake `claude` binary, so they need no model and no network.

**Scope**: Only the loop infrastructure. No task builds, plans, or references the QuickFlow
application (FR-037). A test (T066) asserts this.

**Organization**: Tasks are grouped by user story (US1–US6 in spec.md) so that each story can be
implemented and tested on its own.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: The user story this task belongs to (US1–US6)
- Paths are relative to the repository root. Layout: [contracts/workspace-layout.md](./contracts/workspace-layout.md)

## Conventions that apply to every task

- **Python**: Python ≥ 3.10, **stdlib only** (no third-party packages; research R-2).
- **Package**: `loops/shared/devloops/`. Tests live in `loops/shared/tests/test_*.py` and run
  with `python3 -m unittest discover -s loops/shared/tests -v`.
- **State writes**: Every write to `state/` uses `state.write_json_atomic`: write to a temp file in
  the same directory, `fsync`, then `os.replace`. Every write also happens **before** the action it
  records (plan.md, Iteration model).
- **Redaction**: Every text written to `state/`, to `evidence/`, or as a prompt first passes
  through `redact.redact(...)` (FR-070).
- **Contracts**: The formats are the JSON Schemas in `loops/shared/schemas/`, which are copies of
  `specs/001-reusable-dev-loops/contracts/*.schema.json`. Do not invent fields. If a field is
  missing, update both copies of the schema and `data-model.md`.
- **Terminology**: "milestone", not "phase" (spec A-2).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Repository skeleton, the entry point, and the test harness

- [X] T001 Create the directory skeleton: `bin/`, `loops/shared/devloops/validators/`, `loops/shared/hooks/`, `loops/shared/prompts/steps/`, `loops/shared/schemas/`, `loops/shared/config/`, `loops/shared/tests/fixtures/`, `loops/backend-dev/`, `loops/frontend-dev/`, `loops/orchestrator/`, `workspaces/`. Add `workspaces/.gitkeep`, and create empty `loops/shared/devloops/__init__.py` and `loops/shared/devloops/validators/__init__.py`.
- [X] T002 Create the executable entry point `bin/devloops`:
  - Use the shebang `#!/usr/bin/env python3`.
  - Exit with code 2 and a clear message if `sys.version_info < (3, 10)`.
  - Insert `<repo>/loops/shared` into `sys.path`, resolved from `__file__`, and call `devloops.cli.main(sys.argv[1:])`.
  - Run `chmod +x bin/devloops`.
  - Set `__version__ = "0.1.0"` in `loops/shared/devloops/__init__.py`.
- [X] T003 [P] Copy the six schemas from `specs/001-reusable-dev-loops/contracts/` into `loops/shared/schemas/`: `config`, `plan`, `checks`, `validation-result`, `invocation-record`, and `run-state` `.schema.json`. Add `loops/shared/tests/test_schemas_sync.py`, which asserts that each pair is byte-identical (constitution IX).
- [X] T004 [P] Create `loops/shared/config/defaults.json` with every default from `config.schema.json`: `max_trials: 3`, `max_invocations_per_run: 60`, `invocation_timeout_seconds: 1800`, `max_budget_usd_per_invocation: null`, `model: null`, `implement_tools: ["Read","Edit","Write","Glob","Grep","Bash"]`, `unit_tests: {enabled: false, command: null}`, `runtime: {ready_timeout_seconds: 120}`, `backend: {}`, `playwright: {mcp_command: ["npx","@playwright/mcp@latest","--headless"]}`, `git: {commit_per_milestone: false}`, `secrets: {env: [], literals: []}`, `boundary: {allowed_extra: []}`. It must contain **no** stack-specific commands (FR-059).
- [X] T005 [P] Create a root `.gitignore` that ignores `__pycache__/`, `*.pyc`, and `workspaces/*/*/state/lock`. Workspaces themselves are committed (spec A-4).
- [X] T006 [P] Create the test harness in `loops/shared/tests/helpers.py`:
  - `TempEnv`, a context manager that creates a temp repo root holding a copy or symlink of `loops/` and `bin/`, plus a temp target dir and a workspace dir.
  - `run_cli(args, env)`, which runs `bin/devloops` as a subprocess and returns `(exit_code, stdout, stderr)`.
  - `write_scenario(dict)`, which writes a fake-Claude scenario file and sets `DEVLOOPS_FAKE_SCENARIO`.
- [X] T007 [P] Create the fake Claude binary `loops/shared/tests/fake_claude.py` (executable). It must:
  - Accept the same flags as real `claude -p` and identify the step from the prompt's first line, `<!-- step: <name> -->`.
  - Read a scenario JSON from `$DEVLOOPS_FAKE_SCENARIO`. For each step, and optionally for each call number, the scenario gives: a `structured_output` object; file writes (`[{path, content}]`, which may use Bash-style writes outside `cwd` to exercise the audit); `api_error_status`; `is_error`; `sleep_seconds`; an exit code; and `tool_uses` (a list of tool names emitted as stream-json `tool_use` events).
  - Print the same JSON shape that real Claude Code 2.1.283 prints (research, Environment facts): `session_id` (taken from `--session-id`), `usage` with the four token counters, `total_cost_usd`, `num_turns`, `duration_ms`, `is_error`, `subtype`, `api_error_status`, `permission_denials`, `result`, and `structured_output`.
  - With `--output-format stream-json`, emit JSONL events ending in a `{"type":"result",...}` event.
  - Record each call's argv to `$DEVLOOPS_FAKE_LOG` (JSONL), so tests can assert flags and prompts.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared driver that every loop uses (FR-038). No user story can start before this
phase is done.

- [ ] T008 [P] Implement a stdlib JSON-Schema subset validator in `loops/shared/devloops/schema.py`.
  - Support `type` (including type lists and `null`), `enum`, `const`, `required`, `properties`, `additionalProperties` (bool or schema), `items`, `minItems`, `minLength`, `pattern`, `minimum`, and local `$ref` to a sibling schema file.
  - Provide `validate(instance, schema_name) -> list[str]`, which returns error paths.
  - Add tests in `loops/shared/tests/test_schema.py`, covering each schema file in `loops/shared/schemas/` against one valid and one invalid sample.
- [ ] T009 [P] Implement `loops/shared/devloops/state.py`:
  - `write_json_atomic(path, obj)`, `read_json(path, default=None)`, `append_jsonl(path, obj)` (open with append, write one line, `flush` + `fsync`), and `now_iso()` (UTC, ISO-8601, `Z`).
  - `record_event(loop_dir, type, message, milestone=None, trial=None)`, which writes to `state/events.jsonl`. The event types come from data-model.md, "Event".
  - Add tests in `loops/shared/tests/test_state.py`, including one showing that a crash between the temp write and the replace leaves the old file intact.
- [ ] T010 [P] Implement `loops/shared/devloops/redact.py` (FR-070, research R-21):
  - `Redactor(config)` builds its value list from `os.environ[name]` for each name in `secrets.env` (skipping unset or empty values) plus `secrets.literals`.
  - `redact(text) -> (text, changed)` replaces every value with `***`, longest first. `redact_obj(obj)` does the same recursively for JSON.
  - Add tests in `loops/shared/tests/test_redact.py`.
- [ ] T011 Implement `loops/shared/devloops/config.py`. It depends on T008.
  - `load_effective(defaults_path, workspace_config_path|None, cli_overrides: dict) -> dict` does a deep merge in the order defaults < workspace `config.json` < CLI, then validates with `schema.validate(..., "config.schema.json")`. Invalid config exits with code 2 and lists the errors.
  - The effective config is frozen into `run.json` `effective_config` on the first run. Later CLI overrides are applied and recorded as an event `config-override`.
  - Add tests in `loops/shared/tests/test_config.py`.
- [ ] T012 Implement `loops/shared/devloops/workspace.py` (FR-035a–d, FR-049–051, FR-065). It depends on T009.
  - `open_workspace(name_or_path, repo_root)` resolves a bare name to `workspaces/<name>/` and creates `workspace.json` on the first run with `{name, created_at, requirements: {path, sha256, mode, story_id}, targets: {"backend-dev": path, "frontend-dev": path}, config_path}`. The name must match `^[a-z0-9-]+$`.
  - `set_target(loop, path)` requires an absolute path that exists or can be created and is writable, is **not inside `loops/` or `bin/`**, and is not equal to or inside the other loop's target. Violations give `stopped-on-input-error` with code `target-unwritable`. Attaching with a different target for the same loop gives `workspace-mismatch`.
  - `acquire_lock(loop_dir)` writes `state/lock` as `{pid, host, started_at}`. If the lock is held by a live process, exit 40 and name that pid and start time. If the pid is dead, report "stale lock" and exit 40 unless `--force-unlock` is given, which records an event.
  - `release_lock()` removes the lock and is called in a `finally` block.
  - Add tests in `loops/shared/tests/test_workspace.py`.
- [ ] T013 Implement `loops/shared/devloops/inputs.py` for the PRD mode (FR-009, FR-012, FR-013, FR-051a).
  - `check_requirements(path)` gives `missing-input` if the file is missing, unreadable, or empty or whitespace-only. `sha256_file(path)` hashes at byte level.
  - `compare_fingerprints(run_state, current)` gives `stopped-on-input-error` with code `input-changed` and `input` set to one of `requirements`, `api-spec`, or `answers`, and changes **no** code or state other than `status` and `status_reason`.
  - Story modes are added in T060. Add tests in `loops/shared/tests/test_inputs.py`.
- [ ] T014 [P] Implement `loops/shared/devloops/preflight.py` (FR-013b, research R-22).
  - `check_tools(loop_def, config)`: run `claude --version` (or `$DEVLOOPS_CLAUDE_BIN --version`). For each name in `loop.json` `required_tools`, check `curl --version` for `"curl"`, and check that `shutil.which(config.playwright.mcp_command[0])` exists for `"playwright-mcp"`.
  - Return a `missing-tool` result that names the tool. It runs before planning and again on every start.
  - Add tests in `loops/shared/tests/test_preflight.py`, using a manipulated `PATH`.
- [ ] T015 [P] Implement `loops/shared/devloops/openapi.py` (FR-013a, FR-019, FR-024).
  - `load_spec(path)` requires valid JSON with `openapi` starting with `"3."` and a `paths` object; otherwise it gives `invalid-api-spec`.
  - `operations(spec)` returns a set of `(METHOD, path_template)` pairs.
  - `match(spec, method, url_or_path, base_url=None)` strips the base URL and query, then matches template segments where `{param}` matches any single segment.
  - Add tests in `loops/shared/tests/test_openapi.py`.
- [ ] T016 Implement plan validation in `loops/shared/devloops/plan.py` (research R-5). It depends on T008.
  - `validate_plan(plan, loop_def, mode, story_id) -> list[str]` validates against `plan.schema.json`, which already enforces ID patterns: milestone `^M[0-9]{2}$`, task `^M[0-9]{2}-T[0-9]{2}$`, criterion `^M[0-9]{2}-AC[0-9]+$`, question `^OQ[0-9]+$`. It then applies these semantic rules:
    - all IDs are unique;
    - `depends_on` references existing milestones, forms a DAG, and the list order is a valid topological order;
    - each milestone has ≥ 1 task and ≥ 1 acceptance criterion;
    - every task and criterion `requirement_refs` entry appears in `requirements_inventory[].ref` (FR-066);
    - a non-empty `stack.conflicts` requires ≥ 1 open question (FR-060);
    - `runtime.openapi_path` is present when `loop.json` has `"requires_openapi_path": true`.
  - Story-scope rules are added in T061. Add tests in `loops/shared/tests/test_plan.py`.
- [ ] T017 Implement the headless call wrapper in `loops/shared/devloops/claude.py` ([contracts/claude-invocation.md](./contracts/claude-invocation.md)). It depends on T009 and T010.
  - **Prompt composition**: first line `<!-- step: <step> -->`, then `loops/shared/prompts/common.md`, then `loops/<loop>/Loop-instructions.md`, then `loops/shared/prompts/steps/<step>.md`, then a `## Context` JSON block from the engine. Save the redacted prompt to `state/prompts/<seq:04d>-<step>.md`.
  - **argv per step**, from the Steps table: `-p <prompt> --session-id <uuid4> --output-format json|stream-json --json-schema <schema json> --allowedTools ... --disallowedTools ... [--permission-mode acceptEdits] --settings <per-call settings file> --strict-mcp-config [--mcp-config <file>] [--model] [--max-budget-usd]`.
    - Read-only steps (`plan`, `replan`, `author-checks`, `validate-ui`) disallow `Edit Write MultiEdit NotebookEdit Bash`.
    - The settings file registers a PreToolUse hook: `{"hooks":{"PreToolUse":[{"matcher":"Edit|Write|MultiEdit|NotebookEdit","hooks":[{"type":"command","command":"python3 <abs>/loops/shared/hooks/guard_writes.py"}]}]}}`. `DEVLOOPS_ALLOWED_ROOTS` is set to the target dir for implement and fix steps, and to the empty string for the others.
    - The binary is `$DEVLOOPS_CLAUDE_BIN`, defaulting to `claude`.
    - `cwd` is the target dir. The process starts in a new process group.
  - **Timeout**: `invocation_timeout_seconds` kills the group and sets `timed_out: true`.
  - **Parsing**: parse the JSON output, or for stream-json the final `result` event, and count `tool_use` events by name.
  - **Classification** (research R-19): `failure_class = "service"` if `api_error_status` is 401, 403, 429, or 500–599, or if the process exited non-zero with no result and stderr matches authentication or connection patterns (keep the patterns in a module constant). `"work"` for any other failure. `"none"` on success.
  - **Records**: append a redacted invocation record matching `invocation-record.schema.json`, where tokens map `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, and `cache_read_input_tokens`, each `null` if missing. Increment `run.json` `invocation_count` **before** the call.
  - Add tests in `loops/shared/tests/test_claude.py`, using fake_claude and asserting on argv for each step.
- [ ] T018 [P] Implement the PreToolUse write guard `loops/shared/hooks/guard_writes.py` (FR-035b, FR-071, research R-11).
  - Read the hook JSON from stdin. Take the path from `tool_input.file_path` or `tool_input.notebook_path`, resolve it with `os.path.realpath` relative to `cwd`, and allow it (exit 0) only if it lies under one of the roots in `DEVLOOPS_ALLOWED_ROOTS` (separated by `os.pathsep`). Otherwise print a reason to stderr and exit 2.
  - Before finalizing, check the stdin field names against the Claude Code hooks documentation for version 2.1.283.
  - Add tests in `loops/shared/tests/test_guard_writes.py`.
- [ ] T019 [P] Implement `loops/shared/devloops/boundary.py` (FR-035b, research R-11/R-23).
  - `snapshot(repo_root, workspace_loop_dir, targets)` records a sha256 manifest of `loops/`, `bin/`, and the loop's `state/` directory, plus `git status --porcelain -z` for every git repo that contains a target or the workspace. Discover repos with `git -C <dir> rev-parse --show-toplevel`; if git is absent, skip the git part and record `git-unavailable`.
  - `diff(before, after, allowed_roots, allowed_extra) -> violations[]` lists every changed path outside the allowed roots and outside `boundary.allowed_extra`. Tool caches outside the audited repos are out of scope.
  - It never reverts anything; it only reports.
  - Add tests in `loops/shared/tests/test_boundary.py`.
- [ ] T020 [P] Implement `loops/shared/devloops/runtime.py`.
  - `start(command, cwd, env, log_path)` uses `subprocess.Popen(shell=True, start_new_session=True)`.
  - `wait_ready(ready_url, timeout)` polls with `urllib.request` until it gets a status below 500, or fails with `runtime-start-failed`.
  - `stop(proc)` sends SIGTERM to the group, waits 10 s, then sends SIGKILL.
  - Use it as a context manager so the process is always stopped.
  - Add tests in `loops/shared/tests/test_runtime.py`, using `python3 -m http.server` as the runtime.
- [ ] T021 [P] Implement the shared unit-test runner `loops/shared/devloops/validators/unit_tests.py` (FR-008).
  - `run(config, plan_runtime, target_dir, trial_dir)` does nothing unless `unit_tests.enabled`. The command is `config.unit_tests.command`, falling back to `plan.runtime.unit_test_command`. If it is enabled with no command, the result is failed with the reason "no unit test command".
  - It records `{enabled, command, exit_code, log_path}`. A non-zero exit fails validation.
  - Add tests in `loops/shared/tests/test_unit_tests_runner.py`.
- [ ] T022 Implement Markdown rendering in `loops/shared/devloops/render.py` (FR-002–004b, FR-034). It depends on T009. Every view is regenerated from state and never read back.
  - `outputs/milestone-<NN>-<slug>.md`: title, goal, dependencies, task checkboxes (`[x]` only for `achieved`), acceptance criteria, a table of trials (n, status, reason, start, end), and assumptions.
  - `progress.md`:
    - action items rendered from `events.jsonl`;
    - a milestone table with start (the first trial's start), end (the last validation's end), input, output, cache-creation, and cache-read tokens, cost, and session IDs, where any `null` sum is shown as `unavailable`;
    - a per-trial timing table;
    - when the run is stopped, a **Stop** section showing the status, reason code and message, the milestone, and the trials used out of the limit, with links to the last trial's `validation.json` and `evidence/` directory (FR-007, US3 AC1).
  - `outputs/plan-summary.md` (FR-058): the chosen stack summary, its `source` (`existing-code`, `requirements`, `configuration`, or `proposed`), any `conflicts`, the declared `runtime` commands, and the milestone list with dependencies. It is rendered as soon as a plan is stored, so it is there for review at the approval pause.
  - The workspace `task.md` is rendered from the `loops/<loop>/task.md` template by replacing `{{requirements_path}}`, `{{requirements_sha256}}`, `{{mode}}`, `{{story_id}}`, `{{target_dir}}`, `{{api_spec_path}}`, and `{{effective_config}}`.
  - `outputs/open-questions.md` lists every question as `### OQ<n>`, with its context and an empty `**Answer:**` line.
  - `outputs/final-report.md`: outcome, milestones, validation summary, and "Assumptions for review" (FR-055).
  - Add golden-file tests in `loops/shared/tests/test_render.py`.
- [ ] T023 Implement next-unit selection in `loops/shared/devloops/selector.py` (FR-026, plan Iteration model step 4). It depends on T009.
  - `next_unit(run_state, plan) -> ("complete" | ("stop", code) | ("trial", milestone_id, n))` takes the first milestone in the stored order whose status is not `achieved`.
  - A milestone with status `failed` gives `stop trials-exhausted`.
  - `n` = the number of **counted** trials + 1, where trials with status `void` are not counted.
  - `n > max_trials + sum(grants.extra_trials for that milestone)` gives: mark the milestone `failed`, then `stop trials-exhausted`.
  - `invocation_count >= max_invocations_per_run` gives `stop invocation-cap`.
  - Add tests in `loops/shared/tests/test_selector.py`.
- [ ] T024 Write the shared prompts:
  - `loops/shared/prompts/common.md` (every step): work only on the given milestone; change only what its tasks need; no unrelated refactoring (FR-035); keep existing conventions (FR-036); never edit the requirements; report ambiguity as `assumptions[]`; route anything that would add, remove, or contradict a requirement to `needs_input[]` (FR-055a); cite requirement references (FR-066); never write outside the target.
  - `loops/shared/prompts/steps/plan.md` and `replan.md`: return a plan per `plan.schema.json`; apply the stack priority order of existing code, then the requirements or configuration, then a proposal (FR-057/058); observable acceptance criteria (FR-018/023); open questions; declared runtime commands.
  - `loops/shared/prompts/steps/implement.md` and `fix.md`: the result schema from claude-invocation.md, with `tasks`, `assumptions`, `needs_input`, and `files_changed`. `fix` explains how to use the previous failure summary and evidence paths from the context.
  - These prompts must contain no application- or stack-specific content.
- [ ] T025 Implement the loop engine `loops/shared/devloops/engine.py` (plan, Iteration model steps 1–10). It depends on T011–T023.
  - **Interface**: `Engine(loop_name, workspace, config).run() -> exit_code`, taking a validator adapter with `validate(ctx) -> dict` that matches `validation-result.schema.json`. Load the adapter by name from `loops/<loop>/loop.json` `validator`.
  - **Steps 1–2**, in this exact order: (1) lock; (2) preflight; (3) the terminal-state short-circuit, where a terminal run (`completed`, or `stopped-on-failure`/`stopped-on-input-error` with no new grant) makes no calls, changes nothing, reports its status, and exits with its code, so `completed` exits 0 (FR-029, FR-063); (4) only then the fingerprint checks. A terminal run is never moved to `stopped-on-input-error`. With no plan: `plan` trial → `validate_plan`. An invalid plan counts as a planning trial (FR-061), and running out of planning trials gives `stopped-on-failure` / `planning-trials-exhausted`. A valid plan is stored in `state/plan.json`, milestones are initialized to `pending` and tasks to `pending`, the views are rendered, and the status becomes `awaiting-approval` (exit 10).
  - **Steps 3–10**:
    - Write the trial as `in-progress` (`state/milestones/<id>/trials/<n>/trial.json`), then take the boundary snapshot.
    - Call `implement` (n = 1) or `fix`, listing only tasks that are not achieved. Then run the boundary diff; any violation fails the trial with `boundary-violation`. Set the task statuses to `implemented`.
    - `adapter.validate`.
    - Compute `passed` **only** with the data-model pass rule: all criteria pass, and a missing criterion counts as failed (FR-068); contract passes; boundary passes; unit tests pass if enabled (FR-008). Never use the model's claim (FR-027, FR-069).
    - On pass, the milestone and its tasks become `achieved`. On fail, record the reason and summary.
    - Loop via the selector. When the loop completes, call the adapter's `on_complete(ctx)` hook, write `final-report.md`, and set `completed` (exit 0).
    - Exit codes follow [contracts/cli.md](./contracts/cli.md).
  - Leave interrupted detection, the service-error path, `needs_input`, and grants to US3 (T052–T056), but keep the hook points.
- [ ] T026 Implement the CLI `loops/shared/devloops/cli.py`, using `argparse` and following [contracts/cli.md](./contracts/cli.md). It depends on T025.
  - Commands: `run <backend-dev|frontend-dev>` (with `--workspace`, `--requirements`, `--target`, `--api-spec`, `--max-trials`, `--config`, `--force-unlock`, `--json`), `approve <loop>` (allowed only in `awaiting-approval`; records `approval` = `{approved_at, action: "approve", answers_path, answers_sha256}`), `replan <loop>` (runs a `replan` planning trial with the answers and pauses again), and `status [<loop>]`, which is read-only and prints the status, the next milestone, the trials used out of the limit, the last failure, `ui_url`, and `openapi_artifact`.
  - `--json` prints one status object. Usage errors exit 2.
  - `retry`, `orchestrate`, and `export-sessions` are added in T056, T065, and T072.
- [ ] T027 Add engine core tests in `loops/shared/tests/test_engine_core.py`, using fake_claude and a stub validator adapter registered by a test `loop.json` under a temp `loops/` copy. Cover:
  - plan → exit 10, with milestone files and `open-questions.md` rendered;
  - `approve`, then `run` → the trial passes → `completed` (exit 0), with tasks `[x]` in the milestone file and `progress.md` token columns filled;
  - a second `run` → no fake-claude calls (FR-029);
  - an invalid plan counted as a planning trial;
  - a stub that fails every time plus a model claim of success → never `achieved`;
  - a boundary violation through a Bash-style write outside the target → the trial fails with `boundary-violation`;
  - a missing requirements file → exit 30.

**Checkpoint**: The shared engine runs end to end with a stub validator. User stories can now start.

---

## Phase 3: User Story 1 - Build a backend from requirements (Priority: P1) 🎯 MVP

**Goal**: `backend-dev` plans milestones, implements them, validates each one with curl checks the
driver runs itself, and publishes a verified OpenAPI document (FR-014–019).

**Independent Test**: Run only `backend-dev` with fake Claude against a small requirements file. The
milestone files, `outputs/openapi.json`, and `validation.json` with curl commands and responses
exist for every milestone, and the tasks are `[x]`.

### Tests for User Story 1

- [ ] T028 [P] [US1] Create a local fixture API server `loops/shared/tests/fixtures/http_app.py`: a stdlib `http.server` on a port given by argv, with a small in-memory JSON resource (`GET/POST /items`, `GET /items/{id}`) and `GET /health`. It is a test fixture only, not an application of the loops. Add a matching fixture `loops/shared/tests/fixtures/http_app.openapi.json` in OpenAPI 3.0.
- [ ] T029 [P] [US1] Write `loops/shared/tests/test_validator_curl.py` against the fixture server. Cover: status, `body_contains`, and dotted-path `json_equals`; `capture` with `${var}` substitution in a later check's path and body; evidence files (command line, headers, body) under `trials/<n>/evidence/`; a failing expectation → `passed: false` with failure text; a check on an operation missing from the OpenAPI file → `contract.passed: false`; checks frozen after trial 1, so author-checks is not called on trial 2.
- [ ] T030 [P] [US1] Write `loops/shared/tests/test_backend_loop.py`, a full `backend-dev` flow with fake Claude. The plan has two milestones. `implement` writes `openapi.json` into the target and uses `runtime.start_command = "python3 <abs>/fixtures/http_app.py 8765"`. Cover:
  - `outputs/openapi.json` is copied only after a milestone is achieved (FR-019);
  - an OpenAPI document with an operation not exercised by this milestone's or an earlier achieved milestone's checks → that milestone's validation fails with `validation-failed` naming the operation, the milestone is not achieved, and `outputs/openapi.json` is not updated (FR-019);
  - a missing `runtime.openapi_path` in the plan is rejected;
  - the `curl` tool is missing → exit 30 `missing-tool`.

### Implementation for User Story 1

- [ ] T031 [US1] Create `loops/backend-dev/loop.json`: `{"name": "backend-dev", "required_inputs": ["requirements"], "required_tools": ["claude", "curl"], "validator": "curl", "requires_openapi_path": true, "artifacts": ["openapi"]}`.
- [ ] T032 [P] [US1] Write `loops/backend-dev/Loop-instructions.md`, the authoritative backend instructions (FR-046):
  - Role: a backend developer working only in the target.
  - Plan milestones API-first, with dependency order and observable acceptance criteria phrased as HTTP behaviors (method, path, expected status and content; FR-018).
  - Declare `runtime` (install, start, `cwd`, `base_url`, `ready_url`, optional `unit_test_command`, and `openapi_path`).
  - Maintain an OpenAPI 3 JSON document at `runtime.openapi_path` listing only implemented endpoints (FR-016/019).
  - A Swagger UI is optional.
  - Apply the stack priority order (FR-057).
  - No application-specific content and no default stack (FR-037, FR-059).
- [ ] T033 [P] [US1] Write `loops/backend-dev/task.md`, the standing-assignment template (research R-14). It has the loop's purpose, inputs, and outputs taken from the task description, and the placeholders listed in T022.
- [ ] T034 [P] [US1] Write `loops/shared/prompts/steps/author-checks.md`. It turns the milestone's acceptance criteria and the current OpenAPI document into a checks file per `checks.schema.json`, where every criterion ID appears in at least one check's `criteria`. It must be read-only, and it must derive checks from the criteria, never from the implementation's claims.
- [ ] T035 [US1] Implement `loops/shared/devloops/validators/curl.py` (research R-8):
  - On the first trial only, call `author-checks` and validate the result against `checks.schema.json` plus the coverage rule (a missing criterion → `invalid-output`), then freeze it to `state/milestones/<id>/checks.json`. On later trials, load the frozen file (FR-069).
  - Start the runtime through `runtime.py` using the plan runtime merged with the config `runtime` overrides.
  - For each check, in order, substitute `${var}`, then run `curl -sS -X <METHOD> <base_url><path> -H ... --data-binary @<body file> -D <headers file> -o <body file> -w '%{http_code}'` as a subprocess. Evaluate `status`, `body_contains`, and `json_equals`, and apply `capture`. Save the redacted command line and files to `evidence/`.
  - Run the contract check with `openapi.match`, run unit tests through T021, always stop the runtime, and return the validation dict.
- [ ] T036 [US1] Add backend `on_complete` and artifact publication to `loops/shared/devloops/validators/curl.py`:
  - After each achieved milestone, copy `<target>/<runtime.openapi_path>` to `workspaces/<ws>/backend-dev/outputs/openapi.json` and record `openapi_artifact: {path, sha256}` in `run.json`.
  - **At every publication**, as part of the milestone's validation (so before it is marked achieved), the contract check also requires that every operation in the target's OpenAPI document is exercised by a check of this milestone or of an earlier achieved milestone. Otherwise the contract fails, the trial fails with `validation-failed` naming the unverified operations, and nothing is published (FR-019). So `outputs/openapi.json` never lists an unverified endpoint.
  - `on_complete` repeats the same check against the final document as a last safeguard. A failure is recorded as a failed trial of the last milestone with reason `validation-failed`.
- [ ] T037 [US1] Connect `curl` adapter loading in `engine.py` and the backend context block: stack, runtime, and OpenAPI path. Then run `test_validator_curl.py` and `test_backend_loop.py` until they pass.

**Checkpoint**: `backend-dev` works on its own (User Story 1).

---

## Phase 4: User Story 2 - Build a frontend from requirements and a backend contract (Priority: P1)

**Goal**: `frontend-dev` consumes the requirements and an OpenAPI document, serves the UI at a
recorded URL, and validates each milestone through the Playwright MCP server in a restricted call
(FR-020–024, FR-039).

**Independent Test**: Run only `frontend-dev` with fake Claude, `--api-spec` pointing to the fixture
OpenAPI file, and a static-file runtime. `outputs/ui-url.txt` exists, each trial has per-criterion
results with evidence, and the contract check has run.

### Tests for User Story 2

- [ ] T038 [P] [US2] Write `loops/shared/tests/test_validator_playwright.py`, where fake Claude `validate-ui` returns stream-json with `mcp__playwright__browser_navigate` and `browser_snapshot` `tool_use` events plus structured `criteria[]` and `network_requests[]`. Cover:
  - all criteria pass with evidence files → pass;
  - one criterion missing → fail (FR-068);
  - a criterion with empty `evidence` or `observed` → fail (FR-023);
  - no Playwright tool use → fail;
  - a network request not in the OpenAPI → `contract.passed: false` (FR-024);
  - no `backend.base_url` or `backend.start_command` → criteria that need the backend fail and never pass (FR-039);
  - the argv has only `Read` and `mcp__playwright__*` allowed, write tools and Bash disallowed, and `--strict-mcp-config --mcp-config`.
- [ ] T039 [P] [US2] Write `loops/shared/tests/test_frontend_loop.py`: a full flow with a runtime of `python3 -m http.server <port>` serving a static `index.html` written by fake `implement`. Cover:
  - missing `--api-spec` → exit 30 `missing-input`;
  - a non-OpenAPI JSON → exit 30 `invalid-api-spec`;
  - the API spec edited after planning → exit 30 `input-changed` with input `api-spec`;
  - `ui_url` recorded in `run.json` and `outputs/ui-url.txt`.

### Implementation for User Story 2

- [ ] T040 [US2] Create `loops/frontend-dev/loop.json`: `{"name": "frontend-dev", "required_inputs": ["requirements", "api_spec"], "required_tools": ["claude", "playwright-mcp"], "validator": "playwright", "requires_openapi_path": false, "artifacts": ["ui-url"]}`.
- [ ] T041 [P] [US2] Write `loops/frontend-dev/Loop-instructions.md`, the authoritative frontend instructions:
  - Plan milestones by feature or page, with acceptance criteria phrased as observable UI behavior (content, interactions, and results; FR-023).
  - Call the backend only through operations in the supplied OpenAPI document (FR-024).
  - Declare `runtime` (start, `cwd`, `base_url`, `ready_url`).
  - Apply the stack priority order.
  - No application-specific content and no default stack.
- [ ] T042 [P] [US2] Write `loops/frontend-dev/task.md`, the standing-assignment template, with the same placeholders as T033 plus `{{api_spec_path}}`.
- [ ] T043 [P] [US2] Write `loops/shared/prompts/steps/validate-ui.md`: use only the Playwright MCP tools; for each acceptance criterion, list the steps taken, what was observed, pass or fail, and evidence (save screenshots into the given evidence directory and cite the relative paths); also return the `network_requests` from the browser network log; never modify files.
- [ ] T044 [US2] Extend `loops/shared/devloops/inputs.py` for the API spec (FR-011, FR-013a, FR-051a).
  - `--api-spec` is required for `frontend-dev` (missing → `missing-input`) and is checked with `openapi.load_spec` (→ `invalid-api-spec`).
  - Copy it to `state/api-spec.json`, record `inputs.api_spec = {path, sha256}`, and compare the original path's sha256 on every start.
- [ ] T045 [US2] Implement `loops/shared/devloops/validators/playwright.py` (research R-10/R-12):
  - Write `trials/<n>/mcp.json` as `{"mcpServers": {"playwright": {"command": cmd[0], "args": cmd[1:] + ["--output-dir", <abs evidence dir>]}}}`.
  - Start the backend if `config.backend.start_command` is set (with `backend.cwd` and `backend.ready_url`), otherwise use `config.backend.base_url` if set. Start the frontend runtime.
  - Record `ui_url` in `run.json` and write `outputs/ui-url.txt` (D-2).
  - Call `validate-ui` with stream-json. Save `stream.jsonl` in redacted form.
  - Checks: coverage of every criterion; for each criterion, a non-empty `observed` and ≥ 1 existing evidence path; ≥ 1 `mcp__playwright__` tool use; every network request to the backend base URL matching `openapi.match` against `state/api-spec.json`.
  - Pass the backend base URL into the context. When no backend is configured, context `backend: null` tells the validator to mark backend-dependent criteria as failed.
  - Always stop the runtimes.
- [ ] T046 [US2] Add the frontend context block in `engine.py`: API spec path, backend base URL, and the rule to use only documented operations. Then run `test_validator_playwright.py` and `test_frontend_loop.py` until they pass.

**Checkpoint**: `frontend-dev` works on its own (User Story 2).

---

## Phase 5: User Story 3 - Stop safely, retry within limits, and resume (Priority: P1)

**Goal**: Bounded, recoverable execution: trial limits, interruption, service errors,
`needs-input`, recorded retry grants, the call cap, timeouts, and the answers fingerprint
(FR-005–007, FR-030a, FR-051a, FR-055a, FR-061–067).

**Independent Test**: With the stub validator, a milestone that always fails stops after exactly
`max_trials` trials (exit 20) and no later milestone starts. A run killed in the middle of a trial
resumes without re-implementing achieved tasks.

### Tests for User Story 3

- [ ] T047 [P] [US3] Write `loops/shared/tests/test_limits.py`:
  - always-failing validation with the default limit → exactly 3 trials, then exit 20 `trials-exhausted`, the next milestone still `pending`, and its unachieved tasks `failed` (FR-005, SC-004);
  - `--max-trials 2` → 2 trials;
  - a fake call sleeping past `invocation_timeout_seconds` → trial failed `timeout` (FR-062);
  - `max_invocations_per_run` reached → exit 20 `invocation-cap`;
  - a second concurrent `run` → exit 40, naming the active pid (FR-065).
- [ ] T048 [P] [US3] Write `loops/shared/tests/test_recovery.py`:
  - kill the driver while fake `implement` sleeps, then `run` again → the trial is failed with `interrupted`, counts, and trial n + 1 starts; the prompt of the new trial lists only tasks that are not achieved; milestones already achieved are not re-run (FR-030a, SC-003);
  - `run` on `stopped-on-failure` without a grant → no calls and no changes (FR-063);
  - `retry --milestone M01 --reason "x"` → `grants[]` recorded, a `retry-granted` event, a new trial with the reason in the fix prompt;
  - `retry` in any other status → refused, exit 2;
  - `retry` on a run stopped with `planning-trials-exhausted` → refused, exit 2, with a message saying to start a new workspace (FR-061).
- [ ] T049 [P] [US3] Write `loops/shared/tests/test_service_errors.py`:
  - fake Claude returns `api_error_status: 429` → exit 50, status `stopped-on-service-error` code `rate-limited`, trial `void`, and `resume_status` recorded;
  - the next `run` succeeds with the **same** trial number, and the trial count is unchanged (FR-067);
  - status 401 → `auth-failed`;
  - `is_error: true` with no `api_error_status` → a counted work failure.
- [ ] T050 [P] [US3] Write `loops/shared/tests/test_needs_input.py`:
  - `implement` returns a non-empty `needs_input` on trial 1 of 3 → the milestone is `failed` at once with `needs-input` (no further trials), the run exits 20, and the questions are appended to `open-questions.md`;
  - answering them and running `retry` resumes the milestone (FR-055a);
  - editing `open-questions.md` after `approve` → exit 30 `input-changed` with input `answers` (FR-051a);
  - editing `open-questions.md` while `awaiting-approval` and then running `run` → exit 10 (still awaiting approval), not `input-changed`; `replan` and `approve` after such an edit both succeed;
  - editing it after a `needs-input` stop and then running `retry` → the grant records the new hash, and the next `run` proceeds.

### Implementation for User Story 3

- [ ] T051 [US3] Implement interrupted-trial detection in `engine.py` step 1. Any `trial.json` with status `in-progress` at startup becomes `failed` with reason `interrupted` and `ended_at = now`, a `trial-started` event is recorded before the next trial, and the trial counts toward the limit (FR-030a).
- [ ] T052 [US3] Implement the service-error path in `engine.py`. When `claude.py` returns `failure_class == "service"`:
  - mark the trial `void` with a reason of `service-unavailable`, `rate-limited` (429), or `auth-failed` (401/403);
  - store `resume_status` (`planning` or `implementing`), set the status to `stopped-on-service-error`, record a `service-error` event, and exit 50.
  - On the next start, restore `resume_status` and continue; the selector does not count `void` trials (FR-067, research R-19).
- [ ] T053 [US3] Implement `needs_input` handling in `engine.py`. A non-empty `needs_input` from `implement` or `fix` fails the milestone immediately with reason `needs-input`, appends each question to `outputs/open-questions.md` as a new `OQ<n>` with an empty answer, sets `stopped-on-failure` / `needs-input`, and exits 20 (FR-055a, research R-20).
- [ ] T054 [US3] Wire the time limit and call cap into `engine.py`. A `timed_out` call fails the trial with `timeout`, which counts. The selector's `invocation-cap` result sets `stopped-on-failure` / `invocation-cap` (FR-062).
- [ ] T055 [US3] Implement answers fingerprinting in `engine.py` and `cli.py`.
  - `approve` and `retry` record the sha256 of `outputs/open-questions.md` as `approval.answers_sha256` or `grants[].answers_sha256`.
  - **When the comparison applies**: the answers file is compared only if an approval or grant has recorded a hash (`approval.answers_sha256` or the latest `grants[].answers_sha256`). The comparison never runs while the status is `planning` or `awaiting-approval`, or in the `approve`, `replan`, and `retry` commands, because editing answers is the expected step there. When it applies, a changed file gives `input-changed` with input `answers` (FR-051a).
  - The engine itself writes `open-questions.md` only while the status is `planning` or `awaiting-approval`, or when it stops as `stopped-on-failure` with reason `needs-input`. It never records an answers hash when it writes the file; only `approve` and `retry` record hashes.
- [ ] T056 [US3] Add `retry <loop> --milestone <id> --reason <text> [--trials n]` to `cli.py` (FR-063, contracts/cli.md).
  - It is allowed only in `stopped-on-failure` when the milestone is `failed`. Otherwise exit 2.
  - It appends `{milestone_id, granted_at, reason, extra_trials (default max_trials), answers_sha256}` to `run.json` `grants`, resets the milestone status to `in-progress` and its `failed` tasks to `pending`, sets the status to `implementing`, and records a `retry-granted` event.
  - The engine includes grant reasons in `fix` prompts.
  - Run T047–T050 until they pass.

**Checkpoint**: Both loops are safe to leave unattended (User Story 3).

---

## Phase 6: User Story 4 - Implement a single user story (Priority: P2)

**Goal**: Accept a standalone story file, or a PRD plus a story ID, and keep all planned work inside
that story (FR-010, FR-010a, FR-010b; D-6).

**Independent Test**: A run with `--requirements prd.md --story-id US-2` produces a plan whose every
task and criterion cites `US-2`. A plan citing another story is rejected. An unknown ID gives exit 30.

### Tests for User Story 4

- [ ] T057 [P] [US4] Create fixtures `loops/shared/tests/fixtures/stories/prd.md`, a generic two-story PRD with stories `US-1` and `US-2` and a shared "Rules" section, and `loops/shared/tests/fixtures/stories/single-story.md`.
- [ ] T058 [P] [US4] Write `loops/shared/tests/test_story_input.py`:
  - `--story-file` → mode `story-file`;
  - `--story-id US-2` → mode `prd-story` with `story_id` recorded;
  - `--story-id US-9` → exit 30 `story-not-found`, naming `US-9`;
  - `--story-id` together with `--story-file` → exit 2;
  - a plan with a task whose `requirement_refs` lacks `US-2` → counted as an invalid planning trial;
  - the plan prompt context contains the scope rule and the story ID.

### Implementation for User Story 4

- [ ] T059 [US4] Add the `--story-id` and `--story-file` options to `cli.py` (they are mutually exclusive, exit 2 otherwise). Pass the mode through to the workspace and run state, as `requirements.mode` = `"prd" | "story-file" | "prd-story"` and `story_id`.
- [ ] T060 [US4] Add story modes to `inputs.py`. For `prd-story`, the story ID must appear literally, case-sensitive, in the file text; otherwise the result is `story-not-found`, with the ID in the message (FR-010b). Record the mode and ID in `workspace.json` and `run.json`.
- [ ] T061 [US4] Add story-scope rules to `plan.py`: in `story-file` and `prd-story` modes, every task and acceptance criterion `requirement_refs` must include the story ID (FR-010, FR-010a).
- [ ] T062 [US4] Add a story-scope block to the engine context and a matching section in `loops/shared/prompts/common.md`: "Plan and implement only story `<id>`. Other PRD sections are context only. If the story depends on another story that is not implemented, raise an open question; never implement the other story." Run T058 until it passes.

**Checkpoint**: Single-story input works for both loops (User Story 4).

---

## Phase 7: User Story 5 - Run both loops through an orchestrator (Priority: P2)

**Goal**: One command runs `backend-dev`, then `frontend-dev`, in the same workspace and hands over
the verified OpenAPI document and the backend runtime (FR-040–042, FR-052, FR-056; D-9).

**Independent Test**: With fake Claude, `orchestrate` pauses (exit 10) while either loop is
awaiting approval. It never starts `frontend-dev` before `backend-dev` is `completed`. After
completion, `orchestrator/state.json` records the handoff with the OpenAPI sha256.

### Tests for User Story 5

- [ ] T063 [P] [US5] Write `loops/shared/tests/test_orchestrator.py`:
  - backend `awaiting-approval` → exit 10, and there is no `frontend-dev/state/` directory;
  - backend `stopped-on-failure` → exit 20, and the orchestrator step records the loop and reason;
  - backend `completed` → frontend runs with `--api-spec workspaces/<ws>/backend-dev/outputs/openapi.json` and `backend.start_command`, `cwd`, and `ready_url` taken from the backend plan runtime;
  - re-running `orchestrate` resumes each loop from its own state;
  - `engine.Engine` is used for both loops through the same code path as `run` (spy or patch).

### Implementation for User Story 5

- [ ] T064 [US5] Implement `loops/shared/devloops/orchestrator.py` (plan, "Optional orchestration"; research R-15). Write `workspaces/<ws>/orchestrator/state.json` = `{status: running|paused|completed|stopped, steps: [{loop, status, reason, started_at, ended_at}], handoff: {api_spec: {path, sha256}, backend_runtime: {start_command, cwd, base_url, ready_url}}}`.
  - Run the backend-dev Engine. If the result is not exit 0, record it and return the same exit code.
  - Build the handoff from `backend-dev/outputs/openapi.json` and `state/plan.json` runtime, with `cwd` resolved against the backend target.
  - Run the frontend-dev Engine with those inputs and config overrides, then record completion.
  - The loops contain no orchestrator-specific code.
- [ ] T065 [US5] Add `orchestrate` to `cli.py`, with `--workspace`, `--requirements`, `--story-id`/`--story-file`, `--target-root` (default targets `<root>/backend` and `<root>/frontend`), `--backend-target`, `--frontend-target`, `--config`, and `--json`. Exit codes: 10, 20, 30, 50, or 0 (contracts/cli.md).
- [ ] T066 [P] [US5] Render `workspaces/<ws>/orchestrator/progress.md` from `orchestrator/state.json` in `render.py`, and write `loops/orchestrator/README.md`, which describes the orchestration behavior and points to `devloops/orchestrator.py`. Run T063 until it passes.

**Checkpoint**: Orchestrated and direct runs behave identically (User Story 5).

---

## Phase 8: User Story 6 - Reuse the loops for a different application (Priority: P3)

**Goal**: Show that the unchanged infrastructure runs on unrelated requirements and contains nothing
specific to any one application (FR-037, FR-050, FR-059; SC-006).

**Independent Test**: Running full flows for both loops on two unrelated fixtures, in separate
workspaces, leaves the hash manifest of `loops/` and `bin/` unchanged.

- [ ] T067 [P] [US6] Create the smoke fixtures:
  - `loops/shared/tests/fixtures/smoke/requirements.md`: one story, "a `GET /health` endpoint returning `{\"status\":\"ok\"}` and a page that shows that status".
  - `loops/shared/tests/fixtures/smoke-alt/requirements.md`: one story, "a counter: `POST /counter/increment` and `GET /counter`, and a page with a button that increments it and shows the value".

  They share no entities or endpoints (SC-006). These are the inputs for the real-Claude runs in quickstart §2–4.
- [ ] T068 [P] [US6] Write `loops/shared/tests/test_reusability.py`. With fake Claude, run the backend-dev and frontend-dev flows for both smoke fixtures in workspaces `reuse-a` and `reuse-b`. Assert that both reach `completed`, that `boundary.snapshot` manifests of `loops/` and `bin/` are identical before and after, and that the two workspaces share no files.
- [ ] T069 [P] [US6] Write `loops/shared/tests/test_no_app_specifics.py`. It scans only the files that steer the loops' behavior:
  - `loops/*/Loop-instructions.md`, `loops/*/task.md`, and `loops/*/loop.json`;
  - `loops/shared/prompts/**`;
  - `loops/shared/config/defaults.json`;
  - `loops/shared/devloops/**/*.py` and `bin/devloops`.

  It does **not** scan `loops/README.md`, `loops/orchestrator/README.md`, or `loops/shared/tests/`, because documentation may show example commands.

  The test fails if a scanned file contains, case-insensitively and as a whole word, an application term (`quickflow`, `habit`, `todo plan`, `learning resource`) or a stack default in a stack-specific form: `npm install`, `npm run`, `react-dom`, `create-react-app`, `from 'react'`, `require('express')`, `from 'express'`, `express()`, `fastapi`, `django`, `flask`, `vite`, `next.js`. Plain English words such as "express" or "react" in prose do not match. Keep both lists, and an allow-list of accepted phrases, in the test file (FR-037, FR-059). The Playwright MCP launcher in `defaults.json` (`npx @playwright/mcp`) matches neither list and needs no exception.

**Checkpoint**: Reusability is proven offline (User Story 6).

---

## Phase 9: Polish & Cross-Cutting Concerns

- [ ] T070 [P] Write `loops/README.md` (FR-047/048), covering only implemented behavior:
  - an overview and prerequisites (Claude Code login, Python ≥ 3.10, curl, node/npx, and `npx playwright install chromium`);
  - the command reference with exit codes (from contracts/cli.md), configuration keys and defaults (from `defaults.json`), and the workspace layout;
  - approval, replan, and `open-questions.md`; recovery (interrupted trials, `retry`, service errors with exit 50, stale locks); the secrets configuration, and a note to review workspaces before committing them (FR-070);
  - Mermaid `sequenceDiagram`s for backend-dev, frontend-dev, and orchestrate.
- [ ] T071 [P] Create optional Claude Code skills (research R-16): `.claude/skills/loops-backend-dev/SKILL.md`, `.claude/skills/loops-frontend-dev/SKILL.md`, and `.claude/skills/loops-orchestrate/SKILL.md`. Each has frontmatter `name` and `description` and instructions to run exactly one `bin/devloops` command through Bash with the user's arguments, then summarize `status --json`. They contain no loop logic.
- [ ] T072 [P] Add `export-sessions [--csv <file>]` to `cli.py`. It writes a CSV with the columns workspace, loop, step, milestone, trial, session ID, prompt path, the four token counts, cost, start, and end, built from every `state/invocations.jsonl` in the workspace (FR-033). Test it in `loops/shared/tests/test_export.py`.
- [ ] T073 [P] Implement optional `git.commit_per_milestone` (spec A-6), which is off by default, in `loops/shared/devloops/engine.py`. After an achieved milestone, if the target is in a git repo, run `git add` for **only** the target's changed paths and commit with a Conventional Commits message, `feat(<loop>): complete <milestone id> <title>`. Test it in `loops/shared/tests/test_git_commit.py`.
- [ ] T074 [P] Extend `status` in `cli.py` to list any evidence file larger than 1 MB under the workspace, as a review hint (research R-21).
- [ ] T075 Run the full offline suite (`python3 -m unittest discover -s loops/shared/tests -v`, quickstart §1) and fix failures until it is green. Confirm that `git status loops/ bin/` is clean after the suite runs.
- [ ] T076 Run quickstart §2–4 with real Claude Code, using `loops/shared/tests/fixtures/smoke` and `smoke-alt` (SC-011, SC-008, SC-006), following only the commands in `loops/README.md`. Record the outcome, workspace paths, and any README gaps in `specs/001-reusable-dev-loops/validation-results.md`, and fix the documentation or code where the README and the behavior differ (FR-048).

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)** has no dependencies.
- **Foundational (Phase 2)** depends on Setup and blocks every user story.
- **US1 (Phase 3), US2 (Phase 4), US3 (Phase 5), US4 (Phase 6)** depend only on Foundational and are
  independent of one another. Where they touch the same file (`engine.py`, `cli.py`,
  `inputs.py`), they edit different functions, so apply them in sequence if one person does the work.
- **US5 (Phase 7)** depends on US1 and US2, because the orchestrator hands the backend's output to
  the frontend.
- **US6 (Phase 8)** depends on US1 and US2, because it runs full flows.
- **Polish (Phase 9)** depends on all the stories. T076 needs a logged-in Claude Code.

### Within Foundational

- T008 → T011, T016.
- T009 → T012, T022, T023.
- T009 + T010 → T017.
- T011–T024 → T025 → T026 → T027.

### Within stories

- The tests for a story are written first and must fail before its implementation tasks.
- The `loop.json` task comes before the adapter task.
- The adapter comes before the engine wiring, which comes before running that story's tests.

## Parallel Opportunities

- **Setup**: T003, T004, T005, T006, and T007 can run together after T001 and T002.
- **Foundational**:
  - T008, T009, T010, T014, T015, T018, T019, T020, and T021 can run together, since they touch
    different files.
  - Then T011, T012, T013, T016, T017, T022, T023, and T024.
- **Across stories**: After Phase 2, US1, US2, US3, and US4 can proceed in parallel.
- **Within stories**:

| Story | Tasks that can run together |
|-------|-----------------------------|
| US1 | T028, T029, T030 (tests); T032, T033, T034 (docs and prompts) |
| US2 | T038, T039; T041, T042, T043 |
| US3 | T047, T048, T049, T050 |
| US4 | T057, T058 |
| US6 | T067, T068, T069 |
| Polish | T070–T074 |

## Parallel Example: User Story 1

```text
# After Phase 2 is done, in parallel:
T028  fixtures/http_app.py + http_app.openapi.json
T029  tests/test_validator_curl.py
T030  tests/test_backend_loop.py
T032  loops/backend-dev/Loop-instructions.md
T033  loops/backend-dev/task.md
T034  loops/shared/prompts/steps/author-checks.md
# Then in sequence:
T031 → T035 → T036 → T037
```

## Implementation Strategy

### MVP first

1. Phase 1 (Setup), then Phase 2 (Foundational). The engine then runs with a stub validator (T027).
2. Phase 3 (US1): `backend-dev` produces a verified backend and OpenAPI document. **Stop and
   validate** with T030, then optionally run quickstart §2 (backend part) with real Claude.
3. Phase 5 (US3) comes next, before any unattended use. Its bounded-execution guarantees are P1.

### Incremental delivery

| Step | Adds |
|------|------|
| MVP | Setup + Foundational + US1 |
| + US3 | Safe to run unattended |
| + US2 | Frontend loop, so both required loops exist |
| + US4 | Single-story input |
| + US5 | Orchestrator |
| + US6 | Reusability proven |
| + Polish | README (the FR-047 deliverable), skills, export, and the real-Claude validation (SC-011) |

### Traceability

Every requirement in spec.md is covered by at least one task:

| Requirement | Tasks |
|-------------|-------|
| FR-001–004b | T001, T022, T031–T033, T040–T042 |
| FR-005–008 | T021, T023, T025, T047 |
| FR-009–013b | T013, T014, T044, T059, T060 |
| FR-014–019 | T031–T037 |
| FR-020–024 | T040–T046 |
| FR-025–029 | T025, T027 |
| FR-030–034 | T009, T017, T022, T051 |
| FR-035–037 | T012, T018, T019, T069 |
| FR-038–039 | T025, T045 |
| FR-040–043 | T064, T065 |
| FR-044–046 | T017, T024, T071 |
| FR-047–048 | T070, T076 |
| FR-049–052 | T012, T013, T044, T055, T064 |
| FR-053–056 | T022, T025, T026, T053, T055, T064 |
| FR-057–060 | T016, T024, T032, T041 |
| FR-061–071 | T010, T012, T016, T017, T025, T047–T056, T069 |
| SC-001–011 | T027, T047–T050, T068, T075, T076 |

## Notes

- A `[P]` task touches different files and does not depend on an incomplete task.
- The `[USn]` labels map to spec.md user stories 1–6.
- Commit after each task or logical group, with Conventional Commits and no Co-Authored-By
  trailer (user preference).
- Stop at any checkpoint to validate a story on its own.
- Never add application-specific requirements to `loops/`; T069 enforces this.
