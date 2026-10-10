---
title: spec-kit features
description: >-
  Use a spec-kit feature folder as the requirements: which files devloops reads, how the plan
  follows tasks.md, and how to build one user story.
sources:
  - loops/shared/devloops/speckit.py
  - loops/shared/devloops/inputs.py
  - loops/shared/devloops/plan.py
  - loops/shared/devloops/render.py
  - loops/shared/devloops/initcmd.py
  - spec 002 FR-023
  - spec 002 FR-024
  - spec 002 FR-025
  - spec 002 FR-026
---

# spec-kit features

[spec-kit](https://github.com/github/spec-kit) is a way of writing a feature down before building
it: a folder with the specification (`spec.md`), a technical plan (`plan.md`) and a task list
(`tasks.md`). devloops can use such a folder as its [requirements](../glossary.md#requirements),
instead of a single Markdown file. devloops only reads spec-kit's files; it never runs spec-kit.

## Use a feature

Give the folder to [`devloops run`](../reference/commands.md#run) with
[`--speckit-feature`](../reference/commands.md#run--speckit-feature):

```sh
devloops run --speckit-feature specs/003-billing
devloops run --speckit-feature        # the active feature
```

With no folder, devloops uses the active feature: the folder named by `feature_directory` in the
project's `.specify/feature.json`, the file spec-kit keeps.

To set it once for the project, put it in the
[`requirements.speckit_feature`](../reference/configuration.md#requirements.speckit_feature)
setting of `.devloops/devloops.json`, as a folder or as `"active"`.
[`devloops init`](../reference/commands.md#init) writes `"active"` there by itself when the project
has an active feature, or a folder given with
[`--speckit-feature`](../reference/commands.md#init--speckit-feature).

## Which files devloops reads

- **`spec.md`** is the requirements. A feature folder without it stops the run with
  [`missing-input`](../reference/statuses.md#stop-missing-input).
- **`plan.md`**, when there is one, is the feature's technical plan. Its stack counts as named in
  the requirements, so devloops' plan uses that stack instead of choosing one.
- **`tasks.md`**, when there is one, decides the shape of devloops' plan (see below).

devloops records a fingerprint of each of these files when the run starts. If any of them changes
later, or a `plan.md` or `tasks.md` appears that was not there at the start, the run stops with
[`input-changed`](../reference/statuses.md#stop-input-changed): its plan was made from the old
files. Restore them, or start a new [workspace](../glossary.md#workspace).

## How the plan follows tasks.md

With a `tasks.md`, devloops' [plan](../glossary.md#plan) follows its phases (its
`## Phase <n>: <title>` headings), in order, with one or more
[milestones](../glossary.md#milestone) for each phase. Each task in the plan names the spec-kit
tasks (`T001`, `T002`, …) it does.

devloops checks this when the plan is made. A plan fails its planning
[trial](../glossary.md#trial), and Claude Code is asked again, when:

- it names a spec-kit task that is not in `tasks.md`;
- a spec-kit task is neither planned nor left out with a reason (for example "frontend task", in
  the backend loop);
- its milestones do not follow the order of the phases.

A task marked done in `tasks.md` (`- [x]`) is not skipped: devloops asks Claude Code to plan it
anyway, unless the code shows it is done, because a mark is not proof that the code exists.

## Build one user story

[`--story-id`](../reference/commands.md#run--story-id) limits the run to one user [story](../glossary.md#story):

```sh
devloops run --speckit-feature specs/003-billing --story-id US2
```

`US2` selects the `User Story 2` heading of `spec.md`. With a `tasks.md`, the story's work is its
tasks labelled `[US2]`, plus the setup or foundational tasks (those with no story label) it needs.
A plan that uses a task of another story fails its trial. A story ID with no matching heading
stops the run with [`story-not-found`](../reference/statuses.md#stop-story-not-found).

## Review the coverage

With a `tasks.md`, the plan summary,
[`plan-summary.md`](../reference/state-files.md#loop-outputs-plan-summary.md), has a "Spec-kit
tasks" section. It lists:

- the spec-kit tasks planned, and the plan's tasks that do each;
- the spec-kit tasks left out, and why;
- for one story, the setup and foundational tasks it needs, and the other stories' tasks, which
  are out of scope;
- the plan's tasks that do no spec-kit task;
- the tasks already marked done in `tasks.md`.

Read it when you [review the plan](approval-and-questions.md): it shows every difference between
spec-kit's task list and what devloops will build.
