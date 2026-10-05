# Contract: Claude Code skills installed by `init`

The templates live in the kit at `shared/skills/<name>/SKILL.md`. `init` renders them into
`.claude/skills/<name>/SKILL.md`, replacing `{{DEVLOOPS}}` with the project's devloops command
(research P-7):
- `devloops` when installed;
- `bin/devloops` (or an absolute path) from a source checkout.

The installed skills and this repository's skills are rendered from the same templates (FR-022).

| Skill | Runs exactly | Arguments (`$ARGUMENTS`, passed unchanged) |
|-------|--------------|---------------------------------------------|
| `devloops-run` | `{{DEVLOOPS}} run $ARGUMENTS --json` | `<backend-dev\|frontend-dev> [--workspace …] [--requirements … \| --speckit-feature [dir]] [--story-id …] [--target …] …` |
| `devloops-orchestrate` | `{{DEVLOOPS}} orchestrate $ARGUMENTS --json` | `[--speckit-feature [dir] \| --requirements …] [--story-id …] …` |
| `devloops-approve` | `{{DEVLOOPS}} approve $ARGUMENTS --json` | `<loop> [--workspace …]` |
| `devloops-replan` | `{{DEVLOOPS}} replan $ARGUMENTS --json` | `<loop> [--workspace …]` |
| `devloops-retry` | `{{DEVLOOPS}} retry $ARGUMENTS --json` | `<loop> --milestone M01 --reason "…" [--trials n]` |
| `devloops-status` | `{{DEVLOOPS}} status $ARGUMENTS --json` | `[<loop>] [--workspace …]` |
| `devloops-dashboard` | `{{DEVLOOPS}} dashboard $ARGUMENTS --json` | `[--workspace …] [--light]` |

## Template shape

```markdown
---
name: "devloops-run"
description: "Start or resume one devloops loop (backend-dev or frontend-dev) in this project, then summarize its status."
argument-hint: "<backend-dev|frontend-dev> [--speckit-feature [dir] | --requirements <file>] [--story-id <id>] [other run options]"
user-invocable: true
allowed-tools: Bash({{DEVLOOPS}} *)
---

## User Input

```text
$ARGUMENTS
```

Run exactly one command through Bash from the project root, passing the user's arguments unchanged:

    {{DEVLOOPS}} run $ARGUMENTS --json

Summarize: exit_code, message, status, status_reason, next milestone and trials used, last
failure, artifacts, the dashboard and full-dashboard paths, and any warnings. Explain what the exit
code asks of the user (10: review outputs/ and answer open-questions.md, then approve or replan;
20/30/40/50: the stop reason and the README's recovery step).

Do not approve, replan, retry, edit files, or re-run anything unless the user asks. On a usage
error, report it and do not guess missing arguments. This skill holds no loop logic.
```

## Rules (FR-021)

- One devloops command per invocation. Never a second command, a retry, or a file edit.
- The arguments are passed unchanged. `--json` is always appended.
- `allowed-tools` pre-approves only `Bash({{DEVLOOPS}} *)`.
