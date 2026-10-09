# Contract: `devloops` CLI

> **Changed by 002** ([specs/002-devloops-init/contracts/cli.md](../../002-devloops-init/contracts/cli.md)):
> - `--workspace` is optional: the default is the project configuration's `workspace`, and a bare
>   name resolves under its `workspaces_dir`. Commands find the project from the current folder.
> - `dashboard.html` is a summary page, written when a command pauses, stops, or ends, with no
>   file links and no self-reload; `dashboard --serve` serves the live dashboard with every file
>   and conversation, and `dashboard --export` writes a self-contained full dashboard.
> - New commands `init` and `check`; new `run` option `--speckit-feature`; targets and
>   requirements default to the project configuration.

> **Revised by specs/003-single-run-command**
> ([specs/003-single-run-command/contracts/cli.md](../../003-single-run-command/contracts/cli.md)):
> - One run command: `devloops run` takes no loop name and runs the loops the project includes,
>   in order. The per-loop `run <loop>` (with `--target` and `--api-spec`) and the separate
>   orchestrator command are removed; either is a usage error (exit 2).
> - `approve`, `replan`, and `retry` take no loop name: they act on the waiting loop, and always
>   continue the whole run.
> - The run's record is `run/state.json` (formerly `orchestrator/state.json`).

The entry point is `bin/devloops`, and every run goes through it
[RC, research R-1/R-16]. Each command prints a human-readable summary. With `--json`, it prints a
single JSON status object instead (the same shape as `status --json`).

## Common options

| Option | Meaning |
|--------|---------|
| `--workspace <name\|path>` | **Required.** The workspace name (under `workspaces/`) or a path. It is created on the first `run` (D-3) |
| `--config <file>` | An optional config file, merged over the defaults. See [config.schema.json](./config.schema.json) |
| `--json` | Machine-readable output |

## Commands

### `run`

Starts or resumes the workspace's run (FR-039, FR-040). It runs each loop the run includes, in
order: `backend-dev`, then `frontend-dev`, handing the backend's verified OpenAPI document and how
to start the backend to the frontend (FR-041, FR-052).

> **Revised by specs/003-single-run-command**: this section described the per-loop
> `run <backend-dev|frontend-dev>` and a separate orchestrator command. `run` now takes no loop
> name; `--target` is replaced by `--backend-target` / `--frontend-target`, and `--api-spec` is
> removed (frontend-dev gets the backend's contract from the run's handoff).

| Option | Meaning | Rule |
|--------|---------|------|
| `--requirements <file>` | A PRD Markdown file, or a standalone story file; passed to every loop | Required on the first run unless the project sets it; if given later, it must match the recorded fingerprint (D-8) |
| `--story-id <id>` | Selects one story within `--requirements` (D-6 form b) | Must occur in the file, or the run stops with an input error (FR-010b) |
| `--story-file` | Marks `--requirements` as a standalone story (D-6 form a) | Mutually exclusive with `--story-id` |
| `--target-root <dir>` | Places the loops the project includes at `<dir>/backend` and `<dir>/frontend` [RC] | Never includes a loop the project leaves out |
| `--backend-target <dir>`, `--frontend-target <dir>` | That loop's directory for application code (D-7, FR-035a); includes the loop even when the project sets it to `null` | Created if missing; must be writable, outside `loops/`, and not the other loop's target. For a loop already recorded in the workspace, a different folder is a usage error (exit 2) |
| `--max-trials <n>` | Overrides `max_trials` (FR-006) for every loop this command starts or resumes; those loops keep it | Integer ≥ 1 |
| `--review-plan` | Sets `questions: ask`: pause after each plan for review (FR-053, D-13) | Also allowed on a later start; recorded in `run/state.json` and as a `config-override`. Mutually exclusive with `--accept-suggested` |
| `--accept-suggested` | Sets `questions: accept-suggested`, the default (FR-055c) | Also allowed on a later start; recorded in `run/state.json` and as a `config-override` |

**Loop selection**: a loop is included when the workspace has recorded its target, then when a
target flag names it, then when `targets.<loop>` in the project configuration is neither `null` nor
missing. Before anything is written (no workspace, lock, or `run/state.json`), a run with no loop
exits 30 (`no-loop`), and a run with `frontend-dev` but not `backend-dev` exits 30
(`frontend-needs-backend`; frontend-only runs are not supported yet).

