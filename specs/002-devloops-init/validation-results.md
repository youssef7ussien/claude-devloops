# Validation results: real Claude Code run (T061, SC-007)

**Date**: 2026-10-06 · **devloops**: 0.2.0 (and a local 0.2.1 for §4) · **Claude Code**: 2.1.291 ·
**Playwright MCP**: 0.0.83 (system Chromium) · **uv**: 0.12.19
**Scope**: quickstart §2–5, using only the commands in `loops/README.md`.

## Outcome

| Step | Result | Claude calls | Cost (USD) |
|------|--------|--------------|------------|
| §2 install, `init`, `check` | as expected (details below) | 0 | 0 |
| §3 `orchestrate --speckit-feature`, backend-dev | completed: M01 on trial 3 (after a `retry`), M02 on trial 1 | 7 | 1.39 |
| §3 `orchestrate`, frontend-dev | completed: M01 and M02 on trial 1 (plus one voided trial, below) | 7 | 1.13 |
| | **total** | **14** | **2.52** |
| §4 upgrade 0.2.0 → 0.2.1, and back | as expected | 0 | 0 |
| §5 visible browser | `check`'s display warning verified; the window itself not opened (below) | 0 | 0 |

The counts and costs come from `devloops export-sessions`. Elapsed time from the first plan to
completion was 7 min 25 s. The project was a throwaway folder outside the repository; nothing
under `loops/` or `bin/` was written by the runs.

## What was checked

- **§2 install.** `uv tool install .` (with `UV_TOOL_DIR`/`UV_TOOL_BIN_DIR` pointing at a scratch
  folder, so the machine's own tools were untouched) installed `devloops`; `devloops --version`
  printed `devloops 0.2.0`. `devloops init --no-prompt` listed its 11 files, the permission rule
  and how to add it, and the next command. It wrote `"requirements": {"speckit_feature":
  "active"}` because `.specify/feature.json` named a feature. `git status` showed exactly the
  installed files, `devloops.json`, `manifest.json`, and `.gitignore`.
- **§2 check.** Without a Chrome-channel browser, `check` exited 30 and named `browser` with its
  fix. With `executable_path` in `devloops.local.json` (which `git status` did not show, so the
  ignore block works), it exited 0.
- **§3 spec-kit feature.** `specs/001-health/` had `spec.md`, `plan.md`, and `tasks.md` (three
  tasks over two phases). Both plans followed the phases: each milestone has `speckit_phase`
  (1, then 2) and each task cites its spec-kit task IDs. The plan summaries' **Spec-kit tasks**
  sections listed the planned tasks, and each loop left out the other loop's task with a reason
  ("Frontend task … out of scope for backend-dev", and the reverse). The stack came from
  `plan.md` (source `requirements`). `status` showed the spec-kit feature folder.
- **§3 full dashboard.** Each command that ended in a final status printed `full dashboard: <path>
  (<size>)`. The last one (2.9 MB) was copied to another folder and opened offline in headless
  Chromium: it has no external `src`/`href`, every screenshot is embedded, and all 14 calls show
  their prompt (with its prompt sources) and their full conversation. None was unavailable.
- **Recovery and relocation, not planned but exercised.** The first scratch folder was under
  `~/.claude`, where Claude Code blocks writes. The first implement call could not write and
  raised a `needs-input` question saying so (exit 20). The project was moved to `/tmp`, the
  question answered, and `retry` granted trials. The next `orchestrate` recorded `project moved
  from … to …` (`input-check`), rewrote the recorded paths, and continued. M01's trial 2 then
  failed the contract check (the server answered `GET /openapi.json`, its ready URL, without
  documenting it); trial 3 documented it and passed.
- **Service error.** The frontend's first `validate-ui` call stopped with exit 50: `the Playwright
  MCP server did not start`. `npx` was downloading a new `@playwright/mcp` release (0.0.83) and
  the server missed Claude Code's start-up time. The trial was voided (not counted), and running
  `orchestrate` again resumed and completed, as the README says.
- **§4 upgrade.** A scratch copy with `__version__ = "0.2.1"` and two changed skill templates was
  installed with `uv tool install --force`. Every command then warned about the version
  mismatch. After editing `devloops-run/SKILL.md` locally, `init --upgrade` updated
  `devloops-status/SKILL.md`, kept `devloops-run/SKILL.md` and wrote
  `SKILL.md.devloops-new` next to it, and recorded `0.2.1` and `upgraded_at` in the manifest.
  Reinstalling 0.2.0 then warned on every command, and `init --upgrade` exited 30
  `downgrade-refused` with nothing changed.
- **§5 visible browser.** With `"headless": false` in `devloops.local.json` and no `DISPLAY`,
  `check` showed the `display` warning and its fix. The window itself was not opened: this ran in
  a background session on a machine with a live desktop, and a frontend run would have opened a
  browser on the user's screen. The `--headless` flag is dropped from the MCP command in that
  case (`test_config`); the visible window remains to be checked by hand.

## Defects found and fixed

1. **A command that changed nothing wrote a new full dashboard.** Running `orchestrate` on a run
   that had already stopped ("nothing to do") wrote a second 631 KB dashboard 10 seconds after
   the first. Since full dashboards accumulate, this filled the folder with duplicates.
   - **Fix**: `run`, `approve`, `replan`, `retry`, and `orchestrate` write one only when the
     command recorded an event (a loop's `events.jsonl` grew) and ended in a final status.
     `devloops dashboard` still writes one on demand.
   - **Tests**: `test_full_dashboard` now checks that re-running a completed or stopped run, or
     `orchestrate` on it, writes no new file. This replaces the earlier expectation that a re-run
     of a completed run writes another one.
2. **The version warning gave the wrong advice to an older devloops.** On a project set up by
   0.2.1, devloops 0.2.0 said `Run "devloops init --upgrade"`, which then refuses the downgrade.
   - **Fix**: when the project's version is newer, the warning says `Install devloops <v> or
     later.` (`test_upgrade`).

## README gaps fixed

- The `check` example showed a git version; the item shows git's path.
- New known limitations: projects under `~/.claude` (Claude Code blocks writes there), and the
  first Playwright MCP start downloading the server (with `npx @playwright/mcp@latest --help` to
  pre-fetch it).
- The version-warning sentence now covers both directions.
