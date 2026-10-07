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

## `run` and `orchestrate`: new and changed options

| Option | Meaning |
|--------|---------|
| `--requirements <file>` | Unchanged. Default: the project configuration's `requirements` |
| `--speckit-feature [DIR]` | A spec-kit feature folder as input. With no `DIR`, the **active** feature from `.specify/feature.json`. Mutually exclusive with `--requirements` and `--story-file` (FR-023, FR-024) |
| `--story-id <id>` | Unchanged for Markdown requirements. With a spec-kit input, `US<n>` selects `User Story <n>` (FR-025) |
| `--target <dir>` (`run`) | Default: `targets.<loop>` from the project configuration |
| `--backend-target`, `--frontend-target` (`orchestrate`) | Default: `targets.*` from the project configuration |

Missing spec-kit inputs (both are input errors, exit 30):
- a feature folder without `spec.md` stops the run with `missing-input`;
- a `US<n>` with no matching heading stops it with `story-not-found` (FR-026).

**Full dashboard after a final status**: only when `dashboard.full_on_stop` is set (in the
configuration files as they are when the command ends; it is not frozen and never drift), and `run`, `approve`, `replan`, `retry`, or `orchestrate` ends in
`completed`, `stopped-on-failure`, `stopped-on-input-error`, or `stopped-on-service-error`,
devloops writes a full dashboard (FR-039) and prints `full dashboard: <path> (<size>)`. `--json`
adds `full_dashboard: {path, bytes}`. A write failure prints `devloops: warning: could not write
the full dashboard: …` and leaves the exit code unchanged. Otherwise the summary ends with
`full dashboard (files and conversations): devloops dashboard [--workspace <ws>]`.

**Progress** (FR-039a): `run`, `orchestrate`, `approve`, `replan`, and `retry` take `--quiet` or
`--verbose`. Before running they print the paths of `dashboard.html` and `state/run.log` and the
`devloops dashboard` command; then, on stderr, one line per event and per Claude call:

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
| `--requirements <file>` | Written as `requirements.path` |
| `--speckit-feature [DIR]` | Written as `requirements.speckit_feature` (`active` with no value) |
| `--no-prompt` | Never ask questions. Implied when stdin or stdout is not a terminal |
| `--track-workspaces` | Do not add the workspaces ignore rule |
| `--track-dashboards` | Do not add the full-dashboards ignore rule |
| `--allow-skills` | Add the skills' permission rule to `.claude/settings.json` (also on an initialized project; FR-022b) |
| `--upgrade` | Upgrade an initialized project (FR-027 to FR-029) |
| `--restore` | With `--upgrade`, re-create installed files that were deleted |
| `--json` | Print the result as JSON |

**Interactive questions**: asked only on a terminal and without `--no-prompt`, research P-13.
- *Backend target* [`backend`]
- *Frontend target* [`frontend`]
- *Requirements* [`active spec-kit feature (<dir>)` or blank]

An invalid answer is explained and the question is asked again.

**Results**:

| Case | Exit | Output |
|------|------|--------|
| Fresh project | 0 | Each created or changed file; the permission rule and how to add it; the next command (`devloops check`, then `devloops orchestrate` or `devloops run …`) |
| Already initialized, no `--upgrade` / `--allow-skills` | 0 | `already initialized (devloops <v>); use "devloops init --upgrade" to update`. Nothing is written |
| Conflicting existing files | 30 (`init-conflict`) | Every conflicting path. Nothing is written |
| Invalid flag value (target overlaps `.devloops/`, the kit, or the other target) | 30 (`target-unwritable`) | The reason. Nothing is written |
| `--upgrade` | 0 | The files updated, kept (with the `.devloops-new` path), reported as deleted, added, and removed |
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

`--json` prints `{"ready": bool, "project": "<abs>|null", "items": [{"name", "status", "detail",
"fix", "needed_for": ["backend-dev"|"frontend-dev"|"all"]}]}`.

The exit code is **0** when no needed item is `missing`, otherwise **30**. Warnings never change
the exit code.

## `dashboard`: changed

| Form | Effect |
|------|--------|
| `devloops dashboard` | Writes a **new full dashboard** ([full-dashboard.md](./full-dashboard.md)), then refreshes the lightweight one. Prints `full dashboard: <path> (<size>)`, the five largest embedded files, and the files too large to embed. `--json`: `{"workspace", "dashboard", "full_dashboard": {"path", "bytes", "largest": [{"path", "bytes"}], "unavailable", "not_embedded": [{"path", "bytes"}]}}` |
| `devloops dashboard --light` | 001 behavior: refreshes `<workspace>/dashboard.html` only |

## `status`: additions

`status --json` adds:

| Key | Content |
|-----|---------|
| `config_drift` | Dotted keys whose effective value would differ if the configuration were resolved now (FR-015) |
| `prompt_drift` | Prompt parts whose source or fingerprint changed since the configuration was frozen (FR-032) |
| `full_dashboards` | `{count, bytes, latest}` |
| `warnings` | e.g. the version mismatch |

The text output shows each addition as one line, only when it is not empty.
