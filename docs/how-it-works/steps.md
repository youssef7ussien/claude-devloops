---
title: Steps
description: >-
  Each call to Claude Code: why it exists, what it is given, what it may do, what it must return,
  and how devloops checks the answer.
sources:
  - loops/shared/devloops/claude.py
  - loops/shared/devloops/prompts.py
  - loops/shared/devloops/engine.py
  - loops/shared/devloops/plan.py
  - loops/shared/devloops/validators/curl.py
  - loops/shared/devloops/validators/playwright.py
  - loops/shared/prompts/common.md
  - loops/shared/prompts/steps
  - loops/backend-dev/loop.json
  - loops/frontend-dev/loop.json
  - loops/shared/hooks
  - spec 001 FR-025
  - spec 001 FR-069
  - spec 002 FR-030
  - spec 002 FR-031
---

# Steps

devloops never lets Claude Code run free. Each time it needs Claude, it makes one
[call](../glossary.md#call) of [headless Claude Code](../glossary.md#headless-claude-code) for one
[step](../glossary.md#step): a job with its own instructions, its own tools, and a fixed form for
the answer. There are six steps:

| Step | When it runs | Changes files |
|---|---|---|
| [`plan`](../reference/steps.md#step-plan) | Once, at the start of a loop | no |
| [`replan`](../reference/steps.md#step-replan) | When you ask for a new plan | no |
| [`author-checks`](../reference/steps.md#step-author-checks) | Once per backend [milestone](../glossary.md#milestone), before its code | no |
| [`implement`](../reference/steps.md#step-implement) | The first [trial](../glossary.md#trial) of a milestone | yes, in the [target](../glossary.md#target) |
| [`fix`](../reference/steps.md#step-fix) | Each later trial of a milestone | yes, in the target |
| [`validate-ui`](../reference/steps.md#step-validate-ui) | Each trial of a frontend milestone, to test it | no |

Only `implement` and `fix` write code. The other four only read, so a step that plans or tests can
never change what it plans or tests.

## How a step runs

Every step runs the same way:

```mermaid
flowchart LR
  parts["Prompt: shared rules + loop instructions + step instructions + context"] --> call[Call Claude Code]
  call --> answer[Answer]
  answer --> check{Matches the step's form?}
  check -- yes --> rules{Passes the step's own rules?}
  check -- no --> failed[Call failed]
  rules -- yes --> used[Answer used]
  rules -- no --> failed
  used --> record[Call recorded]
  failed --> record
```

**The prompt.** devloops builds each prompt from four parts, in this order:

1. The shared rules, the same for every step: work only on what the context asks for, write only
   inside the target, never stop a process by its name, record every
   [assumption](../glossary.md#assumption), and ask an [open question](../glossary.md#open-question)
   (with a [suggested answer](../glossary.md#suggested-answer)) instead of changing the
   requirements.
2. The loop's instructions: what [backend-dev](../glossary.md#backend-dev) or
   [frontend-dev](../glossary.md#frontend-dev) builds, and how.
3. The step's instructions: what to do, and what to return.
4. The context: a block of JSON with the facts of this call, such as the path of the
   [requirements](../glossary.md#requirements), the target folder, the milestone, and your approved answers.

You can replace any of the first three parts for a project. See [prompts](../guides/prompts.md).

**The call.** Claude Code runs in the target folder, with only the tools the step allows. It must
end with an answer in the step's form (a JSON schema that devloops hands to Claude Code). Two
settings bound every call: [`invocation_timeout_seconds`](../reference/configuration.md#invocation_timeout_seconds)
stops a call that takes too long, and
[`max_budget_usd_per_invocation`](../reference/configuration.md#max_budget_usd_per_invocation)
caps what one call may spend. Each step can run on its own model; see
[`models`](../reference/configuration.md#models).

**Checking the answer.** devloops checks the answer against the step's form again itself, then against the
step's own rules (each step below lists them). An answer that fails is never used. A call that
times out, crashes, or returns a bad answer fails the trial it belongs to. A call that fails
because Claude Code itself could not be reached (a service outage, a rate limit, an expired
login) does not count against the milestone: the trial is [`void`](../reference/statuses.md#trial-void)
and the run stops so you can fix the cause. See [trials and recovery](trials-and-recovery.md).

**The record.** Whatever happened, devloops records the call. It keeps:

- the exact prompt, with your secrets replaced by `***`, in
  [`<loop>/state/prompts/<seq>-<step>.md`](../reference/state-files.md#loop-state-prompts-seq-step.md);
- one line in [`<loop>/state/invocations.jsonl`](../reference/state-files.md#loop-state-invocations.jsonl)
  with the step, the milestone and trial, the model, the time taken, the tokens, the cost, how it
  ended, and where each prompt part came from;
- a copy of Claude Code's conversation, when Claude Code kept one, in
  [`<loop>/state/conversations/<seq>-<step>.jsonl`](../reference/state-files.md#loop-state-conversations-seq-step.jsonl).

The [dashboard](../guides/dashboard.md) shows all three for every call.

## What a step may do

The tools a step may use decide what it can change:

- **Steps that only read** (`plan`, `replan`, `author-checks`) may use `Read`, `Glob` and `Grep`.
  Claude Code's tools that write files, and its shell, are turned off.
- **`implement` and `fix`** may use the tools in [`implement_tools`](../reference/configuration.md#implement_tools):
  by default `Read`, `Edit`, `Write`, `Glob`, `Grep` and `Bash`, so they can write code and run
  commands such as a build or the tests. File edits are accepted without asking.
- **`validate-ui`** may use only `Read` and the browser tools of the Playwright MCP server.

Three guards keep writing inside the target, for the steps that write:

- Before each file edit or write by Claude Code's file tools, a hook checks the path. A write
  outside the target is blocked.
- Before each shell command, a hook blocks commands that stop processes by name or pattern
  (`pkill`, `killall`, and the like). Such a command could stop Claude Code's own call.
- After the call, devloops compares what the step must not change (devloops' own files, the
  loop's state, and the git status of the repositories around the target and the project) with
  how it was before. Any change fails the trial, whatever the answer says. This also catches a
  write made by a shell command. See [security](../guides/security.md).

Steps may always read the input files (the requirements, and for the frontend the backend's
OpenAPI document), even when they are outside the target.

## `plan` {#plan}

**Why it exists.** Before any code is written, devloops has the requirements turned into a
[plan](../glossary.md#plan) that can be built and checked piece by piece. See [the run lifecycle](run-lifecycle.md).

**What Claude is given.** The path of the requirements and what kind they are (a full product
description, one story, or a [spec-kit](../guides/spec-kit.md) feature), the target folder, the
[`runtime`](../reference/configuration.md#runtime) and [`backend`](../reference/configuration.md#backend)
settings, if any, and, for the frontend loop, the path of the backend's OpenAPI document with the
rule that the frontend may call only the operations it lists. When the run builds one
[story](../glossary.md#story), the context says which. When the last plan was rejected, the
context lists the reasons, so the next attempt can fix them.

**What it may do.** Read the requirements and any code already in the target. It writes nothing.

**What it must return.** A [plan](../glossary.md#plan) (see
[the fields of `plan.json`](../reference/state-files.md#loop-state-plan.json-fields)):

- an inventory of the requirements it covers, using the requirements' own identifiers;
- the technology to use, and where that choice came from: the code already in the target first,
  then the requirements or the settings, and otherwise a proposal;
- the [runtime](../glossary.md#runtime): how to start the application and where it answers;
- the milestones in order, each with its [tasks](../glossary.md#task) and
  [acceptance criteria](../glossary.md#acceptance-criterion): behaviour that can be seen from
  outside the code, never "it compiles";
- open questions, each with a suggested answer, and the assumptions the plan relies on.

**How devloops checks it.** Besides the form, the plan must hold together:

- every identifier (requirement, milestone, task, criterion, question, assumption) is unique;
- each task and criterion belongs to its milestone and cites a requirement from the inventory;
- each milestone depends only on milestones listed before it;
- a disagreement about the technology comes with at least one open question;
- the backend loop's runtime names where its OpenAPI document will be;
- when the run builds one story, all the work cites that story;
- for a spec-kit feature, every task in scope is planned or left out with a reason, and the
  milestones follow the feature's phases in order.

A plan that breaks a rule fails that planning trial, and the next one gets the reasons. A loop gets
[`max_trials`](../reference/configuration.md#max_trials) planning trials; when all fail, the loop
stops ([`planning-trials-exhausted`](../reference/statuses.md#stop-planning-trials-exhausted)).
A valid plan is stored and waits for [approval](../glossary.md#approval).

## `replan` {#replan}

**Why it exists.** After reading a plan and answering its questions, you may want a new plan built
on your answers instead of the one you have. [`devloops replan`](../reference/commands.md#replan)
asks for it.

**What Claude is given.** Everything `plan` gets, plus the path and the text of
`outputs/open-questions.md` with your answers, and the path of the previous plan. An empty answer
under a suggested answer means you accept the suggestion.

**What it may do.** Read, as `plan` does. It writes nothing.

**What it must return.** A complete plan, in the same form and under the same rules as `plan`. It
applies every answer, keeps what the answers do not affect, and drops the questions now answered.

**How devloops checks it.** As for `plan`. If no valid plan comes back within the planning trials,
the previous plan is kept and still waits for your approval.

## `author-checks` {#author-checks}

**Why it exists.** A backend milestone is tested with HTTP requests. If the requests were written
after the code, they could be written to fit the code. So devloops has them written first, from
the acceptance criteria alone, and then keeps them unchanged for every trial of the milestone.
These are the milestone's [checks](../glossary.md#check). This step runs only in the backend loop.

**What Claude is given.** The milestone (its title, goal and acceptance criteria), the runtime, the
target folder, and the backend's current OpenAPI document, if there is one yet.

**What it may do.** Read. It writes nothing and runs nothing.

**What it must return.** A list of checks (see
[the fields of `checks.json`](../reference/state-files.md#loop-state-milestones-id-checks.json-fields)).
Each check has an identifier, the acceptance criteria it is evidence for, the request to send
(method, path, headers, body), and the answer expected: the status code, and optionally text the
body must contain or exact values at given places in a JSON body. A check may also keep a value
from its answer, such as the identifier of an item it just created, for a later check to use.

**How devloops checks it.** Besides the form:

- each check's identifier is unique and made only of letters, digits, `_`, `.` and `-` (it names
  the check's evidence files);
- every acceptance criterion of the milestone is covered by at least one check.

Checks that break a rule fail the trial before any code is written, and the next trial writes
them again. Valid checks are saved in
[`checks.json`](../reference/state-files.md#loop-state-milestones-id-checks.json) and never
written again for that milestone. Whether each request is an operation the OpenAPI document
declares is checked later, during [validation](validation.md).

## `implement` {#implement}

**Why it exists.** It is where the code is written: the first trial of each milestone.

**What Claude is given.** The milestone with its goal, the tasks not achieved yet, and its
acceptance criteria; the plan's technology and runtime; the path of the requirements; the target
folder; your answers in `outputs/open-questions.md`; and the list of milestones already achieved,
which must keep working. The frontend loop also gets the path of the backend's OpenAPI document
and the rule that the frontend may call only the operations it lists.

**What it may do.** Change files in the target, and run commands to check its work, with the tools
in [`implement_tools`](../reference/configuration.md#implement_tools). It must stop every process
it started before it answers: devloops starts the application itself to validate it.

**What it must return.** A report of four parts:

- each task, marked `implemented` or `not-implemented`, with a short note;
- the assumptions it made, and what each affects;
- questions it could not settle without changing the requirements, each with a suggested answer
  and why;
- the files it changed.

**How devloops checks it.** Besides the form, the report decides nothing. A task Claude marks
`implemented` becomes [`implemented`](../reference/statuses.md#task-implemented), not achieved:
only validation achieves it. Next, devloops checks that nothing outside the target changed. Then,
if Claude asked questions, devloops either accepts the suggested answers and goes on (the default)
or stops for your answers (see [approval and questions](../guides/approval-and-questions.md)).
Then it [validates](validation.md) the milestone.

## `fix` {#fix}

**Why it exists.** When a trial fails validation, the next trial starts from that failure instead
of from nothing. Each trial after the first is a `fix`.

**What Claude is given.** Everything `implement` gets, plus the previous trial's failure: its
number, the reason, a summary of what failed, and the paths of its
[`validation.json`](../reference/state-files.md#loop-state-milestones-id-trials-n-validation.json)
and its [evidence](../glossary.md#evidence) folder (the requests and answers, screenshots, the application's output). When
you gave the milestone more trials with [`devloops retry`](../reference/commands.md#retry), the
[`--reason`](../reference/commands.md#retry--reason) you wrote comes too, as guidance.

**What it may do.** The same as `implement`. The acceptance criteria and the checks stay as they
are: a fix changes the code, never the test.

**What it must return.** The same report as `implement`.

**How devloops checks it.** As for `implement`. The last fix trial a milestone is allowed can run
on a stronger model, set with [`models.fix_last_trial`](../reference/configuration.md#models.fix_last_trial).

## `validate-ui` {#validate-ui}

**Why it exists.** A frontend milestone has to be tested in a real browser, and only Claude can
read a page and judge what it shows. So devloops gives that job to a separate call that can look
but not touch: it cannot change a file or run a command. This step runs only in the frontend loop,
as part of each trial's [validation](validation.md).

**What Claude is given.** The address of the user interface, which devloops has already started;
the backend's address, if one is running; the path of the backend's OpenAPI document; the
milestone and its acceptance criteria; the folder for the evidence; and, when the project has a
unit test command, the result of its unit tests, which devloops ran just before, so that a
criterion about them can be judged without running a command.

**What it may do.** Use the browser through the Playwright MCP server: open pages, click, type,
read, take screenshots. It may read files. It may not write or run anything.

**What it must return.** For each acceptance criterion: what it did, what it saw, whether that
meets the criterion, and the screenshots that show it. It does not report the page's requests to
the backend: devloops reads them from the browser's own network log.

**How devloops checks it.** devloops does not take the answer on trust. Every criterion must have
an entry with what was seen and evidence files that exist. The call must have used the browser and
tried no tool it was not allowed. And every request the page sent to the backend, read from the
browser's network log, must be an operation the OpenAPI document lists. See
[validation](validation.md).
