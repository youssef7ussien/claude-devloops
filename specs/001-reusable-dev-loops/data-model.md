# Data Model: Reusable Development Loops

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**: 2026-09-27

This file covers the loop infrastructure only. No application entities appear here. The exact
formats are defined by the JSON Schemas in [contracts/](./contracts/). This document describes
meaning, relationships, validation rules, and state transitions.

`state/` is the authoritative record (A-3). Every Markdown file in `outputs/`, plus `progress.md` and
the workspace `task.md`, is **rendered from state** by the driver [RC, research R-5].

## Entity overview

```text
Workspace 1 ──< LoopRun (backend-dev | frontend-dev) 1 ── 1 Plan 1 ──< Milestone 1 ──< Task
                  │                                                    │
                  │                                                    ├──< AcceptanceCriterion
                  │                                                    ├── 0..1 CheckSet (backend)
                  │                                                    └──< Trial 1 ──< Invocation
                  │                                                                 └── 0..1 ValidationResult ──< Evidence
                  ├──< Event (action-item log)
                  └── Approval
Workspace 1 ── 0..1 OrchestratorRun
```

## Workspace

A per-application or per-run folder (D-3). File: `workspaces/<name>/workspace.json`.

| Field | Meaning | Rules |
|-------|---------|-------|
| `name` | Workspace identifier | Matches the folder name; `[a-z0-9-]+` |
| `created_at` | ISO-8601 UTC | Set once |
| `requirements` | `{path, sha256, mode: "prd" \| "story-file" \| "prd-story", story_id?}` | Fixed at the first run; see D-8 |
| `targets` | `{ "backend-dev": path, "frontend-dev": path }` | Absolute and must exist or be creatable; must not lie inside `loops/` (FR-035a–d) |
| `config_path` | Optional workspace config file | See [config.schema.json](./contracts/config.schema.json) |

**Identity rule (FR-051, FR-051a)**: A run is attached to an existing workspace only if its
requirements `sha256`, mode, and `story_id` match `workspace.json`. The same byte-level comparison
is repeated on every start for the API spec (frontend-dev) and for the approved answers. A mismatch
gives `stopped-on-input-error` with reason `input-changed` (naming the input: `requirements`,
`api-spec`, or `answers`; D-8) or `workspace-mismatch`.

## LoopRun

One loop's run within a workspace. File: `workspaces/<ws>/<loop>/state/run.json`.

| Field | Meaning |
|-------|---------|
| `loop` | `backend-dev` \| `frontend-dev` |
| `status` | See the state machine below |
| `status_reason` | Code + message when stopped. Codes by outcome: **stopped-on-failure**: `trials-exhausted`, `planning-trials-exhausted`, `invocation-cap`, `needs-input`. **stopped-on-input-error**: `missing-input`, `story-not-found`, `invalid-api-spec`, `missing-tool`, `input-changed`, `workspace-mismatch`, `target-unwritable`. **stopped-on-service-error**: `service-unavailable`, `rate-limited`, `auth-failed`. See [run-state.schema.json](./contracts/run-state.schema.json). Boundary violations are trial-level failure reasons |
| `inputs` | `{requirements: {path, sha256}, api_spec?: {path, sha256}}`. `api_spec` is required for frontend-dev (FR-011) |
| `target_dir` | The only root that application code may be written to (D-7) |
| `effective_config` | The merged configuration (defaults < workspace < CLI), frozen at the first run. Later CLI overrides are recorded as events |
| `planning` | `{trials: [Trial], status}` |
| `approval` | `Approval` or null |
| `invocation_count` | Checked against `max_invocations_per_run` |
| `ui_url` | frontend-dev only: the URL where the built UI is served (D-2) |
| `openapi_artifact` | backend-dev only: `{path, sha256}` of `outputs/openapi.json` |
| `grants[]` | Trial-budget grants (FR-063): `{milestone_id, granted_at, reason, extra_trials}` |

### LoopRun state machine

```text
          ┌────────────────────────── input check fails ───────────────────────────┐
          │                                                                         ▼
 (new) ─► planning ──valid plan──► awaiting-approval ──approve──► implementing ──all milestones achieved──► completed
             │   ▲                    │        │                    │
             │   └──────replan────────┘        │                    ├── milestone trials exhausted ─► stopped-on-failure
             │                                 │                    ├── invocation cap reached ─────► stopped-on-failure
             │                                 │                    ├── needs-input (FR-055a) ──────► stopped-on-failure
             └── planning trials exhausted ────┴────────────────────┴──────────────────────────────► stopped-on-failure
 any state ── input fingerprint changed / missing input or tool / invalid API spec / workspace mismatch ──► stopped-on-input-error
 planning or implementing ── service failure (R-19) ──► stopped-on-service-error ──next run──► back to the same state
 stopped-on-failure ── retry --milestone (grant, FR-063) ──► implementing
```

