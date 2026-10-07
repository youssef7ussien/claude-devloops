# Contract: `devloops` CLI

> **Changed by 002** ([specs/002-devloops-init/contracts/cli.md](../../002-devloops-init/contracts/cli.md)):
> - `--workspace` is optional: the default is the project configuration's `workspace`, and a bare
>   name resolves under its `workspaces_dir`. Commands find the project from the current folder.
> - `dashboard.html` is a summary page, written when a command pauses, stops, or ends, with no
>   file links and no self-reload; `dashboard --serve` serves the live dashboard with every file
>   and conversation, and `dashboard --export` writes a self-contained full dashboard.
> - New commands `init` and `check`; new `run`/`orchestrate` option `--speckit-feature`; targets
>   and requirements default to the project configuration.

The entry point is `bin/devloops`, and every loop and the orchestrator run through it
[RC, research R-1/R-16]. Each command prints a human-readable summary. With `--json`, it prints a
single JSON status object instead (the same shape as `status --json`).

## Common options

| Option | Meaning |
|--------|---------|
| `--workspace <name\|path>` | **Required.** The workspace name (under `workspaces/`) or a path. It is created on the first `run` (D-3) |
| `--config <file>` | An optional config file, merged over the defaults. See [config.schema.json](./config.schema.json) |
| `--json` | Machine-readable output |

## Commands

### `run <backend-dev|frontend-dev>`

Starts or resumes one loop directly (FR-039, FR-040).

| Option | Meaning | Rule |
|--------|---------|------|
| `--requirements <file>` | A PRD Markdown file, or a standalone story file | Required on the first run; if given later, it must match the recorded fingerprint (D-8) |
| `--story-id <id>` | Selects one story within `--requirements` (D-6 form b) | Must occur in the file, or the run stops with an input error (FR-010b) |
| `--story-file` | Marks `--requirements` as a standalone story (D-6 form a) | Mutually exclusive with `--story-id` |
| `--target <dir>` | This loop's directory for application code (D-7, FR-035a) | Required on the first run; created if missing; must be writable, outside `loops/`, and not the other loop's target |
| `--api-spec <file>` | An OpenAPI JSON document | **Required for `frontend-dev`** (FR-011) |
| `--max-trials <n>` | Overrides `max_trials` (FR-006) | Integer ≥ 1 |
| `--review-plan` | Sets `questions: ask`: pause after each plan for review (FR-053, D-13) | Also allowed on a later start; recorded as a `config-override`. Mutually exclusive with `--accept-suggested` |
| `--accept-suggested` | Sets `questions: accept-suggested`, the default (FR-055c) | Also allowed on a later start; recorded as a `config-override` |

**Behavior** (see the iteration model in [plan.md](../plan.md#iteration-model)):
- A run exits when it reaches `awaiting-approval`, a terminal state, `stopped-on-service-error`, or
  a hard limit. By default the plan is approved automatically, so `awaiting-approval` is reached
  only when plans are reviewed or a question has no suggested answer.
- At `awaiting-approval`, when standard input and output are a terminal and `--json` is not given,
  it asks `[a]pprove [e]dit answers [r]eplan [q]uit` (FR-056a): `a` and `r` act as `approve` and
  `replan` (continuing), `e` opens `open-questions.md` in `$VISUAL` or `$EDITOR`, `q` (or end of
  input) exits 10.
- Before planning, and again on every start, it checks the required tools (FR-013b) and, for
  frontend-dev, that `--api-spec` parses as OpenAPI 3 (FR-013a).
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

### `approve <loop>`

Accepts the stored plan together with any answers written in `outputs/open-questions.md`, and moves
the run to `implementing`. It is allowed only in `awaiting-approval`. It records `Approval`
(FR-053, FR-054). An empty answer under a suggested answer accepts the suggestion: it is copied
into the answer and marked `**Answer source:**` before the file is fingerprinted, and its ID is
listed in `approval.accepted_suggestions` (FR-053a). It then continues the run (FR-056a).

### `replan <loop>`

Re-runs planning with the answers in `outputs/open-questions.md`. This consumes a planning trial
(research R-6). It then continues the run: under `questions: ask` it pauses again at
`awaiting-approval`; under `accept-suggested` the new plan is approved and implemented. With
`--no-continue` it always pauses at the new plan.

### Continuing after a decision (`approve`, `replan`, `retry`)

These commands take `--no-continue`, `--review-plan` / `--accept-suggested` (which apply to the
continued run, so they are refused with `--no-continue`), and `--force-unlock`.
Unless `--no-continue` is given, after recording the decision they continue as `run` does, and exit
with the run's code (FR-056a):

- for a single loop, under the same lock as the decision;
- in a workspace with `orchestrator/state.json`, through the orchestrator, from the decided loop
  on, so a completed backend goes on to the frontend. `--json` then prints the `orchestrate`
  object with `decision: {command, loop}`.

A refused decision runs nothing and leaves `run.json` and the orchestrator's `state.json`
unchanged: a usage error (exit 2), another driver's lock (40), or, when it would continue, a
missing tool (30, checked before the decision is recorded).

### `status [<loop>]`

Prints the run status, the current or next milestone, trials used out of the limit, the last
failure, the UI URL (frontend), and the OpenAPI artifact (backend). It is read-only.

### `orchestrate`

Runs `backend-dev`, then `frontend-dev`, in the same workspace (FR-040–042, FR-052, FR-056;
research R-15).

| Option | Meaning |
|--------|---------|
| `--requirements`, `--story-id`, `--story-file` | Passed to both loops |
| `--target-root <dir>` | The default targets are `<dir>/backend` and `<dir>/frontend` [RC] |
| `--backend-target`, `--frontend-target` | Override the per-loop targets |
| `--review-plan`, `--accept-suggested` | Passed to both loops and recorded in `orchestrator/state.json` (`questions`), so later calls keep them (FR-055c, D-13) |

- Before running either loop it checks the required tools of every loop with work left; a missing
  one exits 30 (`missing-tool`) with nothing recorded (FR-056b).
- The orchestrator stops and uses the same exit codes as `run`: 10 if a loop is awaiting
  approval, 20 or 30 if a loop stopped, 50 on a service error.
- Running it again resumes. It never starts `frontend-dev` unless `backend-dev` is `completed`.

### `retry <loop> --milestone <id> [--reason "<text>"] [--trials <n>]` (FR-063)

Moves a `stopped-on-failure` run back to `implementing`, granting `n` more trials (default:
`max_trials`) to the failed milestone, then continues the run (FR-056a). The grant is recorded in
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
trials, the questions and answers, the orchestrator handoff, and every Claude call and event.
`run`, `approve`, `replan`, `retry`, and `orchestrate` rewrite it after they finish; a failure to
write it prints a warning and never changes their exit code.

## Optional Claude Code skills [RD + RC, research R-16]

The skills `.claude/skills/loops-backend-dev`, `loops-frontend-dev`, and `loops-orchestrate` each
run exactly one CLI command through Bash and report the result. They contain no loop logic.
