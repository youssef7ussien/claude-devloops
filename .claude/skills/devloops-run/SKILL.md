---
name: "devloops-run"
description: "Start or resume one devloops loop (backend-dev or frontend-dev) in this project, then summarize its status."
argument-hint: "<backend-dev|frontend-dev> [--speckit-feature [dir] | --requirements <file>] [--story-id <id>] [other run options]"
user-invocable: true
allowed-tools: Bash(bin/devloops *)
---

## User Input

```text
$ARGUMENTS
```

Run exactly one command through Bash from the project root, passing the user's arguments unchanged:

    bin/devloops run $ARGUMENTS --json

Summarize: exit_code, message, status, status_reason, next milestone and trials used, last
failure, artifacts, the dashboard and full-dashboard paths, and any warnings. Explain what the exit
code asks of the user (10: review outputs/ and answer open-questions.md, then approve or replan,
which continue the run; 20/30/40/50: the stop reason and the README's recovery step).

Do not approve, replan, retry, edit files, or re-run anything unless the user asks. On a usage
error, report it and do not guess missing arguments. This skill holds no loop logic.
