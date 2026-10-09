---
name: "devloops-dashboard"
description: "Report the devloops dashboard's address for this project (starting it in the background when none runs), stop it, or export a self-contained dashboard."
argument-hint: "[--workspace <ws>] [--stop | --export [<path>]]"
user-invocable: true
allowed-tools: Bash(bin/devloops *)
---

## User Input

```text
$ARGUMENTS
```

Run exactly one command through Bash from the project root:

    bin/devloops dashboard $ARGUMENTS --json

Pass the user's arguments unchanged, except: when they give none of `--daemon`, `--stop`, or
`--export`, add `--daemon --no-open` to them. Without one of those, `devloops dashboard` serves in
the foreground until stopped, and the command would never return.

Summarize: the `serving` address (and the `log` of a background server; it runs until
`devloops dashboard --stop`), whether `--stop` stopped a server, or with `--export` the file's
path and size, the largest embedded items, and any warnings. Remind the user that an export
contains full Claude Code conversations and should be reviewed before sharing.

Do not approve, replan, retry, edit files, or re-run anything unless the user asks. On a usage
error, report it and do not guess missing arguments. This skill holds no loop logic.
