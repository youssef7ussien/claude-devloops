---
title: State and files
description: >-
  What devloops writes to disk, when, and why a run can resume from it.
sources:
  - loops/shared/devloops/workspace.py
  - loops/shared/devloops/state.py
  - loops/shared/devloops/claude.py
  - loops/shared/devloops/engine.py
  - loops/shared/devloops/orchestrator.py
  - loops/shared/devloops/redact.py
  - loops/shared/devloops/cli.py
  - docs-include/examples/workspace-files.txt
  - spec 001 FR-004
  - spec 001 FR-026
  - spec 001 FR-028
  - spec 003 FR-001
---

# State and files

devloops keeps everything it knows about a run in files. It holds nothing in memory that it has
not written down first. This is why you can stop a run at any moment and start it again, read
what happened long after it ended, or hand the whole record to someone else.

This page explains where those files live, what devloops writes and when, and why that is enough
to resume a run. The [state files reference](../reference/state-files.md) lists every file and
the fields of the main ones.

## Project, workspace and target

Three folders matter.

- The **[project](../glossary.md#project)** is the folder you set up with
  [`devloops init`](../reference/commands.md#init). It holds the configuration file
  `.devloops/devloops.json`, and usually your application's code. devloops finds the project
  by looking in the current folder, then in each folder above it, so every command works from
  anywhere inside the project.
- A **[workspace](../glossary.md#workspace)** is the folder that holds one run: its state, the
  record of every [call](../glossary.md#call) to Claude Code, the
  [evidence](../glossary.md#evidence) and the outputs. By default it is
  `.devloops/workspaces/main` in the project. To keep two runs apart, give each its own workspace
  with [`--workspace`](../reference/commands.md#run--workspace).
- A **[target](../glossary.md#target)** is the folder a [loop](../glossary.md#loop) writes the application's code to,
  such as `backend` or `frontend` in the project. Claude Code may change files only there.

The workspace and the target are separate on purpose. The target holds your application, which
you keep. The workspace holds devloops' record of how the application was built. `init` adds the
workspaces folder to `.gitignore` (unless you pass
[`--track-workspaces`](../reference/commands.md#init--track-workspaces)), so the record stays out of your repository unless you choose
to commit it.

The workspace stores the targets and the [requirements](../glossary.md#requirements) as paths
relative to the project when they are inside it. A project you move or clone still resumes where
it was.

## What a workspace holds

Here is every file in the workspace after the backend-only sample run used on this site: a [plan](../glossary.md#plan)
of two [milestones](../glossary.md#milestone), each passed on its first
[trial](../glossary.md#trial), and then a [dashboard](../glossary.md#dashboard)
[export](../glossary.md#export).

```text
--8<-- "examples/workspace-files.txt"
```

The files fall into a few groups:

| Folder | What it holds |
|---|---|
| the workspace itself | [`workspace.json`](../reference/state-files.md#workspace.json): which requirements and targets this workspace was started with. |
| `run/` | The run across its loops: [`run/state.json`](../reference/state-files.md#run-state.json) records each loop's status and the [handoff](../glossary.md#handoff) from the backend loop to the frontend loop. |
| `<loop>/state/` | One loop's state, written by devloops. Never edit it. |
| `<loop>/outputs/` | Readable pages made from the state: the plan, each milestone, the questions, the final report, and what the loop publishes. |
| `exports/` | Dashboard exports, one HTML file each, written by [`devloops dashboard --export`](../reference/commands.md#dashboard--export). |

A loop that the run does not include has no folder. In the sample, the project uses only the
backend loop, so there is no `frontend-dev/` folder. A frontend loop's folder has the same
shape, and its outputs hold `ui-url.txt` (the address of the user interface it built) instead of
an OpenAPI document.

## What devloops writes, and when

Each file is written at a known moment in the run.

**When the run starts**, devloops writes [`workspace.json`](../reference/state-files.md#workspace.json)
and the loop's [`run.json`](../reference/state-files.md#loop-state-run.json). `run.json` is the
heart of the state: the loop's status, the inputs with a fingerprint (a sha256 hash) of each, the
settings in effect, the approval, and each milestone's progress. The settings are frozen into it
on the first start. devloops also writes [`task.md`](../reference/state-files.md#loop-task.md),
the run's inputs in one page.

**When the plan is made**, devloops stores it in
[`plan.json`](../reference/state-files.md#loop-state-plan.json), and writes the readable
[`plan-summary.md`](../reference/state-files.md#loop-outputs-plan-summary.md), one
[`milestone-<NN>-<slug>.md`](../reference/state-files.md#loop-outputs-milestone-nn-slug.md) per
milestone, and [`open-questions.md`](../reference/state-files.md#loop-outputs-open-questions.md).

**For every call to Claude Code**, devloops keeps three things, numbered in the order the calls
were made:

- the exact prompt it sent, in [`state/prompts/`](../reference/state-files.md#loop-state-prompts-seq-step.md),
  with the Claude Code settings the call ran with beside it;
- one line in [`invocations.jsonl`](../reference/state-files.md#loop-state-invocations.jsonl):
  the [step](../glossary.md#step), the milestone and trial, when it ran, the tokens and cost, and how it ended;
- a copy of Claude Code's own conversation, in
  [`state/conversations/`](../reference/state-files.md#loop-state-conversations-seq-step.jsonl).

**For each milestone**, the backend loop first stores the milestone's
[checks](../glossary.md#check) in
[`checks.json`](../reference/state-files.md#loop-state-milestones-id-checks.json). They are
written before any of the milestone's code, and stay the same for every trial.

**For each trial**, devloops writes a folder under `state/milestones/<id>/trials/<n>/`:

- [`trial.json`](../reference/state-files.md#loop-state-milestones-id-trials-n-trial.json):
  whether the trial wrote the code or fixed it, its status, its calls, what Claude reported, and
  why it failed, if it did;
- [`validation.json`](../reference/state-files.md#loop-state-milestones-id-trials-n-validation.json):
  each check and [acceptance criterion](../glossary.md#acceptance-criterion), passed or failed;
- [`runtime.log`](../reference/state-files.md#loop-state-milestones-id-trials-n-runtime.log):
  what the application printed while it was validated;
- an `evidence/` folder with what validation saw. For the backend, that is each check's curl
  command, the body it sent (if any), and the headers and body of the answer. For the frontend, it holds screenshots and
  the browser's record of network requests, and the trial folder also keeps the stream of the
  call that drove the browser (`stream.jsonl`).

**When a milestone passes**, the backend loop publishes its OpenAPI document as
[`outputs/openapi.json`](../reference/state-files.md#loop-outputs-openapi.json), listing only the
operations its validation called.

**When the loop completes**, devloops writes
[`final-report.md`](../reference/state-files.md#loop-outputs-final-report.md).

**All the time**, devloops adds one line to
[`events.jsonl`](../reference/state-files.md#loop-state-events.jsonl) for each thing that
happens (the run started, the plan was stored, a trial started, validation passed or failed), and
every progress line to [`run.log`](../reference/state-files.md#loop-state-run.log). It rewrites
[`progress.md`](../reference/state-files.md#loop-progress.md) and
[`run/progress.md`](../reference/state-files.md#run-progress.md) as the run goes.

Two files exist only while a loop runs: `lock`, which stops a second devloops from running the
same loop at once, and `live.json`, the call running now, which the dashboard shows. Both are in
the loop's `state/` folder.

### Outputs are made from the state

Everything in `outputs/`, and `progress.md`, is made from the files in `state/`. If an output
and the state disagree, the state is right. The one exception is `open-questions.md`: you write
your answers there, and devloops reads them.

### Secrets are removed before anything is written

If you list secrets in the configuration ([`secrets.env`](../reference/configuration.md#secrets.env)
for the names of environment variables, [`secrets.literals`](../reference/configuration.md#secrets.literals)
for values), devloops replaces each of them with `***` before it writes a prompt, a call record,
a conversation, evidence, a question or a report. It only knows the secrets you list, so review
a workspace before you share or commit it.
[`devloops status`](../reference/commands.md#status) lists evidence files over 1 MB, since large
files are the likeliest place for a secret to hide.

### Every call as a spreadsheet

[`devloops export-sessions`](../reference/commands.md#export-sessions) writes every call to
Claude Code in the workspace as CSV, one row per call, from each loop's
[`invocations.jsonl`](../reference/state-files.md#loop-state-invocations.jsonl), loop by loop and
in call order. It prints to the terminal, or writes the file you name with
[`--csv`](../reference/commands.md#export-sessions--csv). The columns are `workspace`, `loop`,
`step`, `model`, `milestone`, `trial`, `session_id`, `prompt_path` (relative to the workspace),
`input_tokens`, `output_tokens`, `cache_creation_tokens`, `cache_read_tokens`, `cost_usd`,
`started_at` and `ended_at`. A value Claude Code did not report is left empty, and so is `model`
when the call used Claude Code's default model. It is useful to compare models or steps in a
spreadsheet.

## Why a run can resume

Two rules make the files enough to resume a run.

**devloops writes before it acts.** It records a trial as started before it calls Claude Code,
and records each result before it moves on. So the state never claims less than what happened.

**A write is never half done.** devloops writes each JSON file of the state, such as `run.json`,
`plan.json` and `trial.json`, to a temporary file in the same folder, makes sure it is on disk,
and then puts it in place of the old one in a single step. A
crash at any moment leaves either the old file or the new one, never a broken one. Lines added
to the `.jsonl` logs are written and flushed to disk one at a time.

So when you run [`devloops run`](../reference/commands.md#run) again after a stop, a crash or a
reboot, devloops reads `run.json` and carries on from the status it finds:

- A trial that was still running when devloops stopped is marked
  [failed](../reference/statuses.md#trial-failed), with the reason
  `interrupted`. It counts as one of the milestone's
  trials, and the next trial fixes the code with that failure as its starting point.
- A trial that ended because Claude Code was unavailable, rate limited or logged out is
  [void](../reference/statuses.md#trial-void): it does not count, and the next trial reuses its
  number. See [trials and recovery](trials-and-recovery.md).
- devloops compares the fingerprints of the requirements and other inputs with the ones in
  `run.json`. If they changed, the run stops with the reason
  [`input-changed`](../reference/statuses.md#stop-input-changed) rather than build on requirements
  it did not plan for.
- A loop that is already completed is not run again.

If a run was killed so hard that its lock was left behind, devloops reports it with
[exit code 40](../reference/exit-codes.md#exit-40). When you are sure no other devloops is
running, [`--force-unlock`](../reference/commands.md#run--force-unlock) removes the lock.
