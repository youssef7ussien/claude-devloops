---
title: Commands
description: >-
  Every devloops command and option, as devloops itself defines them.
generated: true
---

# Commands

!!! note "Generated page"
    This page is generated from devloops' code; do not edit it. Change the code (or
    `tools/docs/descriptions.json`), then run `python3 tools/docs/gen_reference.py`.

Every command is `devloops <command> [options]`. `devloops --help` lists the commands and `devloops <command> --help` a command's options.

## Global options {#global-options}

| Option | Meaning |
|---|---|
| <span id="devloops--help"></span>`--help` | Show this help message and exit. |
| <span id="devloops--version"></span>`--version` | Show program's version number and exit. |

## `run` {#run}

Start or resume the run: backend-dev, then frontend-dev, as the project configures.

```text
devloops run [--workspace WORKSPACE] [--config CONFIG] [--json]
             [--requirements REQUIREMENTS | --speckit-feature [DIR]]
             [--story-id STORY_ID | --story-file] [--target-root TARGET_ROOT]
             [--backend-target BACKEND_TARGET] [--frontend-target FRONTEND_TARGET]
             [--max-trials MAX_TRIALS] [--review-plan | --accept-suggested] [--quiet | --verbose]
             [--force-unlock]
```

| Option | Default | Meaning |
|---|---|---|
| <span id="run--workspace"></span>`--workspace WORKSPACE` |  | Workspace name (under the project's workspaces_dir) or path; created on the first run (default: the project's `workspace`, else main). |
| <span id="run--config"></span>`--config CONFIG` |  | Config file merged over the defaults. |
| <span id="run--json"></span>`--json` |  | Print one JSON status object. |
| <span id="run--requirements"></span>`--requirements REQUIREMENTS` |  | PRD or story Markdown file, passed to every loop (default: the recorded one, then the project's). |
| <span id="run--speckit-feature"></span>`--speckit-feature [DIR]` |  | A spec-kit feature folder as the requirements (no value: the active feature in .specify/feature.json). |
| <span id="run--story-id"></span>`--story-id STORY_ID` |  | Implement only this story of --requirements (a PRD). |
| <span id="run--story-file"></span>`--story-file` |  | --requirements is a standalone story file. |
| <span id="run--target-root"></span>`--target-root TARGET_ROOT` |  | Place the project's loops at <dir>/backend and <dir>/frontend (first run). |
| <span id="run--backend-target"></span>`--backend-target BACKEND_TARGET` |  | backend-dev's target (overrides --target-root). |
| <span id="run--frontend-target"></span>`--frontend-target FRONTEND_TARGET` |  | frontend-dev's target (overrides --target-root). |
| <span id="run--max-trials"></span>`--max-trials MAX_TRIALS` |  | Override max_trials for every loop this command runs. |
| <span id="run--review-plan"></span>`--review-plan` |  | Pause after each plan for review, and stop on open questions (sets questions: ask). |
| <span id="run--accept-suggested"></span>`--accept-suggested` |  | Approve plans and accept Claude's suggested answers without pausing (questions: accept-suggested, the default; review them afterwards). |
| <span id="run--quiet"></span>`--quiet` |  | Print no progress lines, only the final summary. |
| <span id="run--verbose"></span>`--verbose` |  | Also print each tool Claude uses. |
| <span id="run--force-unlock"></span>`--force-unlock` |  | Clear a stale lock. |

Options that cannot be used together:

- `--requirements` or `--speckit-feature`
- `--story-id` or `--story-file`
- `--review-plan` or `--accept-suggested`
- `--quiet` or `--verbose`

## `approve` {#approve}

Accept the stored plan and the answers, then continue.

```text
devloops approve [--workspace WORKSPACE] [--config CONFIG] [--json] [--no-continue]
                 [--review-plan | --accept-suggested] [--quiet | --verbose] [--force-unlock]
```

| Option | Default | Meaning |
|---|---|---|
| <span id="approve--workspace"></span>`--workspace WORKSPACE` |  | Workspace name (under the project's workspaces_dir) or path; created on the first run (default: the project's `workspace`, else main). |
| <span id="approve--config"></span>`--config CONFIG` |  | Config file merged over the defaults. |
| <span id="approve--json"></span>`--json` |  | Print one JSON status object. |
| <span id="approve--no-continue"></span>`--no-continue` |  | Only record the decision; run nothing (the run continues on the next `devloops run`). |
| <span id="approve--review-plan"></span>`--review-plan` |  | Pause after each plan for review, and stop on open questions (sets questions: ask). |
| <span id="approve--accept-suggested"></span>`--accept-suggested` |  | Approve plans and accept Claude's suggested answers without pausing (questions: accept-suggested, the default; review them afterwards). |
| <span id="approve--quiet"></span>`--quiet` |  | Print no progress lines, only the final summary. |
| <span id="approve--verbose"></span>`--verbose` |  | Also print each tool Claude uses. |
| <span id="approve--force-unlock"></span>`--force-unlock` |  | Clear a stale lock. |

Options that cannot be used together:

- `--review-plan` or `--accept-suggested`
- `--quiet` or `--verbose`

## `replan` {#replan}

Plan again with the answers, then continue.

```text
devloops replan [--workspace WORKSPACE] [--config CONFIG] [--json] [--no-continue]
                [--review-plan | --accept-suggested] [--quiet | --verbose] [--force-unlock]
```

| Option | Default | Meaning |
|---|---|---|
| <span id="replan--workspace"></span>`--workspace WORKSPACE` |  | Workspace name (under the project's workspaces_dir) or path; created on the first run (default: the project's `workspace`, else main). |
| <span id="replan--config"></span>`--config CONFIG` |  | Config file merged over the defaults. |
| <span id="replan--json"></span>`--json` |  | Print one JSON status object. |
| <span id="replan--no-continue"></span>`--no-continue` |  | Only record the decision; run nothing (the run continues on the next `devloops run`). |
| <span id="replan--review-plan"></span>`--review-plan` |  | Pause after each plan for review, and stop on open questions (sets questions: ask). |
| <span id="replan--accept-suggested"></span>`--accept-suggested` |  | Approve plans and accept Claude's suggested answers without pausing (questions: accept-suggested, the default; review them afterwards). |
| <span id="replan--quiet"></span>`--quiet` |  | Print no progress lines, only the final summary. |
| <span id="replan--verbose"></span>`--verbose` |  | Also print each tool Claude uses. |
| <span id="replan--force-unlock"></span>`--force-unlock` |  | Clear a stale lock. |

Options that cannot be used together:

- `--review-plan` or `--accept-suggested`
- `--quiet` or `--verbose`

## `retry` {#retry}

Grant a failed milestone more trials, then continue (FR-063).

```text
devloops retry [--workspace WORKSPACE] [--config CONFIG] [--json] --milestone MILESTONE
               [--reason REASON] [--trials TRIALS] [--no-continue]
               [--review-plan | --accept-suggested] [--quiet | --verbose] [--force-unlock]
```

| Option | Default | Meaning |
|---|---|---|
| <span id="retry--workspace"></span>`--workspace WORKSPACE` |  | Workspace name (under the project's workspaces_dir) or path; created on the first run (default: the project's `workspace`, else main). |
| <span id="retry--config"></span>`--config CONFIG` |  | Config file merged over the defaults. |
| <span id="retry--json"></span>`--json` |  | Print one JSON status object. |
| <span id="retry--milestone"></span>`--milestone MILESTONE` |  | required: the failed milestone, e.g. M01. |
| <span id="retry--reason"></span>`--reason REASON` |  | Guidance for the next fix trial; recorded with the grant. |
| <span id="retry--trials"></span>`--trials TRIALS` |  | Trials to grant (default: max_trials). |
| <span id="retry--no-continue"></span>`--no-continue` |  | Only record the decision; run nothing (the run continues on the next `devloops run`). |
| <span id="retry--review-plan"></span>`--review-plan` |  | Pause after each plan for review, and stop on open questions (sets questions: ask). |
| <span id="retry--accept-suggested"></span>`--accept-suggested` |  | Approve plans and accept Claude's suggested answers without pausing (questions: accept-suggested, the default; review them afterwards). |
| <span id="retry--quiet"></span>`--quiet` |  | Print no progress lines, only the final summary. |
| <span id="retry--verbose"></span>`--verbose` |  | Also print each tool Claude uses. |
| <span id="retry--force-unlock"></span>`--force-unlock` |  | Clear a stale lock. |

Options that cannot be used together:

- `--review-plan` or `--accept-suggested`
- `--quiet` or `--verbose`

## `export-sessions` {#export-sessions}

Write every Claude invocation as CSV (FR-033).

```text
devloops export-sessions [--workspace WORKSPACE] [--config CONFIG] [--json] [--csv FILE]
```

| Option | Default | Meaning |
|---|---|---|
| <span id="export-sessions--workspace"></span>`--workspace WORKSPACE` |  | Workspace name (under the project's workspaces_dir) or path; created on the first run (default: the project's `workspace`, else main). |
| <span id="export-sessions--config"></span>`--config CONFIG` |  | Config file merged over the defaults. |
| <span id="export-sessions--json"></span>`--json` |  | Print one JSON status object. |
| <span id="export-sessions--csv"></span>`--csv FILE` |  | Output file (default: standard output). |

## `dashboard` {#dashboard}

Serve the dashboard (until Ctrl+C, or --daemon in the background); --stop stops it; --export writes one shareable file.

```text
devloops dashboard [--workspace WORKSPACE] [--config CONFIG] [--json]
                   [--daemon | --stop | --export [PATH]] [--host HOST] [--port PORT] [--token TOKEN]
                   [--no-token] [--no-open]
```

| Option | Default | Meaning |
|---|---|---|
| <span id="dashboard--workspace"></span>`--workspace WORKSPACE` |  | Workspace name (under the project's workspaces_dir) or path; created on the first run (default: the project's `workspace`, else main). |
| <span id="dashboard--config"></span>`--config CONFIG` |  | Config file merged over the defaults. |
| <span id="dashboard--json"></span>`--json` |  | Print one JSON status object. |
| <span id="dashboard--daemon"></span>`--daemon` |  | Serve in the background; print the address and the log's path. |
| <span id="dashboard--stop"></span>`--stop` |  | Stop the project's dashboard server. |
| <span id="dashboard--export"></span>`--export [PATH]` |  | Write a self-contained dashboard (every file and conversation embedded) to share or keep. |
| <span id="dashboard--host"></span>`--host HOST` |  | The address to listen on (default: 127.0.0.1; 0.0.0.0 for every network, with a token). |
| <span id="dashboard--port"></span>`--port PORT` |  | The port (default: 8765, or the next free one). |
| <span id="dashboard--token"></span>`--token TOKEN` |  | The token to require (default: a random one when listening beyond this machine). |
| <span id="dashboard--no-token"></span>`--no-token` |  | Require no token, even beyond this machine. |
| <span id="dashboard--no-open"></span>`--no-open` |  | Do not open a browser. |

Options that cannot be used together:

- `--daemon` or `--stop` or `--export`

## `status` {#status}

Show run status (read-only).

```text
devloops status [--workspace WORKSPACE] [--config CONFIG] [--json] [loop]
```

| Option | Default | Meaning |
|---|---|---|
| <span id="status--workspace"></span>`--workspace WORKSPACE` |  | Workspace name (under the project's workspaces_dir) or path; created on the first run (default: the project's `workspace`, else main). |
| <span id="status--config"></span>`--config CONFIG` |  | Config file merged over the defaults. |
| <span id="status--json"></span>`--json` |  | Print one JSON status object. |
| <span id="status--loop"></span>`loop` |  | One of `backend-dev`, `frontend-dev`. |

## `check` {#check}

Report whether this environment is ready for the loops.

```text
devloops check [--json]
```

| Option | Default | Meaning |
|---|---|---|
| <span id="check--json"></span>`--json` |  | Print the result as JSON. |

## `init` {#init}

Set up a directory as a devloops project.

```text
devloops init [dir] [--backend-target BACKEND_TARGET | --no-backend]
              [--frontend-target FRONTEND_TARGET | --no-frontend]
              [--requirements REQUIREMENTS | --speckit-feature [DIR]] [--no-prompt] [--no-models]
              [--track-workspaces] [--allow-skills] [--upgrade] [--restore] [--json]
```

| Option | Default | Meaning |
|---|---|---|
| <span id="init--dir"></span>`dir` | `.` | The project root (default: .). |
| <span id="init--backend-target"></span>`--backend-target BACKEND_TARGET` |  | backend-dev's target (default: backend). |
| <span id="init--no-backend"></span>`--no-backend` |  | The project has no backend-dev (targets.backend-dev: null). |
| <span id="init--frontend-target"></span>`--frontend-target FRONTEND_TARGET` |  | frontend-dev's target (default: frontend). |
| <span id="init--no-frontend"></span>`--no-frontend` |  | The project has no frontend-dev (targets.frontend-dev: null). |
| <span id="init--requirements"></span>`--requirements REQUIREMENTS` |  | Default requirements file (PRD or story). |
| <span id="init--speckit-feature"></span>`--speckit-feature [DIR]` |  | Default spec-kit feature folder (no value: the active feature). |
| <span id="init--no-prompt"></span>`--no-prompt` |  | Never ask (implied when stdin or stdout is not a terminal). |
| <span id="init--no-models"></span>`--no-models` |  | Write no model choice into devloops.json (default: opus to plan and write checks, sonnet to build); Claude Code then picks the model. |
| <span id="init--track-workspaces"></span>`--track-workspaces` |  | Do not git-ignore the workspaces folder. |
| <span id="init--allow-skills"></span>`--allow-skills` |  | Add the devloops permission rule to .claude/settings.json (also on an initialized project). |
| <span id="init--upgrade"></span>`--upgrade` |  | Update the installed files of an initialized project, keeping the ones changed here. |
| <span id="init--restore"></span>`--restore` |  | With --upgrade, re-create installed files that were deleted. |
| <span id="init--json"></span>`--json` |  | Print the result as JSON. |

Options that cannot be used together:

- `--backend-target` or `--no-backend`
- `--frontend-target` or `--no-frontend`
- `--requirements` or `--speckit-feature`

## Removed options {#removed-options}

`devloops dashboard` stops with an error naming what replaced these options:

| Option | Instead |
|---|---|
| <span id="dashboard--serve"></span>`--serve` | `devloops dashboard` serves now (add --daemon to run it in the background). |
| <span id="dashboard--open"></span>`--open` | The browser opens by default now (--no-open to not open it). |
| <span id="dashboard--light"></span>`--light` | The summary page is gone; `devloops dashboard` serves the dashboard. |
| <span id="dashboard--out"></span>`--out` | Give the path to --export: `devloops dashboard --export <path>`. |