**Behavior** (see the iteration model in [plan.md](../plan.md#iteration-model)):
- A run exits when it reaches `awaiting-approval`, a terminal state, `stopped-on-service-error`, or
  a hard limit. By default the plan is approved automatically, so `awaiting-approval` is reached
  only when plans are reviewed or a question has no suggested answer.
- At `awaiting-approval`, when standard input and output are a terminal and `--json` is not given,
  it asks `[a]pprove [e]dit answers [r]eplan [q]uit` (FR-056a): `a` and `r` act as `approve` and
  `replan` (continuing), `e` opens `open-questions.md` in `$VISUAL` or `$EDITOR`, `q` (or end of
  input) exits 10.
- Before running any loop, it checks the required tools (FR-013b) of every loop with work left; a
  missing one exits 30 (`missing-tool`) with nothing recorded (FR-056b). Before planning
  frontend-dev, the backend's handed-over OpenAPI document must parse as OpenAPI 3 (FR-013a).
- A completed loop is not run again, and `frontend-dev` starts only after `backend-dev` is
  `completed`. A run that includes only `backend-dev` is completed when it completes.
- The run stops at a plan pause (10), a stopped loop (20 or 30), or a service error (50). Running
  it again resumes.
- **Exit codes**:

  | Code | Meaning |
  |------|---------|
  | 0 | `completed` |
  | 10 | `awaiting-approval` |
  | 20 | `stopped-on-failure` |
  | 30 | `stopped-on-input-error` |
  | 40 | Lock held by another driver (FR-065) |
  | 50 | `stopped-on-service-error`: Claude Code outage, rate limit, or authentication; no trial consumed (FR-067). Re-run to resume |
  | 2 | Usage error |

### `approve`

Accepts the stored plan of the loop in `awaiting-approval` together with any answers written in
`outputs/open-questions.md`, and moves the run to `implementing`. It is allowed only in
`awaiting-approval`. It records `Approval` (FR-053, FR-054). An empty answer under a suggested
answer accepts the suggestion: it is copied into the answer and marked `**Answer source:**` before
the file is fingerprinted, and its ID is listed in `approval.accepted_suggestions` (FR-053a). It
then continues the run (FR-056a). When no loop is awaiting approval it is a usage error (exit 2),
`nothing awaits approval (run: <status>)`, that changes nothing.

### `replan`

Re-runs planning, for the loop in `awaiting-approval`, with the answers in
`outputs/open-questions.md`. This consumes a planning trial (research R-6). It then continues the
run: under `questions: ask` it pauses again at `awaiting-approval`; under `accept-suggested` the new
plan is approved and implemented. With `--no-continue` it always pauses at the new plan. When no
loop is awaiting approval it is the same usage error as `approve`.

> **Revised by specs/003-single-run-command**: `approve`, `replan`, and `retry` took a loop name;
> they now act on the waiting loop.

### Continuing after a decision (`approve`, `replan`, `retry`)

These commands take `--no-continue`, `--review-plan` / `--accept-suggested` (which apply to the
continued run, so they are refused with `--no-continue`), and `--force-unlock`.
Unless `--no-continue` is given, after recording the decision they continue the whole run, as
`devloops run` does, and exit with the run's code (FR-056a): a completed backend goes on to the
frontend. `--json` then prints the `run` object with `decision: {command, loop}`. With
`--no-continue` the decision is only recorded (`--json` prints that loop's status object), and the
next `devloops run` continues.

> **Revised by specs/003-single-run-command**: a decision used to continue a single loop, or the
> orchestrated run only in a workspace that had one. It now always continues the whole run.

A refused decision runs nothing and leaves `run.json` and `run/state.json` unchanged: a usage error
(exit 2), another driver's lock (40), or, when it would continue, a missing tool (30, checked before
the decision is recorded).

### `status [<loop>]`

Prints the run status, the current or next milestone, trials used out of the limit, the last
failure, the UI URL (frontend), and the OpenAPI artifact (backend). It is read-only. Without a loop
it shows the loops the run includes, preceded by `run: <status>` when `run/state.json` exists
(`--json` adds the `run` key).

### `retry --milestone <id> [--reason "<text>"] [--trials <n>]` (FR-063)

Applies to the loop in `stopped-on-failure`; when there is none it is a usage error (exit 2), `no
loop is stopped on failure (run: <status>)`. It moves that loop back to `implementing`, granting
`n` more trials (default: `max_trials`) to the failed milestone, then continues the run
(FR-056a). The grant is recorded in
`run.json` `grants[]` and as a `retry-granted` event, with its time and reason. The reason text is
passed to later fix prompts as developer guidance; without `--reason` it is empty and no
guidance is passed.

- For a `needs-input` stop (FR-055a), answer the questions in `outputs/open-questions.md` first,
  or leave an answer empty to accept its suggested answer (FR-053a); `retry` copies accepted
  suggestions into the file and lists them in the grant's `accepted_suggestions`. It is refused
  while a question has neither an answer nor a suggestion. The file's fingerprint is recorded with
  the grant.
- `retry` is refused for a run stopped with `planning-trials-exhausted`. That stop is final
  (FR-061), and the message says to start a new workspace.
- `retry` is refused for any other status. Without a grant, `run` on a stopped workspace makes no
  changes (FR-063).

### `export-sessions [--csv <file>]`

Writes a table of every invocation (workspace, loop, step, milestone, trial, session ID, prompt
path, tokens, cost, start, end). This is the input for the prompts/session-ID spreadsheet (FR-033).

### `dashboard`

Writes `workspaces/<ws>/dashboard.html` from the workspace state: one self-contained page with the
overview statistics, the trial timeline, costs, every milestone's criteria, checks, evidence, and
trials, the questions and answers, the run and its handoff, and every Claude call and event.
`run`, `approve`, `replan`, and `retry` rewrite it after they finish; a failure to
write it prints a warning and never changes their exit code.

## Optional Claude Code skills [RD + RC, research R-16]

The skills `devloops-run`, `devloops-approve`, `devloops-replan`, `devloops-retry`,
`devloops-status`, and `devloops-dashboard` each run exactly one CLI command through Bash and report
the result. They contain no loop logic, and none takes a loop name except `devloops-status`.

> **Revised by specs/003-single-run-command**
> ([contracts/skills.md](../../003-single-run-command/contracts/skills.md)): the per-loop skills
> and the orchestrator skill are replaced by `devloops-run`, which runs `devloops run`.
