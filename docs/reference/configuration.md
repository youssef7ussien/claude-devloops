---
title: Configuration keys
description: >-
  Every configuration key: where it goes, its type, its default and what it does.
generated: true
---

# Configuration keys

!!! note "Generated page"
    This page is generated from devloops' code; do not edit it. Change the code (or
    `tools/docs/descriptions.json`), then run `python3 tools/docs/gen_reference.py`.

devloops reads its settings from several places. Each one overrides the ones before it:

> packaged defaults < project `devloops.json` `config` < `devloops.local.json` `config` < workspace `config.json` / `--config` < CLI flags.

- **Packaged defaults:** the values below marked **Default**.
- **Project files:** the `config` key of `.devloops/devloops.json` (shared, committed) and of `.devloops/devloops.local.json` (yours, not committed).
- **Workspace file:** `config.json` in the workspace, or the file given with `--config`.
- **Command-line options**, such as `--max-trials`.

A run keeps the settings it started with: later edits to the files apply to new runs.

## Run configuration {#run-configuration}

These keys go under `config` in the project files, or at the top of a workspace's `config.json`.

### `max_trials` {#max_trials}

How many trials a milestone gets before the run stops, and how many tries the plan step gets. A trial is one attempt to build the milestone and pass its validation.

- **Type:** integer, at least 1
- **Default:** `3`

### `max_invocations_per_run` {#max_invocations_per_run}

The most calls to Claude Code one run may make. When a run reaches it, the run stops (invocation-cap).

- **Type:** integer, at least 1
- **Default:** `60`

### `invocation_timeout_seconds` {#invocation_timeout_seconds}

How long one call to Claude Code may run, in seconds. A call that takes longer is stopped and its trial fails (timeout).

- **Type:** integer, at least 30
- **Default:** `1800`

### `max_budget_usd_per_invocation` {#max_budget_usd_per_invocation}

The most one call to Claude Code may spend, in US dollars, passed to Claude Code as its budget. null sets no limit.

- **Type:** number or null
- **Default:** `null`

### `model` {#model}

The model every step uses unless `models` names one for that step, passed to Claude Code as --model. null lets Claude Code choose its default.

- **Type:** string or null
- **Default:** `null`

### `models` {#models}

A model per step, for example a strong model to plan and a cheaper one to write code. A step not named here, or set to null, uses `model`.

- **Type:** object

### `models.plan` {#models.plan}

The model of the plan step, which turns the requirements into milestones.

- **Type:** string or null

### `models.replan` {#models.replan}

The model of the replan step, which revises a plan after the developer's feedback.

- **Type:** string or null

### `models.author-checks` {#models.author-checks}

The model of the author-checks step, which writes a backend milestone's HTTP checks before any code.

- **Type:** string or null

### `models.implement` {#models.implement}

The model of the implement step, a milestone's first trial.

- **Type:** string or null

### `models.fix` {#models.fix}

The model of the fix step, each later trial of a milestone.

- **Type:** string or null

### `models.fix_last_trial` {#models.fix_last_trial}

The model of a milestone's last allowed fix trial, so a hard failure gets a stronger attempt before the run stops.

- **Type:** string or null

### `models.validate-ui` {#models.validate-ui}

The model of the validate-ui step, which checks a frontend milestone in a real browser.

- **Type:** string or null

### `implement_tools` {#implement_tools}

The Claude Code tools the implement and fix steps may use. They are the only steps that change code.

- **Type:** list of strings
- **Default:** `["Read", "Edit", "Write", "Glob", "Grep", "Bash"]`

### `unit_tests` {#unit_tests}

Running the target's unit tests as part of validation.

- **Type:** object

### `unit_tests.enabled` {#unit_tests.enabled}

Run unit tests when a milestone is validated; a failing test fails the trial.

- **Type:** boolean
- **Default:** `false`

### `unit_tests.command` {#unit_tests.command}

The command that runs the unit tests. null uses the command the plan names (runtime.unit_test_command).

- **Type:** string or null
- **Default:** `null`

### `runtime` {#runtime}

How to start the application while it is validated. Each key set here replaces the value the plan chose.

- **Type:** object

### `runtime.install_command` {#runtime.install_command}

How to install the application's dependencies. Shown with the plan; devloops does not run it (the implement step installs dependencies).

- **Type:** string

### `runtime.start_command` {#runtime.start_command}

The command that starts the application for validation.

- **Type:** string

### `runtime.cwd` {#runtime.cwd}

The folder the start command runs in, relative to the target.

- **Type:** string

### `runtime.base_url` {#runtime.base_url}

The address the running application answers on, for example http://127.0.0.1:8000.

- **Type:** string

### `runtime.ready_url` {#runtime.ready_url}

An address devloops asks until it answers, to know the application has started.

- **Type:** string

### `runtime.ready_timeout_seconds` {#runtime.ready_timeout_seconds}

