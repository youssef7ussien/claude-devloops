---
name: "devloops-run"
description: "Start or resume the devloops run in this project (backend-dev, then frontend-dev, as the project configures), then summarize its status."
argument-hint: "[--workspace <ws>] [--speckit-feature [dir] | --requirements <file>] [--story-id <id>] [--target-root <dir>] [--backend-target <dir>] [--frontend-target <dir>] [--max-trials <n>] [--review-plan | --accept-suggested] [other run options]"
user-invocable: true
allowed-tools: Bash({{DEVLOOPS}} *)
---

## User Input

```text
$ARGUMENTS
```

Run exactly one command through Bash from the project root, passing the user's arguments unchanged:

    {{DEVLOOPS}} run $ARGUMENTS --json

Summarize: exit_code, message, the run's status (`run.status`), and for each loop in `loops` its
status, status_reason, next milestone and trials used, last failure, and artifacts; then the
dashboard and full-dashboard paths, and any warnings. When the setup stops before anything runs
(exit 30 with only `status_reason`: no loop, or a frontend without a backend), report that message
and its fix. On a usage error (exit 2) the result is `{error, exit_code}`: report `error`. Explain
what the exit code asks of the user (10: review the waiting loop's outputs/ and answer
open-questions.md, then approve or replan, which continue the run; 20/30/40/50: the stop reason and
the README's recovery step).

Do not approve, replan, retry, edit files, or re-run anything unless the user asks. On a usage
error, report it and do not guess missing arguments. This skill holds no loop logic.
