---
name: "devloops-retry"
description: "Grant the failed milestone of the loop stopped on failure more trials and continue the run, then summarize its status."
argument-hint: "--milestone <M01> [--reason \"<guidance>\"] [--trials <n>] [--workspace <ws>] [--no-continue] [--review-plan | --accept-suggested]"
user-invocable: true
allowed-tools: Bash({{DEVLOOPS}} *)
---

## User Input

```text
$ARGUMENTS
```

Run exactly one command through Bash from the project root, passing the user's arguments unchanged:

    {{DEVLOOPS}} retry $ARGUMENTS --json

Summarize: exit_code, message, and any warnings. When the run continued, the result names the loop
decided (`decision.loop`), the run's status (`run.status`), and for each loop in `loops` its
status, status_reason, next milestone and trials used, last failure, and artifacts, with the
dashboard and full-dashboard paths. With --no-continue, the result is that one loop's status
(`loop`, `status`, `status_reason`, next milestone and trials used, last failure, artifacts) with
the dashboard and full-dashboard paths; the next `devloops run` continues. When the run's setup
stops before anything runs (exit 30 with only `status_reason`), report that message and its fix. On
a usage error (exit 2) the result is `{error, exit_code}`: report `error` (for example, no loop is
stopped on failure). Explain what the exit code asks of the user (10: review the waiting loop's
outputs/ and answer open-questions.md, then approve or replan, which continue the run; 20/30/40/50:
the stop reason and the README's recovery step).

devloops finds the loop stopped on failure itself: never ask the user for a loop name, and never
add one. Do not approve, replan, retry, edit files, or re-run anything else unless the user asks.
On a usage error, report it and do not guess missing arguments. This skill holds no loop logic.
