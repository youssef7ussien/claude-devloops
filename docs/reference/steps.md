---
title: Steps
description: >-
  Each step devloops runs, in order: what it does, what it may change and what it must answer.
generated: true
---

# Steps

!!! note "Generated page"
    This page is generated from devloops' code; do not edit it. Change the code (or
    `tools/docs/descriptions.json`), then run `python3 tools/docs/gen_reference.py`.

A step is one kind of call devloops makes to Claude Code. The steps below are in the order a run meets them. Each runs headless (`claude -p`) with the tools listed and must answer in the form shown; devloops checks the answer before using it.

## `plan` {#step-plan}

Reads the requirements and the target and writes the plan: milestones in order, each with its tasks, acceptance criteria and how to start the application. It changes no files.

- **Changes files:** no
- **Tools:** `Read`, `Glob`, `Grep`
- **Answer:** a JSON document checked against `plan.schema.json`
- **Model setting:** `models.plan`, else `model`

## `replan` {#step-replan}

Writes the plan again, taking your answers in open-questions.md into account, when you run devloops replan. It changes no files.

- **Changes files:** no
- **Tools:** `Read`, `Glob`, `Grep`
- **Answer:** a JSON document checked against `plan.schema.json`
- **Model setting:** `models.replan`, else `model`

## `author-checks` {#step-author-checks}

Before any code is written for a backend milestone, writes the HTTP requests and expected answers that will check it. The checks are then kept unchanged for every trial.

- **Changes files:** no
- **Tools:** `Read`, `Glob`, `Grep`
- **Answer:** a JSON document checked against `checks.schema.json`
- **Model setting:** `models.author-checks`, else `model`

## `implement` {#step-implement}

A milestone's first trial: Claude Code writes the code for the milestone's tasks in the target.

- **Changes files:** yes, only inside the target
- **Tools:** the `implement_tools` setting
- **Answer:** a JSON object with `tasks`, `assumptions`, `needs_input`, `files_changed`
- **Model setting:** `models.implement`, else `model`

## `fix` {#step-fix}

Each later trial of a milestone: Claude Code is shown why the previous trial failed and changes the code to fix it.

- **Changes files:** yes, only inside the target
- **Tools:** the `implement_tools` setting
- **Answer:** a JSON object with `tasks`, `assumptions`, `needs_input`, `files_changed`
- **Model setting:** `models.fix`, else `model`

## `validate-ui` {#step-validate-ui}

Checks a frontend milestone in a real browser: Claude Code drives the browser through each acceptance criterion and reports what it saw, with screenshots as evidence.

- **Changes files:** no
- **Tools:** `Read`, `mcp__playwright__*`
- **Answer:** a JSON object with `criteria`
- **Model setting:** `models.validate-ui`, else `model`