- Terminal states: `completed`, `stopped-on-failure`, `stopped-on-input-error`. Starting a run
  from a terminal state makes no changes and reports the status (FR-029, FR-063).
- `stopped-on-failure` has one exit: an explicit `retry` grant, which is recorded in `grants[]`
  and as an event (FR-063). The exception is `planning-trials-exhausted`, which is final; start a
  new workspace (FR-061).
- **Answers comparison**: the answers file is compared only once an approval or grant has recorded
  its hash. Edits while `planning` or `awaiting-approval` are expected (FR-051a).
- `stopped-on-service-error` is resumable. The next `run` retries the voided step, no trial was
  consumed (FR-067), and the stored pre-stop state (`planning` or `implementing`) is restored.
- `awaiting-approval` is a pause, not a terminal state (FR-028, FR-053).

## Plan

Returned by the planning step as structured output. It is checked and stored at
`state/plan.json`. Schema: [plan.schema.json](./contracts/plan.schema.json).

| Field | Meaning |
|-------|---------|
| `requirements_inventory[]` | `{ref, summary}`: the requirement or story references the plan covers, in the source document's own identifiers |
| `stack` | `{summary, source: existing-code \| requirements \| configuration \| proposed, conflicts[]}` (D-5) |
| `runtime` | `{install_command?, start_command, cwd, base_url, ready_url, unit_test_command?, openapi_path?}`. `openapi_path` is required for backend-dev |
| `milestones[]` | An ordered list of Milestone |
| `open_questions[]` | `{id, question, context, affects[]}` (D-4) |
| `assumptions[]` | `{id, text, source}`: planning-time assumptions, stated explicitly |

**Validation rules (driver)** [RC, R-5]:
- All IDs are unique.
- `milestones[].depends_on` form a DAG, and the list order is a valid topological order.
- Each milestone has ≥ 1 task and ≥ 1 acceptance criterion.
- Each task has ≥ 1 `requirement_refs` entry that appears in `requirements_inventory`.
- In `prd-story` or `story-file` mode, every `requirement_refs` list contains the story ID
  (FR-010, FR-010a).
- `stack.source` is one of the four values. A non-empty `stack.conflicts` implies at least one
  open question (FR-060).

## Milestone

The unit of planning, validation, trials, and accounting (A-2, D-1). Rendered to
`outputs/milestone-<NN>-<slug>.md`.

| Field | Meaning |
|-------|---------|
| `id` | `M01`, `M02`, … |
| `title`, `goal` | Human-readable |
| `depends_on[]` | Milestone IDs |
| `tasks[]` | Task |
| `acceptance_criteria[]` | `{id: "M01-AC1", text, requirement_refs[]}`: observable behaviors (FR-018, FR-023) |
| `status` | `pending → in-progress → achieved`, or `failed` |
| `trials[]` | Trial |
| `started_at` / `ended_at` | First trial start / last validation end |

**Transitions**:
- `pending → in-progress`: the milestone's first trial starts.
- `in-progress → achieved`: a trial's validation passes. Only then are tasks marked achieved
  (FR-027).
- `in-progress → failed`: a trial fails and `len(trials) == max_trials`. The run moves to
  `stopped-on-failure`, and no later milestone starts (D-1).

## Task

| Field | Meaning |
|-------|---------|
| `id` | `M01-T01`, … |
| `title`, `description` | What to build |
| `requirement_refs[]` | Traceability to the requirements (constitution VIII) |
| `status` | `pending → implemented → achieved`, or `failed` |

- `implemented` is set from the implement or fix step's structured result.
- `achieved` is set by the driver only when the milestone's validation passes.
- When a milestone fails, all of its tasks that are not achieved become `failed`.

## Trial

`state/milestones/<id>/trials/<n>/trial.json`. The planning trials use the same shape.

| Field | Meaning |
|-------|---------|
| `n` | 1…(`max_trials` + trials granted under FR-063) |
| `kind` | `implement` (n = 1) \| `fix` (n ≥ 2) \| `plan` \| `replan` |
| `status` | `in-progress → passed`, or `failed`, or `void` (not counted) |
| `failure` | `{reason, detail}`. **Counted** reasons: `validation-failed`, `boundary-violation`, `timeout`, `claude-error`, `invalid-output`, `runtime-start-failed`, `interrupted`, `needs-input`. **Void** reasons (status `void`): `service-unavailable`, `rate-limited`, `auth-failed` (FR-067, R-19) |
| `needs_input[]` | Questions returned by the implement or fix step (FR-055a, R-20) |
| `assumptions[]` | `{text, affects}` returned by the implement or fix step; rendered in the milestone file and the final report (FR-055) |
| `invocations[]` | Session IDs (see the invocation records) |
| `validation` | ValidationResult reference |
| `started_at` / `ended_at` | |

