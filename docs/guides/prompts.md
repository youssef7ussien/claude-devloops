---
title: Prompts
description: >-
  How devloops builds each prompt it sends to Claude Code, and how to replace a part of it for
  one project.
sources:
  - loops/shared/devloops/prompts.py
  - loops/shared/devloops/claude.py
  - loops/shared/devloops/engine.py
  - loops/shared/project/prompts/README.md
  - loops/shared/prompts
  - spec 002 FR-030
  - spec 002 FR-031
  - spec 002 FR-032
---

# Prompts

Every [call](../glossary.md#call) devloops makes to Claude Code starts with a prompt. devloops
builds it from packaged parts. You can replace any of those parts for one project, for example to
add "use the existing logger" to every step, or to give the plan step your team's rules.

## What a prompt is made of

Each prompt has four parts, in this order:

1. **The shared rules** (`common.md`): what every call must do and must not do, whatever the
   loop or step.
2. **The loop's instructions** (`Loop-instructions.md`): what the
   [backend loop](backend-loop.md) or the [frontend loop](frontend-loop.md) builds, and how.
3. **The step's instructions** (`steps/<step>.md`): what this one
   [step](../glossary.md#step) must do and return.
4. **The context**: the facts of this call, such as the requirements, the milestone, and the
   last failure. devloops writes it for each call.

You can replace the first three. The context always comes from devloops.
[Steps](../how-it-works/steps.md) explains what each step is given and what it must return.

## Replace a part

Put a file with the part's name in the project's `.devloops/prompts/` folder. devloops uses it
instead of the packaged part, for every loop and step that part belongs to:

| File | Replaces |
|---|---|
| `.devloops/prompts/common.md` | the shared rules |
| `.devloops/prompts/steps/<step>.md`, where `<step>` is one of [`plan`](../reference/steps.md#step-plan), [`replan`](../reference/steps.md#step-replan), [`author-checks`](../reference/steps.md#step-author-checks), [`implement`](../reference/steps.md#step-implement), [`fix`](../reference/steps.md#step-fix) or [`validate-ui`](../reference/steps.md#step-validate-ui) | that step's instructions |
| `.devloops/prompts/<loop>/Loop-instructions.md`, where `<loop>` is backend-dev or frontend-dev | that loop's instructions |

A file replaces the whole part; it is not added to it. So start from a copy of the packaged file
and edit the copy:

- in a checkout of devloops, the packaged files are in `loops/`: `loops/shared/prompts/common.md`,
  `loops/shared/prompts/steps/`, and `loops/backend-dev/` and `loops/frontend-dev/`;
- in an installed devloops, they are in the same places inside the `devloops_kit` Python package.

For example, to change the instructions of the `implement` step:

```sh
mkdir -p .devloops/prompts/steps
cp <checkout>/loops/shared/prompts/steps/implement.md .devloops/prompts/steps/implement.md
```

Then edit `.devloops/prompts/steps/implement.md`. Keep what the packaged file asks Claude Code
to return: devloops checks every answer against the step's expected form, and an answer that
does not match fails the [trial](../glossary.md#trial).

[`devloops init`](../reference/commands.md#init) creates the folder with a `README.md` that lists
these names. devloops never changes your files in it, not even when it
[upgrades](upgrades.md) the project.

## When an override applies

devloops reads the part files again for every call, so a change applies from the next call,
even in a run that is going on. Overrides are not fixed when a run starts, as its configuration
is.

devloops notices the change when a run is next started or resumed
([`devloops run`](../reference/commands.md#run), or
[`approve`](../reference/commands.md#approve) or [`retry`](../reference/commands.md#retry) when
they continue the run):

- That start records a `prompt-sources-changed` event in the run's
  [events](../reference/state-files.md#loop-state-events.jsonl), naming the parts that changed.
- [`devloops status`](../reference/commands.md#status) prints the changed parts ("prompt parts
  changed since the first run") until the loop completes.

[Milestones](../glossary.md#milestone) already achieved are never built again, so their prompts never change.

## See which parts a call used

Each call records, for each of its three parts, whether it came from the package or from an
override, the file's path, and a fingerprint of its content (its SHA-256 hash). These are in the
call's record in [`invocations.jsonl`](../reference/state-files.md#loop-state-invocations.jsonl),
and the [dashboard](dashboard.md) shows them with the call's prompt. The full prompt devloops sent
is kept too, in the loop's
[`state/prompts/`](../reference/state-files.md#loop-state-prompts-seq-step.md) folder.

## A misspelled name

Any other file in `.devloops/prompts/` replaces nothing and is ignored. So that a typo does not go
unnoticed, `devloops status` prints a warning that lists every such file. The folder's own
`README.md` is expected and never listed.
