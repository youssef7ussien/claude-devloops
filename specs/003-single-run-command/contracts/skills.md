# Contract: skills changes (003)

This contract replaces the skills table in `specs/002-devloops-init/contracts/skills.md`, which is
edited in place to match. The template rules there (rendering `{{DEVLOOPS}}`, one command per skill,
summarizing the `--json` result) are unchanged.

| Skill | Runs exactly | Arguments (`$ARGUMENTS`, passed unchanged) |
|-------|--------------|---------------------------------------------|
| `devloops-run` | `{{DEVLOOPS}} run $ARGUMENTS --json` | `[--workspace …] [--requirements … \| --speckit-feature [dir]] [--story-id …] [--target-root …] [--backend-target …] [--frontend-target …] [--max-trials n] [--review-plan \| --accept-suggested] …` |
| `devloops-approve` | `{{DEVLOOPS}} approve $ARGUMENTS --json` | `[--workspace …] [--no-continue] [--review-plan \| --accept-suggested]` |
| `devloops-replan` | `{{DEVLOOPS}} replan $ARGUMENTS --json` | `[--workspace …] [--no-continue] [--review-plan \| --accept-suggested]` |
| `devloops-retry` | `{{DEVLOOPS}} retry $ARGUMENTS --json` | `--milestone M01 [--reason "…"] [--trials n] [--workspace …] [--no-continue] [--review-plan \| --accept-suggested]` |
| `devloops-status` | `{{DEVLOOPS}} status $ARGUMENTS --json` | `[<loop>] [--workspace …]` (unchanged) |
| `devloops-dashboard` | unchanged | unchanged |

**Removed**: `devloops-orchestrate`. On `init --upgrade`, an unchanged installed copy is removed
and a changed one is reported ("no longer part of devloops"), using the existing handling for
files removed from the kit.

**Wording**:
- **`devloops-run`:** the description reads "Start or resume the devloops run in this project
  (backend-dev, then frontend-dev, as the project configures), then summarize its status".
- **Decision skills:** approve and replan describe "the waiting loop", retry "the loop stopped on
  failure"; none asks the user for a loop name.
- **Summaries** (revised after code review): exit 2 is any usage error (for example, nothing was
  waiting), whose result is `{error, exit_code}`; a decision with `--no-continue` returns one
  loop's status object, not `run`/`loops`; a run (or a continued decision) stopped before anything
  ran returns only `exit_code` and `status_reason`.
