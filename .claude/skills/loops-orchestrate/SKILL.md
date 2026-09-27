---
name: "loops-orchestrate"
description: "Run or resume backend-dev, then frontend-dev, in one workspace with bin/devloops orchestrate, then summarize both loops' status."
argument-hint: "--workspace <ws> [--requirements <file> [--story-id <id> | --story-file]] [--target-root <dir> | --backend-target <dir> --frontend-target <dir>]"
user-invocable: true
---

## User Input

```text
$ARGUMENTS
```

Run **exactly one** command through Bash from the repository root, passing the user's arguments
unchanged:

```sh
bin/devloops orchestrate $ARGUMENTS --json
```

`--json` makes the command print one object: `exit_code`, `message`, `orchestrator` (the contents
of `orchestrator/state.json`: status, steps, and handoff), and `loops` (each loop's status object).
Summarize it for the user: the exit code and message, the orchestrator status, and for each loop
its `status`, `status_reason`, next milestone, last failure, and `progress` path; also the OpenAPI
artifact and the UI URL once they exist. For a read-only look later,
`bin/devloops status --workspace <ws> --json` also lists `large_evidence`.

Explain what the exit code asks of the user, as `loops/README.md` describes it: 10 means the loop
shown awaits approval (`bin/devloops approve <loop>`, then orchestrate again); 20, 30, 40, and 50
mean a loop stopped for the reason shown. Running `orchestrate` again resumes.

Do not approve, replan, retry, edit workspace files, or re-run anything unless the user asks. This
skill contains no loop logic: everything is in `bin/devloops`.
