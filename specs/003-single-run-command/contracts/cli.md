# Contract: `devloops` CLI changes (003)

This contract replaces the parts of `specs/001-reusable-dev-loops/contracts/cli.md` and
`specs/002-devloops-init/contracts/cli.md` named below. Those files are edited in place to match,
with a note pointing here. Everything not named here is unchanged.

## Removed

| Removed | Now |
|---------|-----|
| `devloops run <backend-dev\|frontend-dev>` | `devloops run` (no loop name); a loop name is a usage error (exit 2) |
| `devloops orchestrate` | `devloops run`; `orchestrate` is an unknown command (exit 2) |
| `run --target <dir>` | `--backend-target` / `--frontend-target`, or `targets` in `devloops.json` |
| `run --api-spec <file>` | None for now: frontend-dev gets the backend's contract from the run's handoff |
| `approve <loop>`, `replan <loop>`, `retry <loop> …` | The same commands without the loop |

## `devloops run`

Starts or resumes the workspace's run. It runs each included loop in order (backend-dev, then
frontend-dev), handing the backend's verified OpenAPI document and runtime to the frontend.

| Option | Meaning |
|--------|---------|
| `--requirements <file>` / `--speckit-feature [dir]` | As before; passed to every loop. Default: the workspace's recorded requirements, then `requirements` in `devloops.json` |
| `--story-id <id>` / `--story-file` | As before |
| `--target-root <dir>` | Places the loops the project includes at `<dir>/backend` and `<dir>/frontend`. It never includes a loop the project leaves out |
| `--backend-target <dir>`, `--frontend-target <dir>` | That loop's target for this workspace. Includes the loop even when the project sets it to `null`. For a loop already recorded in the workspace: the same folder is accepted; a different one is a usage error (exit 2) |
| `--max-trials <n>` | Overrides `max_trials` for every loop this command starts or resumes (recorded as a `config-override`); those loops keep it for later commands |
| `--review-plan` / `--accept-suggested` | As before; recorded in `run/state.json` (`questions`) |
| `--quiet` / `--verbose` | As before |
| `--force-unlock` | As before |
| common: `--workspace`, `--config`, `--json` | As before |

**Loop selection** (data-model.md): the workspace's recorded targets, then the flags, then
`targets` in `devloops.json`. `null` or missing in `devloops.json` means the project does not use
that loop.

**Before anything is written**:
- The selection is checked. Nothing is created: no workspace, no lock, no `run/state.json`.
  - **No loop:** exit **30**; `status_reason.code` `no-loop`.
    Message: `no loop to run: set targets.backend-dev or targets.frontend-dev in
    .devloops/devloops.json (or run devloops init)`.
  - **frontend-dev without backend-dev:** exit **30**; `status_reason.code`
    `frontend-needs-backend`. Message: `frontend-dev needs backend-dev in the same run: set
    targets.backend-dev in .devloops/devloops.json (frontend-only runs are not supported yet)`.
    When the frontend came from `--frontend-target`: `frontend-dev needs backend-dev in the same
    run: set targets.backend-dev in .devloops/devloops.json or pass --backend-target
    (frontend-only runs are not supported yet)`.
  - `--json` prints only `{"exit_code": 30, "status_reason": {"code", "message"}}`.
- Then, as before, the tools of every included loop with work left are checked (`missing-tool`,
  exit 30, nothing recorded).

**Behavior**:
- A completed loop is not run again.
- frontend-dev starts only after backend-dev completes.
- The run stops at a plan pause (10), a stopped loop (20 / 30), or a service error (50).
- The exit codes are unchanged (0, 10, 20, 30, 40, 50, 2).
- **Backend only:** the run completes when backend-dev completes. The handoff is still recorded.
- **A loop added to the project later:** the next `devloops run` runs it, so a completed run goes
  back to `running`.
- **Terminal review:** at a plan pause, a terminal still offers `[a]pprove [e]dit answers [r]eplan
  [q]uit`. `q` prints `devloops approve` (no loop) as the command to continue.

- **A workspace from an older devloops** (with an `orchestrator/` folder): the folder is ignored.
  `run/` is created, completed loops are skipped, and the run continues.
- **Shown loops:** output, `status`, and dashboards show only the loops the run includes.

**Output** (text):

```text
run: paused
backend-dev: awaiting-approval …
frontend-dev: not-started …
dashboard: …/dashboard.html
files and conversations: devloops dashboard --serve
```

**`--json`**: `{workspace, run, loops, exit_code, message, dashboard[, full_dashboard]}`, where
`run` is the content of `run/state.json` (formerly the `orchestrator` key).

## `devloops approve`, `devloops replan`

No positional argument. Each applies to the loop in `awaiting-approval`.

- If no loop is in that status: usage error (exit 2) `nothing awaits approval (run: <status>)`.
  Nothing changes.
- Otherwise, as before: the decision is recorded, then the whole run continues.
- `--no-continue` only records the decision; the next `devloops run` continues.
- `--json` adds `decision: {command, loop}` to the run object.

## `devloops retry --milestone <id> [--reason "<text>"] [--trials <n>]`

No positional argument. It applies to the loop in `stopped-on-failure`.

- If no loop is in that status: usage error (exit 2) `no loop is stopped on failure (run:
  <status>)`.
- The milestone is checked against that loop only, as before.
- Otherwise unchanged: a grant, `developer_guidance` from `--reason`, then the run continues.

## `devloops status [<loop>]`

The optional loop name is kept.
- **Without a loop:** it shows only the loops the run includes, the same selection as `devloops
  run` with no flags (FR-016b).
- **Run status:** when `run/state.json` exists, the text output starts with `run: <status>`, and
  `--json` adds the key `run` (its content).
- **With a loop:** the output is unchanged.

## `devloops init`: new options

| Option | Meaning |
|--------|---------|
| `--no-backend` | Writes `targets.backend-dev: null`. Mutually exclusive with `--backend-target` (exit 2) |
| `--no-frontend` | Writes `targets.frontend-dev: null`. Mutually exclusive with `--frontend-target` (exit 2) |

- **Target prompts:** each prompt accepts `none` (case-insensitive) for no target. A folder named
  `none` is entered as `./none`.
- **Both none:** in a terminal, init says `a project needs at least one loop` and asks again. With
  flags or `--no-prompt`, it is a usage error (exit 2) and nothing is written.
- **Next step:** the line now reads ``Next: `devloops check`, then `devloops run` ``.

## `devloops check`: changes

- **Which loops:** only the loops the project includes are checked, using the selection rule with
  no flags and the project's default workspace when it exists (a loop recorded there stays
  checked). Outside a project, both loops are checked.
- **No loop:** a project that includes no loop gets a `missing` item `loops` (`the project
  includes no loop`; fix: set `targets.backend-dev` or `targets.frontend-dev` in
  `.devloops/devloops.json`), so `check` exits 30, as `devloops run` would.
- **Status `unused`:** an item needed only by loops the project does not include gets status
  `unused`, with detail `not used by this project (<loop>)` and no fix. It never makes the check
  fail.
- **`--json`:** adds `"loops": [...]`, the included loops.

```text
devloops check            # backend-only project
  ready    python          3.14.7
  ready    claude          2.1.283
  ready    curl            8.10.1
  unused   playwright-mcp  not used by this project (frontend-dev)
  unused   browser         not used by this project (frontend-dev)
  ready    git             2.51.0
```

## Messages that name a command

Every hint names the commands without a loop:
- `devloops run`;
- `devloops approve`;
- `devloops replan`;
- `devloops retry --milestone <id>`.

A `--workspace <name>` already in a hint is kept.
