# Implementation Plan: One Command to Run Devloops

**Branch**: `003-single-run-command` (work is committed on `main`) | **Date**: 2026-10-08 |
**Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/003-single-run-command/spec.md` (17 clarifications in
Session 2026-10-08, 3 in Session 2026-10-09 from `checklists/run-command.md`)

**Decision tags**: the same as 001's and 002's plans.

| Tag | Meaning |
|-----|---------|
| **[ER]** | Explicit requirement (spec FR, SC, or clarification) |
| **[RD]** | Repository-derived (verified in this repository) |
| **[RC]** | Recommendation (the rationale is in [research.md](./research.md), R-n) |

## Summary

`devloops run`, with no loop name, becomes the only way to run devloops.

**What changes**:
- **One run command:** `devloops run` runs today's orchestrator code. `run <loop>` and
  `orchestrate` are deleted [ER: FR-001, FR-008; RC, R-1].
- **Loop selection:** which loops run is computed on every command from the workspace, the target
  flags, and `targets` in `devloops.json`, where `null` or missing means "not used" [ER: FR-005;
  RC, R-2].
- **Wrong setups stop first:** a setup with no loop, or a frontend without a backend, stops with
  exit 30 before anything is written [ER: FR-006; RC, R-3].
- **Decisions without a loop:** `approve`, `replan`, and `retry` find the waiting loop themselves
  and always continue the whole run [ER: FR-009, FR-010; RC, R-4].
- **init:** gains `--no-backend` / `--no-frontend` and a `none` answer [ER: FR-013, FR-014; RC,
  R-7].
- **check:** checks only the loops the project includes [ER: FR-015; RC, R-8].
- **Renaming:** "orchestrator" becomes "run" in output, JSON, dashboards, and the workspace folder
  [ER: FR-016; RC, R-9].
- **Skills:** `devloops-orchestrate` is removed [ER: FR-017; RC, R-13].
- **Docs:** the README and the 001/002 docs are edited in place [ER: FR-018].
- **Constitution:** Principle VI is amended to 2.0.0 [ER: FR-019; RC, R-12].

**What does not change**: the engine's per-loop behavior (planning, trials, validation, handoff
content), exit codes, run.json, and the questions mode.

## Technical Context

**Language/Version**: Python ≥ 3.10, standard library only at runtime (unchanged) [RD].

**Primary Dependencies**: unchanged (Claude Code CLI, curl, Playwright MCP via npx, git).

**Storage**: JSON files. The workspace folder `orchestrator/` becomes `run/`.

**Testing**:
- The `unittest` suite with the fake `claude`: `timeout 900 python3 -m unittest discover -s
  loops/shared/tests`, 589 tests today, always with `VISUAL=true EDITOR=true` [RD].
- Frontend-loop tests move from the CLI to a test helper that drives `engine.Engine` directly
  [RC, R-11].

**Target Platform**: Linux and macOS developer machines (unchanged).

**Project Type**: CLI tool plus packaged assets.

**Performance Goals**: the selection check is reported in under 1 s (SC-003). It reads only
`devloops.json` and `workspace.json`.

**Constraints**:
- No migration or aliases (devloops is in development) [ER].
- The engine API stays as it is, so each loop remains runnable alone once its inputs exist
  (amended Principle VI) [RC, R-11, R-12].

**Scale/Scope**:
- **No new modules.**
- **Code changes:**
  - most of the work: `cli.py` and `orchestrator.py`;
  - small changes: `initcmd.py`, `checkcmd.py`, `engine.py`, `render.py`, `dashboard.py`,
    `fulldash.py`.
- **Tests:** about 25 test files change their command lines. `test_orchestrator.py`,
  `test_continue.py`, `test_project_runs.py`, and `test_frontend_loop.py` change the most.
- **Docs and skills:** one skill removed, three skill texts changed, the README, 001 `cli.md` /
  `workspace-layout.md` / spec FR-039–040, and 002 `cli.md` / `skills.md` / `project-layout.md`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| # | Principle | How this plan complies | Pre | Post |
|---|-----------|------------------------|-----|------|
| I | Requirements-driven | Every change maps to an FR confirmed by the developer. Details the spec left open are flagged in research.md as **[open detail]** | ✅ | ✅ |
| II | Reusability | The selection reads only project configuration. No application specifics | ✅ | ✅ |
| III | Verifiable increments | Unchanged validation. The frontend still gets a verified contract and a startable backend; the M02 failure mode is removed | ✅ | ✅ |
| IV | Controlled, recoverable automation | A wrong setup writes nothing (FR-006). A refused decision changes nothing (FR-009/010). A loop already started keeps its recorded target | ✅ | ✅ |
| V | Bounded execution | No new retries. A wrong setup no longer spends trials | ✅ | ✅ |
| VI | Separation of concerns | **Requires the amendment (FR-019, R-12).** The CLI can no longer run frontend-dev alone. The engine still can, and is tested that way (R-11). Frontend-only runs are a temporary, recorded deviation (Complexity Tracking) | ⚠️ justified | ✅ after amendment |
| VII | Existing infrastructure first | It reuses the orchestrator, the engine's action path, `config-override`, and init's removed-file upgrade handling. Nothing new is invented | ✅ | ✅ |
| VIII | Testability and traceability | The `decision: {command, loop}` JSON keeps which loop was decided. New offline tests cover the selection, the exit-30 checks, decisions without a loop, init `none`, and check `unused` | ✅ | ✅ |
| IX | Documentation | README, skills, and the 001/002 contracts are updated in place, with notes pointing to 003 (FR-018) | ✅ | ✅ |
| X | Simplicity | Net code removal: one command path instead of three, and no migration code | ✅ | ✅ |
| — | Constitutional boundary | Code names, messages, and folder names live in the spec and code, not the constitution | ✅ | ✅ |

## Project Structure

### Documentation (this feature)

```text
specs/003-single-run-command/
├── spec.md
├── plan.md              # this file
├── research.md          # R-1 … R-13
├── data-model.md        # targets, loop selection, run state, check result
├── quickstart.md        # 5 validation scenarios
├── contracts/
│   ├── cli.md           # run, decisions, init, check, status changes
│   └── skills.md        # skills table
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source code (repository root)

