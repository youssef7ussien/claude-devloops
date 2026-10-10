---
title: Approval and questions
description: >-
  Review a plan, answer Claude's open questions, approve or replan, retry a stopped milestone,
  and review the suggested answers devloops accepted for you.
sources:
  - loops/shared/devloops/engine.py
  - loops/shared/devloops/cli.py
  - loops/shared/devloops/render.py
  - loops/shared/devloops/orchestrator.py
  - loops/shared/prompts/common.md
  - loops/shared/devloops/assets/app/views/questions.js
  - spec 001 FR-051a
  - spec 001 FR-053
  - spec 001 FR-055a
  - spec 001 FR-058
  - spec 001 FR-061
  - spec 001 FR-063
  - spec 003 FR-009
  - spec 003 FR-010
---

# Approval and questions

No code is written until a [plan](../glossary.md#plan) is [approved](../glossary.md#approval).
Where the requirements leave something open, Claude Code asks an
[open question](../glossary.md#open-question), usually with a
[suggested answer](../glossary.md#suggested-answer). This page shows how to review a plan, answer
those questions, and decide what happens next: approve, plan again, or retry a
[milestone](../glossary.md#milestone) that stopped.

For where approval fits in a run, see [the run lifecycle](../how-it-works/run-lifecycle.md).

## Why Claude asks

Claude Code settles every unclear point it can within the requirements, and records each such
decision as an [assumption](../glossary.md#assumption). It asks a question only when every
possible answer would add, remove or contradict a requirement. So each question is a decision
about the product, which is yours to make. Each comes with the answer Claude suggests and why, so
devloops can go on without you and you can review the decision afterwards.

## Who answers: the `questions` setting

The [`questions`](../reference/configuration.md#questions) setting decides whether devloops waits
for you:

| `questions` | A new plan | A question while a milestone is built |
|---|---|---|
| `accept-suggested` (the default) | Approved at once, with the suggested answers | The suggested answer is accepted, and the [trial](../glossary.md#trial) is validated as Claude built it |
| `ask` | The run pauses until you approve it or ask for a new plan | The milestone stops at once until you answer and retry |

[`--review-plan`](../reference/commands.md#run--review-plan) sets `ask`, and
[`--accept-suggested`](../reference/commands.md#run--accept-suggested) sets `accept-suggested`.
Given to any command of a run, the choice is recorded in
[`run/state.json`](../reference/state-files.md#run-state.json) and holds for the rest of the run:
the [frontend loop](../glossary.md#frontend-dev), which often starts in a later command, uses it
too. When no choice is recorded there and the backend loop has already started, the frontend
loop takes the backend's setting.
Under both settings, a question with no suggested answer pauses the plan, or stops the milestone,
because there is nothing to accept.

## Reviewing a plan

A stored plan comes with three kinds of file in the loop's `outputs/` folder:

- [`plan-summary.md`](../reference/state-files.md#loop-outputs-plan-summary.md): the stack and
  where it came from, the [runtime](../glossary.md#runtime), and the list of milestones.
- One [`milestone-NN-slug.md`](../reference/state-files.md#loop-outputs-milestone-nn-slug.md)
  per milestone: its tasks and [acceptance criteria](../glossary.md#acceptance-criterion).
- [`open-questions.md`](../reference/state-files.md#loop-outputs-open-questions.md): Claude's
  questions, each with its suggested answer and why.

Each question in `open-questions.md` ends with an `**Answer:**` line. Leave it empty to accept
the suggestion, or write your own answer after it.

### In a terminal

When a run pauses for review in a terminal (under `ask`, or for a question with no suggested
answer), devloops shows the size of the plan, where to read it, and asks:

```text
[a]pprove  [e]dit answers  [r]eplan  [q]uit:
```

- `a` approves the plan and keeps building.
- `e` opens `open-questions.md` in the editor named by `$VISUAL` or `$EDITOR` (or waits while
  you edit it), then asks again.
- `r` plans again with your answers.
- `q` exits with [exit code 10](../reference/exit-codes.md#exit-10); approve later with
  `devloops approve`.

Without a terminal (in a script, in CI, or with `--json`), a run that pauses for review exits
with code 10 and never asks.

### `devloops approve`

[`devloops approve`](../reference/commands.md#approve) accepts the plan with your answers, then
continues the run in the same command. Each suggestion you left unanswered is copied into its
answer and marked with an `**Answer source:**` line, so the file says exactly what the run uses.
From then on, the answers are part of every prompt.

Once a plan is approved, devloops records a fingerprint of `open-questions.md`. Editing the file
afterwards stops the run with
[`input-changed`](../reference/statuses.md#stop-input-changed), except just before a
`devloops retry`, which records the file as it is then.

### `devloops replan`

[`devloops replan`](../reference/commands.md#replan) asks Claude Code to plan again, with your
answers and the previous plan. This uses one planning [trial](../glossary.md#trial). Write your
feedback as answers in `open-questions.md` first.

After `replan`, the new plan is handled like the first. Under `ask` it pauses for review; under
`accept-suggested` it is approved and built. With `--no-continue`, it always pauses for review.
If no valid plan comes back within the planning trials, the previous plan is kept, and still
waits for approval.

A plan can be replanned only while it waits for approval. To build again from different answers
after that, start a new [workspace](../glossary.md#workspace) with
[`--workspace`](../reference/commands.md#run--workspace).

## Questions while a milestone is built

When the code Claude writes needs a decision the requirements do not make, the `implement` or
`fix` call returns a question with a suggested answer, and Claude builds the rest of the milestone
on that suggestion. devloops adds the question to `open-questions.md` as a new entry, numbered
after the ones already there (`OQ4` after `OQ3`).

- **Under `accept-suggested`**, devloops accepts the suggestion and validates the trial as it was
  built. If validation fails, the next trial gets the answer. The acceptance is recorded in the
  loop's [`run.json`](../reference/state-files.md#loop-state-run.json) (its `auto_answers` list)
  and as an `answers-accepted` event. If the milestone later runs out of trials, the stop message
  names these questions, because its trials were built on them: check them before a retry.
- **Under `ask`, or with no suggestion**, the milestone stops at once, with
  [`needs-input`](../reference/statuses.md#stop-needs-input) and
  [exit code 20](../reference/exit-codes.md#exit-20). Answer the question (an empty answer
  accepts the suggestion), then run `devloops retry --milestone <id>`.

[Trials and recovery](../how-it-works/trials-and-recovery.md) explains how a question fits into
a milestone's trials.

## `devloops retry`

[`devloops retry`](../reference/commands.md#retry) gives a milestone that stopped more trials:

```sh
devloops retry --milestone M03 --reason "the list must be sorted by name"
```

- [`--milestone`](../reference/commands.md#retry--milestone) names the milestone that stopped.
- [`--reason`](../reference/commands.md#retry--reason) is optional guidance; the next trial's
  prompt includes it.
- [`--trials`](../reference/commands.md#retry--trials) sets how many more trials to give
  (by default, as many as [`max_trials`](../reference/configuration.md#max_trials)).

`retry` works only when the loop is
[`stopped-on-failure`](../reference/statuses.md#loop-stopped-on-failure) and that milestone has
failed. After a question stopped the milestone, `retry` refuses while a question has neither an
answer nor a suggestion. A run that stopped because planning failed, or because it reached its
limit of calls to Claude Code, cannot be retried: start a new workspace.

## What the three decisions have in common

`approve`, `replan` and `retry` take no loop name: each acts on the one loop waiting for that
decision. Each records the decision, then continues the whole run, as `devloops run` would, until
it completes, stops, or pauses again. Retrying a backend milestone, for example, finishes the
backend, then plans and builds the frontend. The command exits with the run's code and prints
the same summary as `devloops run`:

```text
--8<-- "examples/approve.txt"
```

A decision that is refused changes nothing and runs nothing. It exits with
[code 2](../reference/exit-codes.md#exit-2) when nothing waits for that decision, with
[code 40](../reference/exit-codes.md#exit-40) when another devloops command holds the
workspace, and with [code 30](../reference/exit-codes.md#exit-30) when a tool the run needs is
missing, so a decision is never recorded for a run that cannot go on.

With [`--no-continue`](../reference/commands.md#approve--no-continue), the command only records
the decision, and the next `devloops run` continues. Use it to grant several retries before
continuing, or in a script that must not wait: without it, the command runs until the loop ends,
which can take hours. `--review-plan` and `--accept-suggested` are refused with `--no-continue`;
give them to that next `devloops run`.

## Reviewing the suggested answers devloops accepted

Under `accept-suggested`, devloops decides for you, so review those decisions as you would
assumptions. Every suggestion it accepted:

- is marked in `open-questions.md` with an `**Answer source:**` line saying it was accepted
  automatically;
- is listed first in [`final-report.md`](../reference/state-files.md#loop-outputs-final-report.md),
  under **Suggested answers accepted**, next to **Assumptions for review**;
- is shown in the dashboard's questions view (see [the dashboard](dashboard.md)).

To change a decision, start a new workspace with your answer written into the requirements. If
the run is stopped on a failure, you can also rewrite the answer before a `retry`, which uses the
file as it is then.
