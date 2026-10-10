---
title: The backend loop
description: >-
  What backend-dev builds and publishes, what it needs, how it is validated, and what it hands to
  the frontend loop.
sources:
  - loops/backend-dev/loop.json
  - loops/backend-dev/Loop-instructions.md
  - loops/shared/devloops/validators/curl.py
  - loops/shared/devloops/orchestrator.py
  - loops/shared/devloops/engine.py
  - spec 001 FR-014
  - spec 001 FR-015
  - spec 001 FR-016
  - spec 001 FR-017
  - spec 001 FR-018
  - spec 001 FR-019
  - spec 001 FR-041
  - spec 003 FR-007
---

# The backend loop

`backend-dev` is the [loop](../glossary.md#loop) that builds an HTTP API: the backend of your
application. It turns the requirements into a [plan](../glossary.md#plan), then builds the plan's
[milestones](../glossary.md#milestone) one at a time. A milestone passes only when real HTTP
requests to the running backend get the answers they should.

When it is done, it publishes an OpenAPI document: a machine-readable list of the operations the
API offers. The [frontend loop](frontend-loop.md) builds against that document.

## What it needs

- **The requirements**: a Markdown file (a product description or one user story), or a
  [spec-kit](spec-kit.md) feature. See [`--requirements`](../reference/commands.md#run--requirements)
  and [`--speckit-feature`](../reference/commands.md#run--speckit-feature).
- **A target**: the folder it writes the backend's code to
  ([`targets.backend-dev`](../reference/configuration.md#targets.backend-dev)). The folder can be
  empty, or hold an existing backend to extend.
- **Claude Code and curl** on your machine.
  [`devloops check`](../reference/commands.md#check) reports both.

## What it builds

Claude Code chooses the stack. It prefers the one already in the target. If the target is empty,
it follows what the requirements or your configuration say, and only picks a stack itself when
neither says.

The plan also says how to run the backend, its [runtime](../glossary.md#runtime): how to install
its dependencies, the command that starts it, the address it answers on, an address devloops can
ask to know it is up, and where the OpenAPI document lives in the target. Your configuration can
change any of these ([`runtime`](../reference/configuration.md#runtime)).

Claude Code keeps the OpenAPI document up to date as it builds. It adds an operation only in the
milestone that implements it, and removes one that stops existing.

## How it is validated

Before any of a milestone's code exists, Claude Code writes the milestone's
[checks](../glossary.md#check), in the [`author-checks`](../reference/steps.md#step-author-checks)
step. A check is an HTTP request and the answer it must get, such as "`POST /items` with a name
answers 201 and returns the item". The checks are then frozen: every trial is tested against the
same ones, so the code cannot be changed to fit the test.

After Claude Code writes the code, devloops starts the backend itself from the runtime, sends each
check's request with curl, and compares the answers. The milestone passes only when every
[acceptance criterion](../glossary.md#acceptance-criterion) is covered by checks that passed, and
no check calls an operation the backend's own OpenAPI document leaves out. When
[`unit_tests.enabled`](../reference/configuration.md#unit_tests.enabled) is set, the backend's unit
tests must pass too.

[Validation](../how-it-works/validation.md) explains each rule, and
[trials and recovery](../how-it-works/trials-and-recovery.md) what happens when one fails.

A backend run, once its plan is approved, looks like this:

```text
--8<-- "examples/approve.txt"
```

## What it publishes

After each milestone passes, devloops publishes the backend's OpenAPI document as
[`outputs/openapi.json`](../reference/state-files.md#loop-outputs-openapi.json) in the loop's
folder of the [workspace](../glossary.md#workspace).

The published document lists only the operations a passed milestone's checks actually called.
This makes it a [contract](../glossary.md#contract) you can trust: every operation in it was seen
working. An operation the backend has but no check ever called does not fail its milestone. It is
left out of the published document, and listed in the loop's final report and in the document
itself, as unverified. A later milestone whose checks call it adds it back.

## The handoff to the frontend

When the backend loop completes, devloops records the [handoff](../glossary.md#handoff) in
[`run/state.json`](../reference/state-files.md#run-state.json): the published OpenAPI document, and
how to start the backend (its start command, its folder, its address, and its ready address).
The frontend loop starts from it. During frontend validation, devloops starts the backend with
that command, so the browser talks to the real backend.

The frontend loop never starts before the backend loop has completed.

## Backend-only projects

A project without a frontend sets
[`targets.frontend-dev`](../reference/configuration.md#targets.frontend-dev) to `null`, or leaves
it out. [`devloops init --no-frontend`](../reference/commands.md#init--no-frontend) does this, as
does answering `none` to the frontend question.

[`devloops run`](../reference/commands.md#run) then plans and builds the backend alone, and the run
[completes](../reference/statuses.md#run-completed) when the backend loop does.
[`devloops status`](../reference/commands.md#status) and the [dashboard](dashboard.md) show only
the backend, and `devloops check` marks the browser tools `unused`.

devloops still records the handoff. If you add a frontend later (set `targets.frontend-dev` and
run `devloops run` again), the frontend loop starts from it, without building the backend again.

A frontend on its own, built against an existing backend's OpenAPI document, is not supported:
the frontend loop runs only after the backend loop, in the same run.
