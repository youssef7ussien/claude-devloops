---
name: "devloops-run"
description: "Start or resume the devloops run in this project (backend-dev, then frontend-dev, as the project configures), then summarize its status; when it waits for a decision, ask the user and carry it out."
argument-hint: "[--workspace <ws>] [--speckit-feature [dir] | --requirements <file>] [--story-id <id>] [--target-root <dir>] [--backend-target <dir>] [--frontend-target <dir>] [--max-trials <n>] [--review-plan | --accept-suggested] [other run options]"
user-invocable: true
allowed-tools: Bash({{DEVLOOPS}} *), Read
---

## User Input

```text
$ARGUMENTS
```

Run this command through Bash from the project root, passing the user's arguments unchanged:

    {{DEVLOOPS}} run $ARGUMENTS --json

A run can take hours: let the command finish, in the background if it outlasts the Bash timeout.

Summarize: exit_code, message, the run's status (`run.status`), and for each loop in `loops` its
status, status_reason, next milestone and trials used, last failure, and artifacts, and any
warnings. Report the dashboard as the result gives it: `dashboard_url` when present (a dashboard
server is running). Without `dashboard_url`, say that `devloops dashboard` in a terminal (or
`devloops dashboard --daemon`) shows the run live; never state an address the result does not give, and never start a dashboard
server yourself. When the setup stops before anything runs (exit 30 with only `status_reason`: no
loop, or a frontend without a backend), report `status_reason.message`, which says how to fix it.
On a usage error (exit 2) the result is `{error, exit_code}`: report `error`, and do not guess
missing arguments.

## When the run waits for a decision

Only the stops below are decided here, and only with the user's answer. Ask with the
AskUserQuestion tool, and never decide for the user.

- **Exit 10 (`awaiting-approval`).** Read the waiting loop's `outputs/plan-summary.md` and
  `outputs/open-questions.md` (the `outputs/` folder beside its `progress` file). Show the
  milestones and each open question with its suggested answer. Ask: approve (an empty answer
  accepts the suggestion), replan, or stop here. Do not offer replan when the result's `message`
  says the planning trials are used up ("the previous plan still awaits approval"): `replan` is
  refused then. If the user gives their own answers, write each after its question's
  `**Answer:**` marker in `open-questions.md`, changing nothing else. Then run
  `{{DEVLOOPS}} approve --json` or `{{DEVLOOPS}} replan --json` (add the user's `--workspace`).
- **Exit 20 (`stopped-on-failure`) on a milestone**, that is with `status_reason.milestone_id`
  set (`trials-exhausted`, or `needs-input`). Show the milestone, why it stopped, and the last
  failure. For `needs-input`, show the new questions and record the user's answers as above. Ask
  whether to give it more trials, how many (default: the configured `max_trials`), and what
  guidance to give the next fix. Then run
  `{{DEVLOOPS}} retry --milestone <id> [--reason "<guidance>"] [--trials <n>] --json` (add the
  user's `--workspace`).

`approve`, `replan`, and `retry` continue the run and return the same result as `run`: summarize
it, and repeat this section while it waits for a decision again. If the user chooses to stop, say
which command continues later (`devloops approve`, `devloops replan`, or `devloops retry
--milestone <id>`).

Every other stop is reported, not decided: explain it from `status_reason` and the README's
recovery step, and do not re-run anything unless the user asks. In particular, exit 20 without a
milestone cannot be retried: `planning-trials-exhausted` is final (start a new workspace), and
`invocation-cap` means the run reached `max_invocations_per_run`. Otherwise: 30, an input or tool
to fix; 40, another driver holds the lock; 50, a service error with no trial used (run again to
resume).

Edit no file other than `open-questions.md` as above (Claude Code asks before that edit). This
skill holds no loop logic.