- `in-progress` is written **before** the first call.
- A trial still `in-progress` when a run starts becomes `failed` with reason `interrupted`, and it
  counts toward the limit (FR-030a, R-4).
- A `void` trial does not count. Its number is reused by the next attempt.
- A `needs-input` failure fails the milestone at once, even if trials remain (FR-055a).

## CheckSet (backend-dev)

`state/milestones/<id>/checks.json`. Schema: [checks.schema.json](./contracts/checks.schema.json).
It is written once, on the milestone's first trial, and then frozen (R-8).

- Each check has an `id`, the `criteria[]` it covers, a `request` (method, path, headers, body), an
  `expect` (status, `body_contains[]`, `json_equals{path: value}`), and an optional
  `capture{var: json_path}` for chained requests.
- **Coverage rule**: every acceptance criterion of the milestone is listed by at least one check.

## ValidationResult

`state/milestones/<id>/trials/<n>/validation.json`. Schema:
[validation-result.schema.json](./contracts/validation-result.schema.json).

| Field | Meaning |
|-------|---------|
| `kind` | `curl` \| `playwright` |
| `passed` | Computed by the driver, never taken from the model |
| `criteria[]` | `{criterion_id, passed, observed, evidence[]}` |
| `checks[]` | curl only: `{check_id, passed, command, response: {status, headers, body_path}, failures[]}` |
| `contract` | `{passed, unmatched_operations[]}`: OpenAPI consistency (backend FR-019) or API-usage conformance (frontend FR-024) |
| `unit_tests` | `{enabled, command?, exit_code?, log_path?}` |
| `boundary` | `{passed, violations[]}` (R-11) |

**The pass rule**: `passed = all(criteria.passed) ∧ contract.passed ∧ boundary.passed ∧
(¬unit_tests.enabled ∨ unit_tests.exit_code == 0)`. In addition:
- every acceptance criterion of the milestone has an entry; a missing entry counts as failed
  (FR-068);
- for `playwright`, every criterion entry has a non-empty `observed` and at least one evidence
  item (FR-023);
- every evidence path exists.

## Invocation (session record)

One JSON line per Claude call in `state/invocations.jsonl`. Schema:
[invocation-record.schema.json](./contracts/invocation-record.schema.json).
It holds the session ID, `step`, milestone, trial, prompt path, timestamps, tokens (four counters,
or `null` when unavailable), cost, duration, turns, `is_error`, `subtype`, and
`permission_denials`.

## Approval

In `run.json`: `{approved_at, action: approve | replan, answers_path, answers_sha256}`.
The answers file is `outputs/open-questions.md`, edited by the developer. `answers_sha256` is
compared on every later start (FR-051a). Answers given for `needs-input` questions before a
`retry` are fingerprinted the same way.

## Event (action-item log)

One JSON line per action in `state/events.jsonl`: `{at, loop, milestone?, trial?, type, message}`.
The `type` values are `run-started`, `input-check`, `config-override`, `lock-cleared`,
`plan-stored`, `paused`, `approved`,
`trial-started`, `trial-voided`, `task-implemented`, `validation-passed`, `validation-failed`,
`needs-input`, `retry-granted`, `service-error`,
`boundary-violation`, `milestone-achieved`, `git-commit`, `stopped`, and `completed`.
`config-override` records a CLI override applied over the frozen `effective_config`; `lock-cleared`
records a stale lock removed by `--force-unlock`; `git-commit` records the outcome of the optional
per-milestone commit (`git.commit_per_milestone`, A-6). Events are rendered into the action-item section of `progress.md` (FR-004).

## OrchestratorRun

`workspaces/<ws>/orchestrator/state.json`.

| Field | Meaning |
|-------|---------|
| `status` | `running` \| `paused` (a loop is awaiting approval) \| `completed` \| `stopped` |
| `steps[]` | `{loop, status, reason?, started_at, ended_at}` in order: backend-dev, then frontend-dev |
| `handoff` | `{api_spec: {path, sha256}, backend_runtime: {start_command, cwd, base_url, ready_url}}` |

**Rule (FR-042, FR-056)**: `frontend-dev` starts only when `backend-dev.status == completed`.
