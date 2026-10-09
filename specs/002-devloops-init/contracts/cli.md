# Contract: `devloops` CLI changes (002)

This contract **extends** [001's CLI contract](../../001-reusable-dev-loops/contracts/cli.md).
Everything not mentioned here is unchanged: run statuses, exit codes 0/10/20/30/40/50/2, and the
`--json` status objects.

The command is `devloops` when installed, and `bin/devloops` from a source checkout. The two behave
the same (FR-002).

## Project discovery (all commands except `init` and `check`)

- **Finding the project**: devloops searches from the current directory upward for
  `.devloops/devloops.json` (research P-3). If none is found, it exits 2 with
  `no devloops project found from <cwd>; run "devloops init"`.
- **Override**: `DEVLOOPS_PROJECT=<dir>` names the project root explicitly, for tests and scripts.
- **Version warning**: if the running version differs from `.devloops/manifest.json`, devloops
  prints `devloops: warning: this project was set up with devloops <a>; running <b>. Run "devloops
  init --upgrade".` on stderr. With `--json`, the same text is added to a `warnings` array
  (FR-029).

## Common options: changes

| Option | Change |
|--------|--------|
| `--workspace <name\|path>` | **No longer required.** Default: the project configuration's `workspace` (`init` writes `main`). A bare name resolves under `workspaces_dir` |
| `--config <file>` | Unchanged; it is now layer 4 of 5 (research P-4) |

## `run`: new and changed options

> Revised by specs/003-single-run-command
> ([contracts/cli.md](../../003-single-run-command/contracts/cli.md)): `devloops run` takes no loop
> name and runs every loop the project includes; `orchestrate`, `run <loop>`, and `run --target`
> were removed.

| Option | Meaning |
|--------|---------|
| `--requirements <file>` | Unchanged. Default: the project configuration's `requirements` |
| `--speckit-feature [DIR]` | A spec-kit feature folder as input. With no `DIR`, the **active** feature from `.specify/feature.json`. Mutually exclusive with `--requirements` and `--story-file` (FR-023, FR-024) |
| `--story-id <id>` | Unchanged for Markdown requirements. With a spec-kit input, `US<n>` selects `User Story <n>` (FR-025) |
| `--backend-target`, `--frontend-target` | Default: `targets.*` from the project configuration (`null` or missing: the project does not use that loop) |
| `--target-root <dir>` | Places the loops the project includes at `<dir>/backend` and `<dir>/frontend` |

Missing spec-kit inputs (both are input errors, exit 30):
- a feature folder without `spec.md` stops the run with `missing-input`;
- a `US<n>` with no matching heading stops it with `story-not-found` (FR-026).

**Full dashboard after a final status**: only when `dashboard.full_on_stop` is set (in the
configuration files as they are when the command ends; it is not frozen and never drift), and `run`,
`approve`, `replan`, or `retry` ends in `completed`, `stopped-on-failure`, `stopped-on-input-error`,
or `stopped-on-service-error`, devloops writes a full dashboard (FR-039) and prints `full dashboard:
<path> (<size>)`. `--json` adds `full_dashboard: {path, bytes}`. A write failure prints `devloops:
warning: could not write the full dashboard: …` and leaves the exit code unchanged. The summary page
`dashboard.html` is written at the end, unless `dashboard.light` is `false` (FR-038), and the
summary ends with where files and conversations are: `files and conversations: <url> (dashboard
server running)` while `devloops dashboard --serve` runs for the project, else `files and
conversations: devloops dashboard --serve [--workspace <ws>]`.

**Progress** (FR-039a): `run`, `approve`, `replan`, and `retry` take `--quiet` or
`--verbose`. Before running they print the same `files and conversations: …` line and the path of
each loop's `state/run.log`; then, on stderr, one line per event and per Claude call:

```
HH:MM:SS <loop> [<milestone> #<trial>]  <message>
```

While a call runs, a terminal shows a status line redrawn in place (`<step> · <elapsed> · <n> tool
call(s) · last: <tool>`); without a terminal, a `still <step> ...` line is printed every minute.
`--verbose` adds a line per tool (`  Bash: pytest -q`, `  Edit app/models.py`); `--quiet`, and
`--json` without `--verbose`, print none of this. Colors only in a terminal and without
`NO_COLOR`. Every line, tools included, is appended to `<workspace>/<loop>/state/run.log`.

## `init [DIR]` (new)

Sets up `DIR` (default: the current directory) as a devloops project (FR-003 to FR-007b). The
files are listed in [project-layout.md](./project-layout.md).

| Option | Meaning |
|--------|---------|
| `--backend-target <dir>` / `--frontend-target <dir>` | Written to `targets` (relative to the project root when inside it) |
| `--no-backend` / `--no-frontend` | Write `targets.backend-dev: null` / `targets.frontend-dev: null` (the project does not use that loop). Each is mutually exclusive with its target flag (exit 2); both together are a usage error (exit 2, `a project needs at least one loop`). Added by specs/003-single-run-command |
| `--requirements <file>` | Written as `requirements.path` |
| `--speckit-feature [DIR]` | Written as `requirements.speckit_feature` (`active` with no value) |
| `--no-prompt` | Never ask questions. Implied when stdin or stdout is not a terminal |
| `--no-models` | Write `config: {}`, with no model choice (FR-007c) |
| `--track-workspaces` | Do not add the workspaces ignore rule |
| `--track-dashboards` | Do not add the full-dashboards ignore rule |
| `--allow-skills` | Add the skills' permission rule to `.claude/settings.json` (also on an initialized project; FR-022b) |
| `--upgrade` | Upgrade an initialized project (FR-027 to FR-029) |
| `--restore` | With `--upgrade`, re-create installed files that were deleted |
| `--json` | Print the result as JSON |

**Interactive questions**: asked only on a terminal and without `--no-prompt`, research P-13.
- *Backend target ('none': not used)* [`backend`]
- *Frontend target ('none': not used)* [`frontend`]
- *Requirements* [`active spec-kit feature (<dir>)` or blank]
- *Recommended models (opus to plan and write checks, sonnet to build; y/n)* [`y`], unless
  `--no-models` (FR-007c)

An invalid answer is explained and the question is asked again. `none` (case-insensitive) means
the project does not use that loop; a folder named `none` is entered as `./none`. Answering `none`
to both says `a project needs at least one loop` and asks again. *(Revised by
specs/003-single-run-command.)*

**Results**:

| Case | Exit | Output |
|------|------|--------|
| Fresh project | 0 | Each created or changed file; the permission rule and how to add it; the next command: ``Next: `devloops check`, then `devloops run`.`` (revised by specs/003-single-run-command) |
| Already initialized, no `--upgrade` / `--allow-skills` | 0 | `already initialized (devloops <v>); use "devloops init --upgrade" to update`. Nothing is written |
| Conflicting existing files | 30 (`init-conflict`) | Every conflicting path. Nothing is written |
| Invalid flag value (target overlaps `.devloops/`, the kit, or the other target) | 30 (`target-unwritable`) | The reason. Nothing is written |
| `--upgrade` | 0 | The files updated, kept (with the `.devloops-new` path), reported as deleted, added, and removed; when neither configuration file sets `model` or `models`, a note with the recommended block to add (nothing is written) |
| `--upgrade` with a newer manifest version | 30 (`downgrade-refused`) | Both versions. Nothing is written |
| `--allow-skills` with unreadable settings | 30 (`settings-unreadable`) | The problem and the rule to add by hand. The settings file is untouched |

`init --json` prints:

```json
{"project": "<abs>", "created": [], "changed": [], "kept": [{"path": "", "new_version": ""}],
 "deleted": [], "removed": [], "conflicts": [], "permission_rule": "Bash(devloops *)",
 "next": "devloops check", "exit_code": 0, "message": ""}
```

## `check` (new)

Reports whether the environment is ready (FR-018, FR-019; research P-14). It works inside or
outside a project.

```text
devloops check
  ready    python          3.14.7
  ready    claude          2.1.283
  ready    curl            8.10.1
  ready    playwright-mcp  npx
  missing  browser         no Chrome-channel browser found
           fix: npx playwright install chrome, or set playwright.executable_path
  warning  display         visible browser configured but no display
           fix: set playwright.headless to true, or run under xvfb-run
```

`--json` prints `{"ready": bool, "project": "<abs>|null", "loops": [...], "items": [{"name",
"status", "detail", "fix", "needed_for": ["backend-dev"|"frontend-dev"|"all"]}]}`.

The exit code is **0** when no needed item is `missing`, otherwise **30**. Warnings never change
the exit code.

> Revised by specs/003-single-run-command:
> - **Which loops:** inside a project, only the loops the project includes are checked (the
>   `devloops run` selection with no flags, including the loops recorded in the default workspace
>   when it exists); `loops` lists them. Outside a project, both loops are checked.
> - **`unused`:** an item needed only by loops the project does not include has status `unused`,
>   detail `not used by this project (<loop>)`, and no fix. It never makes the check fail.
> - **No loop:** a project that includes no loop gets a `missing` item `loops` (`the project
>   includes no loop`; fix: set `targets.backend-dev` or `targets.frontend-dev` in
>   `.devloops/devloops.json`), so `check` exits 30.

```text
devloops check            # backend-only project
  ready    python          3.14.7
  ready    claude          2.1.283
  ready    curl            8.10.1
  unused   playwright-mcp  not used by this project (frontend-dev)
  unused   browser         not used by this project (frontend-dev)
```

## `dashboard`: changed

| Form | Effect |
|------|--------|
| `devloops dashboard` | Writes the summary page `<workspace>/dashboard.html` (FR-038), then prints `dashboard: <path>` and the `files and conversations: …` line. `--json`: `{"workspace", "dashboard", "serving": <url> \| null}`. `--light` is accepted and means the same |
| `devloops dashboard --export [--out <file>]` | Writes a **new full dashboard** ([full-dashboard.md](./full-dashboard.md)) to the dashboards folder, or to `<file>` (replaced if it exists). Then refreshes the summary page (unless `dashboard.light` is `false`), which links it. Prints `full dashboard: <path> (<size>)`, the five largest embedded files, and the files too large to embed. `--json`: `{"workspace", "dashboard", "full_dashboard": {"path", "bytes", "largest": [{"path", "bytes"}], "unavailable", "not_embedded": [{"path", "bytes"}]}}`. Exit 1 when it cannot be written |
| `devloops dashboard --serve [--host <addr>] [--port <n>] [--open] [--token <t> \| --no-token]` | Serves the live dashboard ([full-dashboard.md](./full-dashboard.md#live-dashboard)) of every workspace of the project until `Ctrl C` or SIGTERM, then exits 0. Prints `serving the dashboards of <project> (read-only; Ctrl+C to stop):` and one URL per address; `--json` prints `{"url", "urls", "host", "port", "pid", "token"}` on one line instead. Already running for the project: prints `already serving: <url> (pid <pid>); …` (`--json`: `{"already_serving": true, "url", "pid"}`) and exits 0. A port that cannot be bound: exit 2 |

`--serve` options:

| Option | Default | Meaning |
|--------|---------|---------|
| `--host` | `127.0.0.1` | Address to listen on; `0.0.0.0` or `::` for every interface. Beyond loopback a warning goes to stderr |
| `--port` | `8765`, else the next free port up to `8784` | `0`: any free port. Given explicitly, only that port is tried |
| `--open` | off | Open the first URL in the default browser |
| `--token` | random when `--host` is not loopback | Require this token (also on loopback) |
| `--no-token` | off | Require no token |

`--host`, `--port`, `--open`, `--token`, and `--no-token` without `--serve`, `--out` without
`--export`, `--serve` with `--export`, and `--token` with `--no-token` are usage errors (exit 2).
Without `--workspace`, `--serve` opens on the default workspace, or on the first one when the
default does not exist yet.

## `status`: additions

`status --json` adds:

| Key | Content |
|-----|---------|
| `config_drift` | Dotted keys whose effective value would differ if the configuration were resolved now (FR-015) |
| `prompt_drift` | Prompt parts whose source or fingerprint changed since the configuration was frozen (FR-032) |
| `full_dashboards` | `{count, bytes, latest}` |
| `warnings` | e.g. the version mismatch |

The text output shows each addition as one line, only when it is not empty.
