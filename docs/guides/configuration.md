---
title: Configuration
description: >-
  Where devloops' settings live, which one wins, the settings you are most likely to change,
  choosing a model per step, and watching the browser.
sources:
  - loops/shared/devloops/config.py
  - loops/shared/devloops/project.py
  - loops/shared/devloops/workspace.py
  - loops/shared/devloops/orchestrator.py
  - loops/shared/devloops/claude.py
  - loops/shared/devloops/checkcmd.py
  - loops/shared/devloops/initcmd.py
  - loops/shared/devloops/engine.py
  - loops/shared/config/defaults.json
  - loops/shared/schemas/config.schema.json
  - loops/shared/schemas/project-config.schema.json
  - spec 001 FR-006
  - spec 002 FR-008
  - spec 003 FR-005
---

# Configuration

devloops works without any configuration beyond what [`devloops init`](../reference/commands.md#init)
writes. This page explains where the settings live, which one wins when two disagree, and the
settings you are most likely to change. The [configuration reference](../reference/configuration.md)
lists every key, its type and its default.

## Where settings live

A [project](../glossary.md#project) has two configuration files, in its `.devloops/` folder:

- **`devloops.json`**, the project's shared settings. `devloops init` writes it. Commit it, so
  everyone who works on the project uses the same settings.
- **`devloops.local.json`**, your own settings on this machine, such as the path of a browser.
  It has the same shape as `devloops.json` and overrides it key by key (`requirements` is
  replaced whole). devloops never creates it, and `devloops init` keeps it out of git.

Both files hold the same keys. The project keys say where things are and what to build:

| Key | What it holds |
|---|---|
| [`targets`](../reference/configuration.md#targets) | The folder each [loop](../glossary.md#loop) writes its code to, relative to the project folder. `null` means the project does not use that loop |
| [`requirements`](../reference/configuration.md#requirements) | The requirements a run uses when you give none: a file (`path`) or a spec-kit feature (`speckit_feature`) |
| [`workspace`](../reference/configuration.md#workspace) | The [workspace](../glossary.md#workspace) commands use when you give no `--workspace` (default `main`) |
| [`workspaces_dir`](../reference/configuration.md#workspaces_dir) | Where workspaces are kept (default `.devloops/workspaces`) |
| [`config`](../reference/configuration.md#config) | The run settings described on the rest of this page |

This is what `devloops init` writes for a project with both loops:

```json
{
  "schema_version": 1,
  "workspace": "main",
  "workspaces_dir": ".devloops/workspaces",
  "targets": {"backend-dev": "backend", "frontend-dev": "frontend"},
  "requirements": {"speckit_feature": "active"},
  "config": {
    "model": "sonnet",
    "models": {"plan": "opus", "replan": "opus", "author-checks": "opus", "fix_last_trial": "opus"}
  }
}
```

devloops finds the project by looking for `.devloops/devloops.json` in the current folder, then
in each folder above it, so every command works from anywhere inside the project. To name the
project yourself instead, set the environment variable `DEVLOOPS_PROJECT` to its folder; a
command stops with [exit code 2](../reference/exit-codes.md#exit-2) when that folder has no
`.devloops/devloops.json`. Paths in both files are relative to the project folder, so a moved or
cloned project still works.

## Which setting wins

A run's settings are merged from five levels. Each level overrides the ones before it:

1. devloops' own defaults (the "Default" column of the
   [reference](../reference/configuration.md#run-configuration));
2. `config` in `devloops.json`;
3. `config` in `devloops.local.json`;
4. a workspace's own file: the file given with [`--config`](../reference/commands.md#run--config)
   (the workspace remembers it), or else a file named `config.json` in the workspace folder, if
   there is one;
5. options on the command line:
   [`--max-trials`](../reference/commands.md#run--max-trials), and
   [`--review-plan`](../reference/commands.md#run--review-plan) or
   [`--accept-suggested`](../reference/commands.md#run--accept-suggested) for
   [`questions`](../reference/configuration.md#questions).

Settings are merged key by key: setting `playwright.headless` in your local file leaves the other
`playwright` keys as they were.

The project keys (`targets`, `requirements`, `workspace`) follow the same idea: the local file
over the shared one, and a command-line option, such as
[`--backend-target`](../reference/commands.md#run--backend-target), over both.

### Settings are fixed when a loop starts

The first time a [loop](../glossary.md#loop) starts in a workspace, devloops merges the settings
and keeps the result with the loop's run. Later changes to the files do not change that run, so a
run never changes its rules halfway. [`devloops status`](../reference/commands.md#status) lists
the keys whose value would now differ, so you can see that a change has not applied.

Command-line options still apply when you resume: `devloops run --max-trials 5` raises the limit
of a run in progress. When such an option changes a value, devloops keeps the new value with the
run and records the change as a `config-override` event, which the dashboard's events view and
the progress output show.

To use new settings for a whole run, start it in a new workspace, for example
`devloops run --workspace second-try`.

## The settings you are most likely to change

| Setting | Default | Change it when |
|---|---|---|
| [`max_trials`](../reference/configuration.md#max_trials) | 3 | [Milestones](../glossary.md#milestone) often need more attempts ([trials](../glossary.md#trial)), or you want runs to stop sooner. It is also the number of planning attempts |
| [`max_invocations_per_run`](../reference/configuration.md#max_invocations_per_run) | 60 | A large plan needs more calls to Claude Code. A run that reaches the limit stops for good |
| [`invocation_timeout_seconds`](../reference/configuration.md#invocation_timeout_seconds) | 1800 | Single calls take longer than 30 minutes. A call that takes longer fails its trial |
| [`max_budget_usd_per_invocation`](../reference/configuration.md#max_budget_usd_per_invocation) | none | You want Claude Code to stop a call that costs more than this, in US dollars |
| [`model`](../reference/configuration.md#model) and [`models`](../reference/configuration.md#models) | as `init` wrote them | You want other models; see [Models per step](#models-per-step) |
| [`questions`](../reference/configuration.md#questions) | `accept-suggested` | You want every plan to wait for your review (`ask`); see [approval and questions](approval-and-questions.md) |
| [`unit_tests.enabled`](../reference/configuration.md#unit_tests.enabled) | `false` | You want the application's own unit tests to pass too before a milestone passes; see [validation](../how-it-works/validation.md) |
| [`runtime`](../reference/configuration.md#runtime) keys | the plan's | The plan starts the application in a way that does not work on your machine, such as the wrong port |
| [`backend`](../reference/configuration.md#backend) keys | from the backend loop | Usually never: in a run, devloops sets these keys from the backend loop's [handoff](../glossary.md#handoff), which replaces any value you set |
| [`git.commit_per_milestone`](../reference/configuration.md#git.commit_per_milestone) | `false` | You want a git commit of the target folder after each milestone passes |
| [`secrets`](../reference/configuration.md#secrets) | none | Values must never be written to devloops' records; see [security](security.md) |

For example, to allow five trials per milestone and run the unit tests, add to `config` in
`devloops.json`:

```json
{"config": {"max_trials": 5, "unit_tests": {"enabled": true}}}
```

With [`git.commit_per_milestone`](../reference/configuration.md#git.commit_per_milestone) on,
devloops commits after each milestone that passes, with the message
`feat(<loop>): complete <milestone id> <title>`. It stages and commits only the files inside the
target folder, so other changes in the repository are left alone. It skips the commit when the
target is not in a git repository or has no changes. Each outcome, a commit, a skip or a failure,
is recorded as a `git-commit` event, and a failed commit never fails the milestone.

A setting with a wrong name or value stops the command before anything runs, with a message
naming it. In `devloops.json` or `devloops.local.json`, it makes the project file not valid:
[exit code 30](../reference/exit-codes.md#exit-30). In a workspace's own file or on the command
line, it is [exit code 2](../reference/exit-codes.md#exit-2).

## Models per step

Each [step](../glossary.md#step) can use its own Claude model. `model` is the model of every step
that `models` does not name; [`models.fix_last_trial`](../reference/configuration.md#models.fix_last_trial)
is the model of a milestone's last allowed fix trial. With neither set, Claude Code uses its own
default. Any name `claude --model` accepts works: a short name such as `opus` or `sonnet`, or a
full model ID.

Most of a run's cost is in the [`implement`](../reference/steps.md#step-implement) and
[`fix`](../reference/steps.md#step-fix) steps: one long call per trial, with many tool calls.
[`plan`](../reference/steps.md#step-plan) runs once per loop, and
[`author-checks`](../reference/steps.md#step-author-checks) once per milestone. A strong model
where the decisions are made, and a cheaper one for the code, costs much less than the strong
model everywhere. This is what `devloops init` writes:

| Step | Model | Why |
|---|---|---|
| `plan`, `replan` | opus | Rare, and every later step builds on the milestones and criteria they write |
| `author-checks` | opus | Once per milestone; the checks then stay the same for every trial, so a wrong check fails every trial |
| `implement`, `fix` | sonnet (`model`) | Most of the tokens; the plan lays the work out and the checks test it |
| `fix_last_trial` | opus | The last fix before the milestone runs out of trials (trial 3 by default; after a [retry grant](../glossary.md#retry-grant), the grant's last trial) gets a stronger attempt |
| `validate-ui` | sonnet (`model`) | Mostly drives the browser and reports what it sees |

`devloops init --no-models` writes no model, which leaves the choice to Claude Code. Use it when
those names do not exist where you run Claude Code, for example through Amazon Bedrock or Google
Vertex.

To see whether a choice pays off, compare runs in the [dashboard](dashboard.md): its Claude calls
view shows the cost by model when a run used more than one. If the cheaper model needs many more
fix trials on your project, move `fix` (or `implement`) back to the stronger model.

## Watching the browser

The frontend loop validates in a browser with no window (headless). To watch it, set this in
your `devloops.local.json`, not the shared file, since a machine without a screen cannot show a
window:

```json
{"config": {"playwright": {"headless": false}}}
```

[`playwright.executable_path`](../reference/configuration.md#playwright.executable_path) names the
browser to start, when Chrome is not installed where Playwright looks for it. A leading `~`
stands for your home folder.
[`playwright.mcp_command`](../reference/configuration.md#playwright.mcp_command) replaces the whole
command that starts the Playwright MCP server; when it is set, devloops uses it exactly as written
and ignores the other two keys.

[`devloops check`](../reference/commands.md#check) warns when a visible browser is set but there is
no screen (on Linux), and when it is set in the shared `devloops.json`.
