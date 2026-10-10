---
title: The frontend loop
description: >-
  What frontend-dev builds, what it needs, how it is validated in a real browser, and how it keeps
  to the backend's contract.
sources:
  - loops/frontend-dev/loop.json
  - loops/frontend-dev/Loop-instructions.md
  - loops/shared/devloops/validators/playwright.py
  - loops/shared/devloops/checkcmd.py
  - loops/shared/devloops/orchestrator.py
  - spec 001 FR-011
  - spec 001 FR-020
  - spec 001 FR-021
  - spec 001 FR-022
  - spec 001 FR-023
  - spec 001 FR-024
  - spec 001 FR-041
  - spec 001 FR-042
---

# The frontend loop

`frontend-dev` is the [loop](../glossary.md#loop) that builds the user interface: the pages a
person uses. It plans from the same [requirements](../glossary.md#requirements) as the
[backend loop](backend-loop.md), then builds its [milestones](../glossary.md#milestone) one at a
time, usually one feature or one page each. A milestone passes only when its pages work in a real browser.

Every request a page sends to the backend must be an operation the backend's published OpenAPI
document lists. The frontend cannot rely on an endpoint the backend never showed working.

## What it needs

- **The requirements**: the same ones the backend loop was given.
- **The backend's OpenAPI document**, from the [handoff](../glossary.md#handoff). The frontend loop
  always runs after the backend loop, in the same run, so this comes by itself.
- **A target**: the folder it writes the frontend's code to
  ([`targets.frontend-dev`](../reference/configuration.md#targets.frontend-dev)).
- **On your machine**: Claude Code, Node (with `npx`, which runs the Playwright MCP server that
  lets Claude Code drive a browser), and a Chrome browser
  (`npx playwright install chrome`, or set
  [`playwright.executable_path`](../reference/configuration.md#playwright.executable_path) to
  another Chromium-based browser). [`devloops check`](../reference/commands.md#check) reports each.

## What it builds

As in the backend loop, Claude Code prefers the stack already in the target, then what the
requirements or your configuration say, and picks one itself only when neither says.

Each milestone's [acceptance criteria](../glossary.md#acceptance-criterion) describe what a person
sees and does: what is on the page, what a click does, and what they see next. "The page loads"
is never enough on its own. A browser cannot run a command, so a criterion never asks for
something only a command shows, such as "the unit tests pass"; the unit tests are tasks instead.

The plan's [runtime](../glossary.md#runtime) says how to build and serve the frontend, and the
address it answers on. That address is the UI address devloops tests and publishes.

## How it is validated

For each [trial](../glossary.md#trial), devloops:

1. starts the backend, with the start command from the handoff (see
   [`backend.start_command`](../reference/configuration.md#backend.start_command));
2. starts the frontend from its runtime;
3. runs the frontend's unit tests, when the plan or your configuration gives a command for them;
4. asks Claude Code, in the [`validate-ui`](../reference/steps.md#step-validate-ui) step, to open
   the pages in a real browser and check each acceptance criterion, taking screenshots as
   [evidence](../glossary.md#evidence);
5. reads the browser's own list of the requests each page sent, and checks every request to the
   backend against the OpenAPI document.

The milestone passes only when every criterion passed with evidence from a call that really used
the browser, every backend request matches an operation in the document, and nothing was written
outside the target. When [`unit_tests.enabled`](../reference/configuration.md#unit_tests.enabled)
is set, the unit tests must pass too.

The request list comes from the browser, never from what Claude Code says the page did.
[Validation](../how-it-works/validation.md) explains each rule.

## Keeping to the contract

Claude Code is told to call the backend only through the operations its OpenAPI document lists,
and never to invent one. When a requirement needs an operation the document does not have, Claude
raises an [open question](../glossary.md#open-question) instead.

The document can also list operations as unverified: the backend has them, but no check ever
called them. The frontend must not call those either. If a requirement needs one, Claude asks.

## What it publishes

Each time devloops starts the frontend to validate it, it records the address the frontend
answers on: in the loop's
[`run.json`](../reference/state-files.md#loop-state-run.json), and in the file `ui-url.txt` in the
loop's outputs folder. [`devloops status`](../reference/commands.md#status) prints it as the UI URL.

## Watching the browser

The browser runs without a window by default. To watch it, turn on the window in your own
`.devloops/devloops.local.json`, not in the shared `.devloops/devloops.json`, since a machine
without a display cannot show it:

```json
{"config": {"playwright": {"headless": false}}}
```

See [`playwright.headless`](../reference/configuration.md#playwright.headless). `devloops check`
warns when a window is asked for on a machine with no display, or in the shared file. Like every
setting, it is fixed when the loop first starts in a workspace.

## When the project has no frontend

A project can use the backend loop alone; see
[backend-only projects](backend-loop.md#backend-only-projects). A frontend added later starts from
the handoff the backend loop already recorded.
