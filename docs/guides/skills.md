---
title: Claude Code skills
description: >-
  The two skills devloops init installs, what each does, and when to use them instead of the
  commands.
sources:
  - loops/shared/skills/devloops-run/SKILL.md
  - loops/shared/skills/devloops-status/SKILL.md
  - loops/shared/devloops/initcmd.py
  - spec 002 FR-021
  - spec 002 FR-022
  - spec 002 FR-022a
  - spec 002 FR-022b
---

# Claude Code skills

A skill is a set of instructions Claude Code follows when you call it by name, such as
`/devloops-run`, in a normal (interactive) Claude Code session. [`devloops init`](../reference/commands.md#init)
installs two in your [project](../glossary.md#project), in `.claude/skills/`. They let you start
and follow a run without leaving Claude Code.

Each skill runs one devloops command and reports the result in plain words. Neither holds any of
devloops' logic: the commands do the work, so a run started from a skill behaves exactly like one
started in a terminal.

## devloops-run

`/devloops-run` starts or resumes the run, as [`devloops run`](../reference/commands.md#run)
does, and takes the same options, for example `/devloops-run --review-plan`. When the command
ends, the skill summarizes it: the run's status, each loop's status and next milestone, the last
failure, and what the run published.

When the run waits for a decision, the skill asks you, then carries out your answer:

- **The plan waits for approval** ([exit code 10](../reference/exit-codes.md#exit-10)). It shows
  the milestones and each [open question](../glossary.md#open-question) with its
  [suggested answer](../glossary.md#suggested-answer), and asks whether to approve, plan again,
  or stop. Answers you give are written into `open-questions.md`. Then it runs
  [`devloops approve`](../reference/commands.md#approve) or
  [`devloops replan`](../reference/commands.md#replan).
- **A milestone stopped** ([exit code 20](../reference/exit-codes.md#exit-20), with the reason
  [`trials-exhausted`](../reference/statuses.md#stop-trials-exhausted) or
  [`needs-input`](../reference/statuses.md#stop-needs-input)). It shows the milestone, why it
  stopped and its last failure, records your answers to any new question, and asks how many more
  [trials](../glossary.md#trial) to give and what guidance to pass on. Then it runs
  [`devloops retry`](../reference/commands.md#retry).

Each of these commands continues the run, so the skill repeats this until the run completes,
stops for another reason, or you choose to stop; it then names the command that continues later.
Every other stop it explains, without running anything. It never starts the
[dashboard](../glossary.md#dashboard): run [`devloops dashboard`](../reference/commands.md#dashboard)
in a terminal to watch the run.

A run can take hours. The skill lets the command run to the end, in the background if needed.

## devloops-status

`/devloops-status` runs [`devloops status`](../reference/commands.md#status) and summarizes where
the run stands. It changes nothing.

## Skills or commands?

Use the skills when you already work in Claude Code and want it to walk you through the
decisions. Use the commands in a terminal for everything else, and for what the skills do not do:
the dashboard, [`devloops check`](../reference/commands.md#check), and decisions you want to make
yourself, such as approving a plan after editing several answers.

## Permissions

Claude Code asks before it runs a command, unless a rule allows it. Each skill allows the one
devloops command it needs, and `devloops-run` also allows reading the plan it shows you. Claude
Code still asks before the skill writes your answers into `open-questions.md`.

To let Claude Code run devloops without asking outside the skills too, run:

```sh
devloops init --allow-skills
```

[`--allow-skills`](../reference/commands.md#init--allow-skills) adds the rule `Bash(devloops *)`
(with the checkout's path in place of `devloops` when you set the project up from a checkout)
to `permissions.allow` in `.claude/settings.json`, keeping every other setting. It works on a
project that is already set up. If the settings file is not valid JSON, devloops leaves it alone,
exits with [code 30](../reference/exit-codes.md#exit-30), and prints the rule so you can add it by
hand. Without the option, `devloops init` never changes Claude Code's settings.

## Which devloops the skills call

The skills call `devloops` when it is installed. When `devloops init` ran from a checkout
(`bin/devloops`), they call that file by its full path instead (or by its path from the project root, when the
checkout is inside the project), so they keep working without an install. If you later install devloops, or move the checkout,
[`devloops init --upgrade`](upgrades.md) writes the skills again with the new command.
