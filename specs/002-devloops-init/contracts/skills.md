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

> **Revised after specs/005-dashboard-redesign**: the `devloops-approve`, `devloops-replan`,
> `devloops-retry`, and `devloops-dashboard` skills are removed (`init --upgrade` removes an
> unchanged installed copy of each). `devloops-run` asks the user for the decision when the run
> waits for one and runs that command itself; it never starts a dashboard server. The table, the
> template shape, and the rules below are revised to match. This repository no longer installs
> the skills.

| Skill | Runs | Arguments (`$ARGUMENTS`, passed unchanged) |
|-------|------|---------------------------------------------|
| `devloops-run` | `{{DEVLOOPS}} run $ARGUMENTS --json`; then, only after asking the user, `{{DEVLOOPS}} approve --json` or `{{DEVLOOPS}} replan --json` (exit 10), or `{{DEVLOOPS}} retry --milestone <id> [--reason …] [--trials n] --json` (exit 20 on a milestone), repeated while the run waits again | `[--workspace …] [--requirements … \| --speckit-feature [dir]] [--story-id …] [--target-root …] [--backend-target …] [--frontend-target …] [--max-trials n] [--review-plan \| --accept-suggested] …` |
| `devloops-status` | exactly `{{DEVLOOPS}} status $ARGUMENTS --json` | `[<loop>] [--workspace …]` |

## Template shape

The templates are `loops/shared/skills/<name>/SKILL.md`; the run skill's text is its contract in
full (what it summarizes, which stops it decides, and how it asks). Their frontmatter:

```markdown
---
name: "devloops-run"
description: "Start or resume the devloops run in this project (backend-dev, then frontend-dev, as the project configures), then summarize its status; when it waits for a decision, ask the user and carry it out."
argument-hint: "[--workspace <ws>] [--speckit-feature [dir] | --requirements <file>] … [--review-plan | --accept-suggested] [other run options]"
user-invocable: true
allowed-tools: Bash({{DEVLOOPS}} *), Read
---
```

## Rules (FR-021)

- `devloops-status` runs one devloops command per invocation, and edits no file.
- `devloops-run` runs one `run` command; then, only for a decision the user chose when asked
  (AskUserQuestion), `approve`, `replan`, or `retry`, and it repeats that while the run waits
  again. It decides nothing itself, starts no dashboard server, and edits no file except writing
  the user's own answers into `open-questions.md`.
- The user's arguments are passed unchanged. `--json` is always appended.
- `allowed-tools` pre-approves `Bash({{DEVLOOPS}} *)`, and `Read` for the run skill (the plan it
  shows); an edit of `open-questions.md` is asked for.
