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
  - spec 001 D-15
  - spec 001 FR-041
  - spec 001 FR-042
  - spec 007 FR-001
  - spec 007 FR-004
  - spec 007 FR-006
  - spec 007 FR-009
  - spec 007 FR-011
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

## The design

So that every page looks like part of one product, the plan decides the design once, before any
page is built. Its design brief names the design system or component library, the colours, the
typography, the spacing, the layout and the base components. Claude Code chooses it in the same
order as the stack: the look the target already has, then what the requirements or your design
references show, and only then a proposal of its own. A plan without a design brief is rejected,
and a disagreement between those sources becomes an
[open question](../glossary.md#open-question). The brief is in the loop's
[`plan-summary.md`](../reference/state-files.md#loop-outputs-plan-summary.md) and on the
[dashboard](dashboard.md), beside the stack.

When the target has no frontend yet, the first milestone builds the shared pieces: the theme, the
layout with its navigation, and the base components, such as buttons, form fields, lists, and the
empty and error states. Every later milestone reuses them.

Claude Code is also given rules for each page: a clear layout, every state shown (loading, empty,
error, disabled), semantic HTML with a label for every field, a visible focus, and motion only
where it helps. The points a browser can check become acceptance criteria of each page, so
[validation](../how-it-works/validation.md) enforces them:

- the page at 375 px (a phone) and 1280 px (a desktop) wide, without sideways scrolling;
- its main actions done with the keyboard alone, with the focus visible;
- the error a person sees after sending a form with a wrong value.

Loading, empty and failure states stay rules rather than criteria: they depend on timing, or on
data the backend may already hold from its own checks, so a browser cannot always reach them.

How the pages look is never graded: a model's taste would fail trials for no clear reason.

To show the look you want, list screenshots, a brand guide, or a folder of them in
[`design.references`](../reference/configuration.md#design.references), relative to the project
root:

```json
{"config": {"design": {"references": ["design/brand-guide.md", "design/screenshots"]}}}
```

When the frontend loop first starts in a workspace, devloops copies them into the loop's state
folder, under `design-references/`. Claude Code is given those copies, not the originals'
folders, while it plans and builds each milestone. A reference must not hold the workspace itself:
name the design files or their own folder, not the project root. A change to a reference after that does not reach the
run; start a new workspace to use it. A path that does not exist stops `devloops run` before
anything runs, with [exit code 30](../reference/exit-codes.md#exit-30), and
[`devloops check`](../reference/commands.md#check) reports it.

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

The document can also list operations as unverified: the backend has them, but no check of this
run called them. A run of one [story](../glossary.md#story) on an existing application verifies
only what the story touches, so the rest of its API is unverified, although the existing pages
keep calling it. Claude is told not to add calls to unverified operations; if a requirement needs
one, Claude asks.

When the frontend's folder already held code before the run, a request to an unverified operation
does not fail validation: devloops lists the operation in the trial's result, in the dashboard
and in the loop's [`final-report.md`](../reference/state-files.md#loop-outputs-final-report.md),
under "Calls to unverified operations". devloops cannot tell which code made the request, so read
that list: a call the run added there was not checked by the backend. When the folder was empty,
every request comes from code the run wrote, and a request to an unverified operation fails the
contract. A request to an operation the document does not declare at all always fails it.

> **Changed by spec 001 D-15**: a request to an unverified operation used to fail the contract,
> so a story run failed whenever an existing page called the API.

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
