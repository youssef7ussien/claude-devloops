---
title: Statuses
description: >-
  Every status devloops records, and every reason a loop stops.
generated: true
---

# Statuses

!!! note "Generated page"
    This page is generated from devloops' code; do not edit it. Change the code (or
    `tools/docs/descriptions.json`), then run `python3 tools/docs/gen_reference.py`.

Each kind of thing devloops tracks has its own statuses. [How it works: statuses](../how-it-works/statuses.md) shows how one leads to the next.

## Run {#run}

The whole run, across its loops (`run/state.json`).

| Status | Meaning |
|---|---|
| <span id="run-running"></span>`running` | A devloops command is working on the run's loops. |
| <span id="run-paused"></span>`paused` | A loop is waiting for you to review its plan or answer a question. |
| <span id="run-stopped"></span>`stopped` | A loop stopped, or the command was interrupted. Running devloops run again resumes it. |
| <span id="run-completed"></span>`completed` | Every loop the run includes is completed. |

## Loop {#loop}

One loop's run (`<loop>/state/run.json`).

| Status | Meaning |
|---|---|
| <span id="loop-not-started"></span>`not-started` | The loop has no run in this workspace yet. |
| <span id="loop-planning"></span>`planning` | The plan step is writing the plan. |
| <span id="loop-awaiting-approval"></span>`awaiting-approval` | The plan is written and waits for your review. |
| <span id="loop-implementing"></span>`implementing` | The plan is approved and milestones are being built, one at a time. |
| <span id="loop-completed"></span>`completed` | Every milestone of the plan is achieved. |
| <span id="loop-stopped-on-failure"></span>`stopped-on-failure` | The loop stopped because something failed: a milestone ran out of trials, the plan could not be made, a question needs an answer, or the call limit was reached. |
| <span id="loop-stopped-on-input-error"></span>`stopped-on-input-error` | The loop stopped because an input is missing, wrong, or changed. |
| <span id="loop-stopped-on-service-error"></span>`stopped-on-service-error` | The loop stopped because Claude Code could not be used. Running again resumes where it was. |

## Milestone {#milestone}

One milestone of the plan.

| Status | Meaning |
|---|---|
| <span id="milestone-pending"></span>`pending` | Not started yet. |
| <span id="milestone-in-progress"></span>`in-progress` | A trial is building or validating it. |
| <span id="milestone-achieved"></span>`achieved` | A trial passed validation. It is never run again. |
| <span id="milestone-failed"></span>`failed` | Every allowed trial failed. A retry grant sets it back to in-progress. |

## Task {#task}

One task of a milestone.

| Status | Meaning |
|---|---|
| <span id="task-pending"></span>`pending` | Not done yet. |
| <span id="task-implemented"></span>`implemented` | Claude Code reports it done; validation has not confirmed it yet. |
| <span id="task-achieved"></span>`achieved` | Its milestone passed validation. |
| <span id="task-failed"></span>`failed` | Its milestone ran out of trials before the task was achieved. |

## Trial {#trial}

One attempt at a milestone, or at the plan.

| Status | Meaning |
|---|---|
| <span id="trial-in-progress"></span>`in-progress` | Claude Code is working, or devloops is validating the result. |
| <span id="trial-passed"></span>`passed` | Validation passed. |
| <span id="trial-failed"></span>`failed` | Validation failed, or the call failed in a way that counts against the milestone. |
| <span id="trial-void"></span>`void` | The trial did not count, for example because Claude Code was unavailable. It uses up no trial. |

## Plan approval {#approval}

How the plan was approved, or sent back.

| Status | Meaning |
|---|---|
| <span id="approval-approve"></span>`approve` | You approved the plan with devloops approve. |
| <span id="approval-replan"></span>`replan` | You asked for a new plan with devloops replan. |
| <span id="approval-auto-approve"></span>`auto-approve` | devloops approved the plan by itself and accepted Claude's suggested answers (questions: accept-suggested). |

## Stop reasons {#stop-reasons}

When a loop stops, its status says how (`stopped-on-…`) and its reason says why.

| Reason | Meaning |
|---|---|
| <span id="stop-trials-exhausted"></span>`trials-exhausted` | A milestone used all its trials without passing validation. |
| <span id="stop-planning-trials-exhausted"></span>`planning-trials-exhausted` | The plan step did not produce a usable plan within its trials. |
| <span id="stop-invocation-cap"></span>`invocation-cap` | The run reached its limit of calls to Claude Code (max_invocations_per_run). |
| <span id="stop-needs-input"></span>`needs-input` | Claude Code asked a question that needs your answer before the work can go on. |
| <span id="stop-missing-input"></span>`missing-input` | A file the run needs, such as the requirements, is missing or empty. |
| <span id="stop-story-not-found"></span>`story-not-found` | The story named with --story-id is not in the requirements. |
| <span id="stop-invalid-api-spec"></span>`invalid-api-spec` | The OpenAPI document the frontend loop builds against is not a valid OpenAPI document. |
| <span id="stop-missing-tool"></span>`missing-tool` | A program the loop needs is not installed: Claude Code, curl, or the Playwright MCP server. |
| <span id="stop-input-changed"></span>`input-changed` | An input the run started with, such as the requirements or the plan, changed since. |
| <span id="stop-workspace-mismatch"></span>`workspace-mismatch` | The workspace belongs to another target or project than the one given. |
| <span id="stop-target-unwritable"></span>`target-unwritable` | The target folder cannot be created or written to. |
| <span id="stop-service-unavailable"></span>`service-unavailable` | Claude Code's service did not answer. |
| <span id="stop-rate-limited"></span>`rate-limited` | Claude Code refused calls for a while because too many were made. |
| <span id="stop-auth-failed"></span>`auth-failed` | Claude Code is not logged in, or its login expired. |
| <span id="stop-interrupted"></span>`interrupted` | The run was stopped with Ctrl+C while planning or implementing; running again resumes it. |