How long to wait for the application to answer at its ready address, in seconds, before the trial fails.

- **Type:** integer, at least 1
- **Default:** `120`

### `runtime.openapi_path` {#runtime.openapi_path}

Where the backend writes its OpenAPI document, relative to the target.

- **Type:** string

### `backend` {#backend}

For the frontend loop only: the backend its pages call while they are validated.

- **Type:** object

### `backend.base_url` {#backend.base_url}

The address of the backend. Without a start command, devloops expects a backend already running there.

- **Type:** string

### `backend.start_command` {#backend.start_command}

The command that starts the backend during frontend validation.

- **Type:** string

### `backend.cwd` {#backend.cwd}

The folder the backend's start command runs in, relative to the frontend target.

- **Type:** string

### `backend.ready_url` {#backend.ready_url}

An address devloops asks until it answers, to know the backend has started. Defaults to backend.base_url.

- **Type:** string

### `playwright` {#playwright}

The browser the frontend loop validates in, driven through the Playwright MCP server.

- **Type:** object

### `playwright.headless` {#playwright.headless}

true runs the browser without a window. false shows it, so you can watch validation; that needs a display.

- **Type:** boolean
- **Default:** `true`

### `playwright.executable_path` {#playwright.executable_path}

The browser program to start, when the Chrome that Playwright expects is not installed. Used only when mcp_command is null.

- **Type:** string or null
- **Default:** `null`

### `playwright.mcp_command` {#playwright.mcp_command}

The full command that starts the Playwright MCP server, used exactly as written. null runs npx @playwright/mcp@latest with the two settings above.

- **Type:** list of strings or null
- **Default:** `null`

### `git` {#git}

Git commits devloops makes in the target.

- **Type:** object

### `git.commit_per_milestone` {#git.commit_per_milestone}

After each achieved milestone, commit the target's changes. A failed commit does not fail the milestone.

- **Type:** boolean
- **Default:** `false`

### `secrets` {#secrets}

Values devloops replaces with *** before it writes anything: prompts, call records, logs, evidence and reports.

- **Type:** object

### `secrets.env` {#secrets.env}

Names of environment variables whose values are secret.

- **Type:** list of strings
- **Default:** `[]`

### `secrets.literals` {#secrets.literals}

Secret values, written out.

- **Type:** list of strings
- **Default:** `[]`

### `boundary` {#boundary}

Where Claude Code may write. Writes outside the target fail the trial.

- **Type:** object

### `boundary.allowed_extra` {#boundary.allowed_extra}

Extra paths Claude Code may write to inside a checked git repository, for example a cache folder.

- **Type:** list of strings
- **Default:** `[]`

### `questions` {#questions}

What happens to the plan and to open questions. accept-suggested: the plan is approved and Claude's suggested answers are accepted without pausing, and flagged for review; a question without a suggestion still stops the run. ask: every plan pauses for your review, and open questions stop the run.

- **Type:** one of `"ask"`, `"accept-suggested"`
- **Default:** `"accept-suggested"`

## Project file {#project-file}

These keys go at the top of `.devloops/devloops.json` and `.devloops/devloops.local.json`. The local file is merged over the shared one, and relative paths are relative to the project's folder.

### `schema_version` {#schema_version}

The version of this file's format. Always 1.

- **Type:** always `1`

### `workspace` {#workspace}

The workspace commands use when --workspace is not given.

- **Type:** string, matching `^[a-z0-9-]+$`
- **Default:** `"main"`

### `workspaces_dir` {#workspaces_dir}

The folder that holds workspaces given by name, relative to the project root.

- **Type:** string
- **Default:** `".devloops/workspaces"`

### `targets` {#targets}

The folder each loop writes its code to. A loop with a folder here is part of every run.

- **Type:** object

### `targets.backend-dev` {#targets.backend-dev}

The folder the backend loop writes to, relative to the project root. null or missing: the project does not use the backend loop.

- **Type:** string or null

### `targets.frontend-dev` {#targets.frontend-dev}

The folder the frontend loop writes to, relative to the project root. null or missing: the project does not use the frontend loop.

- **Type:** string or null

### `requirements` {#requirements}

The requirements a run reads when none is given on the command line: a file (path) or a spec-kit feature (speckit_feature), not both.

- **Type:** object or null

### `requirements.path` {#requirements.path}

The requirements file, relative to the project root.

- **Type:** string

### `requirements.story_file` {#requirements.story_file}

true: the requirements file is one standalone story, not a whole product description.

- **Type:** boolean
- **Default:** `false`

### `requirements.speckit_feature` {#requirements.speckit_feature}

A spec-kit feature folder, or "active" for the feature spec-kit marks as active (.specify/feature.json).

- **Type:** string

### `config` {#config}

Run configuration for this project: the same keys as a workspace's config.json.

- **Type:** object (the run configuration keys)
