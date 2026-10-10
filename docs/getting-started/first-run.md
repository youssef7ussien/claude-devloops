---
title: Your first run
description: >-
  Set up a project, write its requirements, start a run, approve its plan, and find the results.
sources:
  - loops/shared/devloops/cli.py
  - loops/shared/devloops/initcmd.py
  - loops/shared/devloops/checkcmd.py
  - tools/docs/examples.py
  - spec 002 FR-003
  - spec 002 FR-005
  - spec 002 FR-007
  - spec 002 FR-020
  - spec 003 FR-001
  - spec 003 FR-009
  - spec 006 FR-009
---

# Your first run

This page takes you from an empty folder to a small, validated backend: a service that lists and
creates items. It builds the backend only, so you need Python, Claude Code and curl, but not Node
or a browser. See [Install](install.md) first.

The outputs below come from a real run of devloops on this same example, with times, paths and
ids made the same on every run. Yours will show your own folder, times and costs, and Claude Code
may choose a different number of milestones.

## 1. Make a folder and write the requirements

A [project](../glossary.md#project) is a folder devloops works in. Make one, and write what you
want built in a Markdown file, the [requirements](../glossary.md#requirements):

```sh
mkdir app && cd app
```

Save this as `requirements.md` in that folder:

```markdown
# Items service

A small HTTP service that keeps a list of items.

- FR-1: Clients can list the items.
- FR-2: Clients can create an item with a name.
```

Real requirements say more: who uses the application, what each part does, the rules it follows.
Giving each requirement an ID, as here, lets the plan cite it. Whatever the requirements leave
open, Claude Code decides and records as an [assumption](../glossary.md#assumption), or asks as an
[open question](../glossary.md#open-question).

## 2. Set up the project

```sh
devloops init --no-frontend --requirements requirements.md --no-prompt
```

[`devloops init`](../reference/commands.md#init) sets the folder up for devloops.
[`--no-frontend`](../reference/commands.md#init--no-frontend) says this project has no frontend,
[`--requirements`](../reference/commands.md#init--requirements) names the requirements file, and
[`--no-prompt`](../reference/commands.md#init--no-prompt) keeps the defaults for everything else.
Without these options, `devloops init` asks each question in turn: the folder for the backend's
code, the folder for the frontend's code, the requirements, and whether to use the recommended
Claude models.

```text
--8<-- "examples/init.txt"
```

It created:

- `.devloops/devloops.json`, the project's configuration: the requirements, the folder each loop
  writes its code to (its [target](../glossary.md#target); here `backend`), and the models. See
  [configuration](../guides/configuration.md).
- `.claude/skills/`, two skills that let you ask Claude Code, in a normal session, to run devloops
  or report its status. See [skills](../guides/skills.md).
- `.gitignore` rules that keep devloops' working files out of git.

`devloops init` never overwrites a file, and running it again changes nothing.

## 3. Check the machine

```sh
devloops check
```

```text
--8<-- "examples/check.txt"
```

[`devloops check`](../reference/commands.md#check) lists each tool this project needs. The
browser and the Playwright MCP server are `unused`, because this project has no frontend. If a
tool is missing, the line under it says how to install it.

## 4. Start the run

```sh
devloops run --review-plan
```

[`devloops run`](../reference/commands.md#run) plans and builds the application. By default it
does not stop: it approves the plan by itself and builds every milestone. For a first run,
[`--review-plan`](../reference/commands.md#run--review-plan) is worth adding: the run pauses
after planning, so you can read the plan before any code is written.

```text
--8<-- "examples/run.txt"
```

Claude Code turned the requirements into a [plan](../glossary.md#plan) of two
[milestones](../glossary.md#milestone), each a part of the backend that can be built and tested
on its own. Then the run paused, with [exit code 10](../reference/exit-codes.md#exit-10). In a
terminal, devloops asks what to do instead of exiting; press `q` to exit as shown here.

## 5. Review the plan and approve it

All of the run's files are in its [workspace](../glossary.md#workspace),
`.devloops/workspaces/main/`. Read the plan in
`.devloops/workspaces/main/backend-dev/outputs/plan-summary.md`: the milestones in order, the
tasks of each, the statements each must make true (its
[acceptance criteria](../glossary.md#acceptance-criterion)), and how the application will be
started. Questions, if any, are in
[`open-questions.md`](../reference/state-files.md#loop-outputs-open-questions.md) next to it,
with Claude's suggested answer; write your own answer under a question to replace it.

When the plan looks right, approve it:

```sh
devloops approve
```

```text
--8<-- "examples/approve.txt"
```

[`devloops approve`](../reference/commands.md#approve) records your approval and continues the
run in the same command. For each milestone, devloops asks Claude Code to write the HTTP
[checks](../glossary.md#check) first, then the code. Then devloops starts the application, sends
the checks' requests to it, and compares each answer with the one expected. Here each milestone
passed on its first [trial](../glossary.md#trial). When a trial fails, the next one fixes the
code, up to three trials per milestone.

If the plan is not what you want, run [`devloops replan`](../reference/commands.md#replan)
instead, after writing your answers in `open-questions.md`. Claude Code then plans again.

## 6. Follow a run

A run prints one line per step, as above. To see more, open the
[dashboard](../glossary.md#dashboard) in another terminal:

```sh
devloops dashboard
```

[`devloops dashboard`](../reference/commands.md#dashboard) serves a page on your own machine and
opens it in your browser. It shows each milestone, every call to Claude Code with its prompt,
conversation and cost, the files, and the questions, and follows the run as it happens. See
[the dashboard](../guides/dashboard.md).

[`devloops status`](../reference/commands.md#status) prints where the run stands:

```text
--8<-- "examples/status.txt"
```

## 7. Find the results

The code is in the target folder, `backend/`. The loop's `outputs/` folder,
`.devloops/workspaces/main/backend-dev/outputs/`, holds what you read afterwards:

| File | What it holds |
|---|---|
| [`final-report.md`](../reference/state-files.md#loop-outputs-final-report.md) | The assumptions to review, the suggested answers accepted (when there were any), and the outcome and validation of each milestone |
| [`plan-summary.md`](../reference/state-files.md#loop-outputs-plan-summary.md) | The plan |
| [`milestone-NN-slug.md`](../reference/state-files.md#loop-outputs-milestone-nn-slug.md) | One file per milestone, with each task marked once it is achieved |
| [`open-questions.md`](../reference/state-files.md#loop-outputs-open-questions.md) | Every question, with the answer used |
| [`openapi.json`](../reference/state-files.md#loop-outputs-openapi.json) | The backend's OpenAPI document, listing only operations its validation called |

Read `final-report.md` first. Its first sections, the assumptions and any suggested answers
devloops accepted, are the decisions the requirements left open, which you may want to check.
[State and files](../how-it-works/state-and-files.md) explains the rest of the workspace.

## When a run stops

A run that does not complete prints the one command to run next, and exits with a code that says
why:

| Exit code | What it means | What to do |
|---|---|---|
| [10](../reference/exit-codes.md#exit-10) | The plan waits for your review | Read `plan-summary.md`, then `devloops approve` or `devloops replan` |
| [20](../reference/exit-codes.md#exit-20) | A milestone used all its trials, or a question needs your answer | `devloops status` says which; read the last trial's evidence, or answer in `open-questions.md`, then `devloops retry` |
| [30](../reference/exit-codes.md#exit-30) | Something the run needs is missing or wrong, such as a tool or the requirements | Fix what the message names, then run the same command again |
| [40](../reference/exit-codes.md#exit-40) | Another devloops command is working in this workspace | Wait for it; if none is running, `devloops status` says how to clear the lock |
| [50](../reference/exit-codes.md#exit-50) | Claude Code could not be used: an outage, a rate limit, or an expired login | Wait, or log in again, then `devloops run`. No trial was used up |
| [130](../reference/exit-codes.md#exit-130) | You pressed Ctrl+C | `devloops run` resumes where it stopped |

[Trials and recovery](../how-it-works/trials-and-recovery.md) explains each case.

## Next

- [How it works](../how-it-works/index.md): what happened during this run, step by step.
- [The frontend loop](../guides/frontend-loop.md): add a user interface built against this
  backend.
- [Configuration](../guides/configuration.md): models, trial limits and the other settings.
