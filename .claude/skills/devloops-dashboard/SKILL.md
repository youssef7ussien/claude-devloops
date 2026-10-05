---
name: "devloops-dashboard"
description: "Generate the devloops dashboard for a workspace of this project and report its path."
argument-hint: "[--workspace <ws>] [--light]"
user-invocable: true
allowed-tools: Bash(bin/devloops *)
---

## User Input

```text
$ARGUMENTS
```

Run exactly one command through Bash from the project root, passing the user's arguments unchanged:

    bin/devloops dashboard $ARGUMENTS --json

Summarize: the dashboard path (and the full dashboard's path and size, when one was
written), the largest embedded files, and any warnings. Remind the user that a full dashboard
contains full Claude Code conversations and should be reviewed before sharing.

Do not approve, replan, retry, edit files, or re-run anything unless the user asks. On a usage
error, report it and do not guess missing arguments. This skill holds no loop logic.
