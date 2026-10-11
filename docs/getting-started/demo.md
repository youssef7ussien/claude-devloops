---
title: A complete example
description: >-
  Build a small application with a backend and a frontend from a PRD, then extend it with one
  story file: the requirements, the commands, and what to watch.
sources:
  - docs-include/demo
  - loops/shared/devloops/cli.py
  - loops/shared/devloops/inputs.py
  - loops/shared/devloops/orchestrator.py
  - loops/shared/schemas/checks.schema.json
  - spec 001 FR-009
  - spec 001 FR-010
  - spec 003 FR-006
---

# A complete example

This page builds Color Clicker, a web page whose background changes to a random color each time
you click it, in two runs:

1. A **PRD** (a product requirements document) describes the whole application. The first run
   builds it: a backend with two HTTP operations, then a page that uses them.
2. A **story file** adds one feature, a counter of the changes. The second run builds only that
   story, on top of the code the first run wrote.

Both loops run, so you need everything [Install](install.md) lists: Python, Claude Code, curl,
Node and a Chrome browser. Read [your first run](first-run.md) first for what each command does.

## The requirements

Make a folder and save the two files below in it.

`PRD.md`, the whole application:

```markdown
--8<-- "demo/PRD.md"
```

`US01.md`, one [story](../glossary.md#story) that extends it:

```markdown
--8<-- "demo/US01.md"
```

### Why they are written this way

- **Exact routes and shapes.** Each operation names its method, path, status and JSON body.
  The backend loop writes its HTTP [checks](../glossary.md#check) from them before any code
  exists, and the frontend loop builds the page against the same operations.
- **Testable statements.** Every rule can be seen from outside: an answer, a status, what the
  page shows. Claude's report that the work is done never counts; only the
  [validation](../glossary.md#validation) does.
- **Random, but still checkable.** The color is random, so no check can expect a fixed value.
  A check can still take the color one answer returns and require the next answer to return the
  same color, and the count is always exact. That "different from the current color" holds
  stays in the requirements, but checks cannot compare two values for inequality, so they do not
  test it.
- **What is out of scope.** Saying what not to build keeps the plan small.
- **The story stands on its own.** A story file is planned alone, without the PRD. So
  `US01.md` says which application it extends and every operation it changes. Claude Code reads
  the code already in each [target](../glossary.md#target) and follows it.

## Run 1: the PRD

```sh
devloops init --requirements PRD.md --no-prompt
devloops check
devloops run --review-plan
```

[`devloops init`](../reference/commands.md#init) sets the folder up, with the backend's code in
`backend/` and the frontend's in `frontend/`, and `PRD.md` as the requirements.
[`devloops check`](../reference/commands.md#check) should show every tool `ready`.
[`--review-plan`](../reference/commands.md#run--review-plan) pauses the run after each plan.

The first run creates the [workspace](../glossary.md#workspace), `.devloops/workspaces/main/`,
so start the dashboard now, while the run waits:

```sh
devloops dashboard --daemon
```

[`devloops dashboard --daemon`](../reference/commands.md#dashboard--daemon) serves it in the
background; open the address it prints to follow the rest of the run. Before the first run there
is no workspace to show, and the command says so.

Read `.devloops/workspaces/main/backend-dev/outputs/plan-summary.md`, then run
[`devloops approve`](../reference/commands.md#approve). The backend loop builds its
[milestones](../glossary.md#milestone) and publishes its OpenAPI document. Then the frontend
loop plans; read `.devloops/workspaces/main/frontend-dev/outputs/plan-summary.md` and approve
again.

What to watch:

- **Checks before code.** In the dashboard, each backend milestone starts with an
  [`author-checks`](../reference/steps.md#step-author-checks) call that writes its HTTP checks,
  before any of its code exists. After each [trial](../glossary.md#trial), devloops starts the
  backend and sends every request itself.
- **A failed trial is fixed.** When validation fails, the next trial gets the
  [evidence](../glossary.md#evidence) and fixes the code.
- **The handoff.** `backend-dev/outputs/openapi.json` lists only the operations the checks
  called. The frontend loop builds against it (the [handoff](../glossary.md#handoff)), and
  every request the page sends in the browser must be one of them.
- **The cost.** The dashboard shows each call to Claude Code, with its tokens and cost.

When the run completes, start the backend and the frontend with the commands in the Runtime
section of each loop's `plan-summary.md`, and click the page. Each loop's
[`final-report.md`](../reference/state-files.md#loop-outputs-final-report.md) lists the
assumptions Claude Code made.

## Run 2: the story

```sh
devloops run --requirements US01.md --story-file --workspace us01
```

[`--story-file`](../reference/commands.md#run--story-file) says that `US01.md` is one story, not
a whole PRD. The run needs a new workspace
([`--workspace`](../reference/commands.md#run--workspace)): a workspace keeps the requirements it
started with, so `main` would refuse a different file. Both loops run again, in
`.devloops/workspaces/us01/`, and change the code in the same `backend/` and `frontend/`
folders. The plan approves itself this time; add `--review-plan` to read it first.

The dashboard shows both workspaces; pick `us01` to follow this run.

A PRD can hold several stories too. With
[`--story-id`](../reference/commands.md#run--story-id), a run builds only the story with that
ID, and reads the rest of the PRD for context.

## What one real run looked like

These are the numbers of one real run of both files, on 11 October 2026. Yours will differ:
Claude Code may plan other milestones, and costs and times change with the models.

The project used cheaper models than the defaults `devloops init` writes: Opus to plan, Sonnet to
write checks, replan and make a milestone's last fix, and Haiku for everything else
([`model`](../reference/configuration.md#model) and
[`models`](../reference/configuration.md#models) in `.devloops/devloops.json`):

```json
"config": {
  "model": "haiku",
  "models": {
    "plan": "opus",
    "replan": "sonnet",
    "author-checks": "sonnet",
    "fix_last_trial": "sonnet"
  }
}
```

Its browser was Chromium, named in `devloops.local.json` with
[`playwright.executable_path`](../reference/configuration.md#playwright.executable_path).

| Run | Loop | Milestones | Trials | Calls | Cost | Time |
|---|---|---|---|---|---|---|
| PRD (`main`) | backend-dev | 2: the server and `GET /api/state`; `POST /api/changes` | 2 | 5 | $0.22 | 2.6 min |
| | frontend-dev | 3: the page shell (title, color code, footer); loading the color; clicking, with the footer link left out | 4 | 8 | $0.24 | 7 min |
| Story (`us01`) | backend-dev | 2: the counter; `POST /api/reset` | 2 | 5 | $0.33 | 2.5 min |
| | frontend-dev | 2: showing the count; the Reset button | 2 | 5 | $0.29 | 3.8 min |
| **Total** | | **9** | **10** | **23** | **$1.07** | **16 min** |

What happened along the way:

- **Claude Code chose the stack.** The PRD names none and the targets were empty, so the plan
  chose a Node.js server with no dependencies and said why. The story's runs found that code
  and kept to it.
- **One trial failed, and the next one passed.** The page's first trial could not start: another
  program on the machine already used port 8080. devloops recorded the failure and its log, and
  the next trial, a [`fix`](../reference/steps.md#step-fix), started from that evidence. Claude
  Code found nothing wrong with the code, and the second trial passed. A trial fails when
  devloops' own validation fails, whatever the reason.
- **No questions.** The requirements left nothing that needed an answer, so the plans were
  approved without a pause. Each plan recorded its [assumptions](../glossary.md#assumption)
  instead, six to nine per loop. For example, the footer has a translucent white background so
  its link stays readable on any color, a styling choice the PRD did not make. Each loop's
  `final-report.md` lists them for review.
- **The OpenAPI document grew with the story.** After the PRD it listed `GET /api/state` and
  `POST /api/changes`; after the story it also listed `POST /api/reset`. Each time, the frontend
  was built against the document of its own run.

## Next

- [How it works](../how-it-works/index.md): what happens in each run, step by step.
- [The backend loop](../guides/backend-loop.md) and [the frontend loop](../guides/frontend-loop.md):
  how each one validates.
- [Approval and questions](../guides/approval-and-questions.md): reviewing plans and answering
  Claude's questions.