```text
.specify/memory/constitution.md            # Principle VI amended, 2.0.0 (R-12)
loops/README.md                            # one run command; backend-only; init --no-*
loops/shared/devloops/
├── cli.py            # run (no loop) → orchestrator; orchestrate removed; decisions find the
│                     # waiting loop; selection check; init --no-*; `run` JSON key / line
├── orchestrator.py   # select_loops(); runs only selected loops; handoff after the backend
│                     # always; completed → running when a loop is added; folder run/
├── engine.py         # resume_command "devloops run"; hints without a loop name
├── initcmd.py        # `none` answer, --no-backend/--no-frontend, both-none refusal, next line
├── checkcmd.py       # included loops; `unused` status; `loops` in JSON
├── render.py         # run progress title and hints
├── dashboard.py      # "Run" view (was Orchestrator); run/state.json; hints without a loop
└── fulldash.py       # run/ file group; trigger names
loops/shared/skills/
├── devloops-orchestrate/   # removed
├── devloops-run/SKILL.md   # `run` with no loop
├── devloops-approve/, devloops-replan/, devloops-retry/SKILL.md   # no loop name
loops/shared/schemas/project-config.schema.json   # targets descriptions (+ 002 copy, byte-identical)
loops/shared/tests/   # command lines updated; new selection, init, check, decision tests;
                      # frontend-loop tests drive the engine (R-11)
.claude/skills/       # re-rendered with `bin/devloops init --upgrade`
specs/001-reusable-dev-loops/{spec.md FR-039/040 note, contracts/cli.md, contracts/workspace-layout.md}
specs/002-devloops-init/{contracts/cli.md, contracts/skills.md, contracts/project-layout.md}
```

**Structure Decision**: no new modules. The orchestrator becomes the run path, and every
user-visible name changes (R-1, R-9).

## Key flows

### `devloops run`

```text
parse (no loop) → project → workspace exists? open read-only : none
→ select_loops(project, ws, flags)                       # R-2
→ empty / frontend-only? exit 30, nothing written        # R-3
→ open/create workspace, record targets
→ Orchestrator.run(selected): check tools of loops with work left
  → for each selected loop: skip if completed, else Engine.run (pause/stop → return code)
     after backend-dev completes: record handoff
→ write run/state.json, summary dashboard, print `run: <status>` (+ review prompt at a pause)
```

### `devloops approve | replan | retry`

```text
parse (no loop) → open workspace (must exist)
→ waiting loop = first selected loop in awaiting-approval (approve/replan) or stopped-on-failure
  (retry); none → exit 2, nothing changed                # R-4
→ --no-continue? record via Engine, sync run/state.json
  : Orchestrator.run(action=(loop, decide)) → the whole run continues
```

## Implementation order (for /speckit-tasks)

1. **Constitution:** the amendment (R-12). It unblocks the rest.
2. **Selection:** `select_loops` and the exit-30 checks, with unit tests.
3. **Orchestrator:** runs the selected loops; backend-only completion; a later-added loop; the
   `run/` folder.
4. **CLI `run`:** the new `run` replaces `run <loop>` and `orchestrate`; `--max-trials`; output
   and JSON renamed.
5. **Decisions:** without a loop; the single-loop path removed.
6. **Messages:** engine, render, and dashboard hints; the dashboard "Run" view; the fulldash
   group.
7. **init:** `--no-*`, `none`, the both-none refusal, the next line.
8. **check:** `unused`, `loops`.
9. **Tests:** existing tests migrated (backend-only project config, `devloops run`); the
   frontend-loop test helper (R-11).
10. **Skills:** removal and texts; repository skills re-rendered.
11. **Docs:** README and the 001/002 docs in place. Then the full test suite and the quickstart
    scenarios.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Principle VI (before amendment): frontend-dev cannot be started alone from the CLI until a follow-up feature adds frontend-only runs through `devloops.json` | The developer limited this feature to step 1. A frontend started alone without a backend is the failure this feature removes | Keeping `run frontend-dev --api-spec` keeps the failure mode and the three-command choice. Adding frontend-only via config now is step 2, which the developer deferred. The engine keeps the capability and its tests (R-11), so the follow-up only adds a CLI path |
