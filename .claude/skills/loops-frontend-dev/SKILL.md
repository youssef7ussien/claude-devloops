---
name: "loops-frontend-dev"
description: "Start or resume the frontend-dev loop with bin/devloops (build a frontend from requirements and a backend OpenAPI document), then summarize its status."
argument-hint: "--workspace <ws> [--requirements <file> [--story-id <id> | --story-file]] [--api-spec <openapi.json>] [--target <dir>] [other `run` options]"
user-invocable: true
---

## User Input

```text
$ARGUMENTS
```

Run **exactly one** command through Bash from the repository root, passing the user's arguments
unchanged:

```sh
bin/devloops run frontend-dev $ARGUMENTS --json
```

`--json` makes the command print one status object (the shape of `status --json`, plus
`exit_code` and `message`). Summarize it for the user: `exit_code`, `message`, `status`,
`status_reason`, the next milestone and trials used, the last failure, the UI URL, and the
`progress` path. For a read-only look later, `bin/devloops status frontend-dev --workspace <ws> --json`
also lists `large_evidence` (evidence files over 1 MB to review before committing a workspace).

Explain what the exit code asks of the user, as `loops/README.md` describes it: 10 means review
`outputs/` and answer `outputs/open-questions.md`, then `bin/devloops approve frontend-dev` or
`bin/devloops replan frontend-dev`; 20, 30, 40, and 50 mean the run stopped for the reason shown.

Do not approve, replan, retry, edit workspace files, or re-run the loop unless the user asks. This
skill contains no loop logic: everything is in `bin/devloops`.
