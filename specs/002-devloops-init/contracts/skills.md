# Contract: Claude Code skills installed by `init`

The templates live in the kit at `shared/skills/<name>/SKILL.md`. `init` renders them into
`.claude/skills/<name>/SKILL.md`, replacing `{{DEVLOOPS}}` with the project's devloops command
(research P-7):
- `devloops` when installed;
- `bin/devloops` (or an absolute path) from a source checkout.

The installed skills and this repository's skills are rendered from the same templates (FR-022).

> Revised by specs/003-single-run-command
> ([contracts/skills.md](../../003-single-run-command/contracts/skills.md)): the run skill runs the
> project's loops with no loop name, the decision skills take no loop, and `devloops-orchestrate`
> is removed (`init --upgrade` removes an unchanged installed copy and reports a changed one).

| Skill | Runs exactly | Arguments (`$ARGUMENTS`, passed unchanged) |
|-------|--------------|---------------------------------------------|
| `devloops-run` | `{{DEVLOOPS}} run $ARGUMENTS --json` | `[--workspace …] [--requirements … \| --speckit-feature [dir]] [--story-id …] [--target-root …] [--backend-target …] [--frontend-target …] [--max-trials n] [--review-plan \| --accept-suggested] …` |
| `devloops-approve` | `{{DEVLOOPS}} approve $ARGUMENTS --json` | `[--workspace …] [--no-continue] [--review-plan \| --accept-suggested]` |
| `devloops-replan` | `{{DEVLOOPS}} replan $ARGUMENTS --json` | `[--workspace …] [--no-continue] [--review-plan \| --accept-suggested]` |
| `devloops-retry` | `{{DEVLOOPS}} retry $ARGUMENTS --json` | `--milestone M01 [--reason "…"] [--trials n] [--workspace …] [--no-continue] [--review-plan \| --accept-suggested]` |
| `devloops-status` | `{{DEVLOOPS}} status $ARGUMENTS --json` | `[<loop>] [--workspace …]` |
| `devloops-dashboard` | `{{DEVLOOPS}} dashboard $ARGUMENTS --json` (never `--serve`, which runs until stopped: the skill tells the user to run it in a terminal) | `[--workspace …] [--export [--out …]]` |

## Template shape

Revised by specs/003-single-run-command (the run skill's description, hint, and summary).

```markdown
---
name: "devloops-run"
description: "Start or resume the devloops run in this project (backend-dev, then frontend-dev, as the project configures), then summarize its status."
argument-hint: "[--workspace <ws>] [--speckit-feature [dir] | --requirements <file>] [--story-id <id>] [--target-root <dir>] [--backend-target <dir>] [--frontend-target <dir>] [--max-trials <n>] [--review-plan | --accept-suggested] [other run options]"
user-invocable: true
allowed-tools: Bash({{DEVLOOPS}} *)
---

## User Input

```text
$ARGUMENTS
```

Run exactly one command through Bash from the project root, passing the user's arguments unchanged:

    {{DEVLOOPS}} run $ARGUMENTS --json

Summarize: exit_code, message, the run's status (`run.status`), and for each loop in `loops` its
status, status_reason, next milestone and trials used, last failure, and artifacts; then the
dashboard and full-dashboard paths, and any warnings. When the setup stops before anything runs
(exit 30 with only `status_reason`: no loop, or a frontend without a backend), report
`status_reason.message`, which says how to fix it. On a usage error (exit 2) the result is
`{error, exit_code}`: report `error`. Explain what the exit code asks of the user (10: review the
waiting loop's outputs/ and answer open-questions.md, then approve or replan, which continue the
run; 20/30/40/50: the stop reason and the README's recovery step).

Do not approve, replan, retry, edit files, or re-run anything unless the user asks. On a usage
error, report it and do not guess missing arguments. This skill holds no loop logic.
```

## Rules (FR-021)

- One devloops command per invocation. Never a second command, a retry, or a file edit.
- The arguments are passed unchanged. `--json` is always appended.
- `allowed-tools` pre-approves only `Bash({{DEVLOOPS}} *)`.
