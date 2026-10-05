---
name: "devloops-status"
description: "Show the status of the devloops loops in a workspace of this project (read-only)."
argument-hint: "[<backend-dev|frontend-dev>] [--workspace <ws>]"
user-invocable: true
allowed-tools: Bash({{DEVLOOPS}} *)
---

## User Input

```text
$ARGUMENTS
```

Run exactly one command through Bash from the project root, passing the user's arguments unchanged:

    {{DEVLOOPS}} status $ARGUMENTS --json

Summarize: each loop's status, status_reason, next milestone and trials used, last
failure, artifacts, large_evidence, and any warnings. This command changes nothing.

Do not approve, replan, retry, edit files, or re-run anything unless the user asks. On a usage
error, report it and do not guess missing arguments. This skill holds no loop logic.
