---
name: "devloops-orchestrate"
description: "Run or resume devloops backend-dev, then frontend-dev, in one workspace of this project, then summarize both loops."
argument-hint: "[--speckit-feature [dir] | --requirements <file>] [--story-id <id>] [other orchestrate options]"
user-invocable: true
allowed-tools: Bash({{DEVLOOPS}} *)
---

## User Input

```text
$ARGUMENTS
```

Run exactly one command through Bash from the project root, passing the user's arguments unchanged:

    {{DEVLOOPS}} orchestrate $ARGUMENTS --json

Summarize: exit_code, message, status, status_reason, next milestone and trials used, last
failure, artifacts, the dashboard and full-dashboard paths, and any warnings. Explain what the exit
code asks of the user (10: review outputs/ and answer open-questions.md, then approve or replan;
20/30/40/50: the stop reason and the README's recovery step).

Do not approve, replan, retry, edit files, or re-run anything unless the user asks. On a usage
error, report it and do not guess missing arguments. This skill holds no loop logic.
