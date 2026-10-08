# Quickstart validation: One Command to Run Devloops

These scenarios prove the feature end to end. They use the offline fake Claude from the test suite
(`loops/shared/tests/fake_claude.py`), as the automated tests do. Always set `VISUAL=true
EDITOR=true` so nothing opens an editor.

## Prerequisites

- A source checkout. Every scenario runs in a temporary directory, using `bin/devloops`.
- The automated suite: `timeout 900 python3 -m unittest discover -s loops/shared/tests`.

## Scenario 1: both loops with one command (US1)

1. Run `devloops init --no-prompt --requirements prd.md` in a temporary project. Both targets keep
   their defaults.
2. Run `devloops run --review-plan`. **Expect** exit 10, `run: paused`, and backend-dev
   `awaiting-approval`.
3. Run `devloops approve`. **Expect** the backend to complete, then the frontend to pause for
   approval (exit 10), with no loop name typed.
4. Run `devloops approve`. **Expect** exit 0 and `run: completed`. `<ws>/run/state.json` has a
   handoff, and frontend-dev's `run.json` has the backend's `openapi.json` as its API spec.
5. Run `devloops orchestrate` and `devloops run backend-dev`. **Expect** exit 2 from both.

## Scenario 2: a failed milestone and retry (US1)

1. Use a scenario where the frontend's M02 fails every trial. **Expect** `devloops run` to exit 20.
2. Run `devloops retry --milestone M02 --reason "seed a user first"`. **Expect** a `retry-granted`
   event on frontend-dev, and a run that continues.
3. Run `devloops approve` in that stopped run. **Expect** exit 2, `nothing awaits approval (run:
   stopped)`, and nothing changed.

## Scenario 3: backend only (US2)

1. Run `devloops init --no-prompt --no-frontend --requirements prd.md`. **Expect**
   `"frontend-dev": null` in `devloops.json`.
2. Run `devloops run`. **Expect** exit 0, `run: completed`, a handoff in `run/state.json`, and no
   `frontend-dev/` folder.
3. Run `devloops check --json` with no browser on `PATH`. **Expect** `ready: true`, `loops:
   ["backend-dev"]`, and the browser item `unused`.
4. Set `targets.frontend-dev` to `"frontend"`, then run `devloops run`. **Expect** frontend-dev to
   start from the recorded handoff, without running the backend again.

## Scenario 4: a wrong setup stops before anything (US3)

1. Set both targets to `null`, then run `devloops run --json`. **Expect** exit 30, code `no-loop`,
   and no `workspaces/` folder created.
2. Set only `frontend-dev`. **Expect** exit 30 and code `frontend-needs-backend`, with nothing
   created.
3. Run `devloops init --no-prompt --no-backend --no-frontend`. **Expect** exit 2, with no
   `.devloops/` written.

## Scenario 5: skills (US4)

1. Run `bin/devloops init --upgrade` in this repository. **Expect** `.claude/skills/
   devloops-orchestrate/` removed, and `devloops-run` to run `devloops run $ARGUMENTS --json`.
2. Run `grep -rn "orchestrate\|run backend-dev\|--api-spec" loops/README.md loops/shared/skills`.
   **Expect** matches only in notes that say the command was removed.
