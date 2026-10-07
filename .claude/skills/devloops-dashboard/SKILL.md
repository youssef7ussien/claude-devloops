---
name: "devloops-dashboard"
description: "Write the devloops summary page, or export a full dashboard, for a workspace of this project and report its path."
argument-hint: "[--workspace <ws>] [--export [--out <file>]]"
user-invocable: true
allowed-tools: Bash(bin/devloops *)
---

## User Input

```text
$ARGUMENTS
```

If the user asks to serve the dashboard (`--serve`, a live dashboard, files and conversations in a
browser), do not run it: it serves until stopped. Tell the user to run
`devloops dashboard --serve` in a terminal of their own (add `--workspace <ws>` when given), and
stop.

Otherwise run exactly one command through Bash from the project root, passing the user's arguments
unchanged:

    bin/devloops dashboard $ARGUMENTS --json

Summarize: the summary page's path, or with `--export` the exported dashboard's path and size, the
largest embedded files, and any warnings; and the `serving` URL when a dashboard server is
running. Remind the user that an exported dashboard contains full Claude Code conversations and
should be reviewed before sharing.

Do not approve, replan, retry, edit files, or re-run anything unless the user asks. On a usage
error, report it and do not guess missing arguments. This skill holds no loop logic.
