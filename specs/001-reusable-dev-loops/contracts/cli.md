# Contract: `devloops` CLI

> **Changed by 002** ([specs/002-devloops-init/contracts/cli.md](../../002-devloops-init/contracts/cli.md)):
> - `--workspace` is optional: the default is the project configuration's `workspace`, and a bare
>   name resolves under its `workspaces_dir`. Commands find the project from the current folder.
> - `dashboard` writes a new **full** dashboard, then refreshes the lightweight one;
>   `dashboard --light` keeps the behavior described here.
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

**Behavior** (see the iteration model in [plan.md](../plan.md#iteration-model)):
- A run exits when it reaches `awaiting-approval`, a terminal state, `stopped-on-service-error`, or
  a hard limit.
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
(FR-053, FR-054). It does not start implementation; call `run` afterwards.

### `replan <loop>`

Re-runs planning with the answers in `outputs/open-questions.md`, then pauses again at
`awaiting-approval`. This consumes a planning trial (research R-6).

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

- The orchestrator stops and uses the same exit codes as `run`: 10 if a loop is awaiting
  approval, 20 or 30 if a loop stopped, 50 on a service error.
- Running it again resumes. It never starts `frontend-dev` unless `backend-dev` is `completed`.

### `retry <loop> --milestone <id> --reason "<text>" [--trials <n>]` (FR-063)

Moves a `stopped-on-failure` run back to `implementing`, granting `n` more trials (default:
`max_trials`) to the failed milestone. The grant is recorded in `run.json` `grants[]` and as a
`retry-granted` event, with its time and reason. The reason text is passed to later fix prompts as
developer guidance.

- For a `needs-input` stop (FR-055a), answer the questions in `outputs/open-questions.md` first.
  Their fingerprint is recorded with the grant.
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
