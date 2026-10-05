# Implementation Plan: Devloops Project Setup

**Branch**: `002-devloops-init` (work is committed on `main`) | **Date**: 2026-10-05 |
**Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/002-devloops-init/spec.md` (8 clarifications,
Session 2026-10-05)

**Decision tags**: the same as 001's plan.

| Tag | Meaning |
|-----|---------|
| **[ER]** | Explicit requirement (spec FR, SC, or clarification) |
| **[RD]** | Repository-derived (verified in this repository or on this machine) |
| **[RC]** | Recommendation (the rationale is in [research.md](./research.md), P-n) |

## Summary

Devloops becomes a tool that is **installed once and set up per project**, the way spec-kit works.

**What it adds**:
- **Packaging**: a `pyproject.toml` packages the existing code (`devloops`) and the existing
  `loops/` assets (`devloops_kit`) without moving any file [RC, P-1].
- **Kit and project**: a new `kit` module finds the packaged files, and a new `project` module
  finds the nearest `.devloops/` from the current directory [RC, P-2, P-3]. Together they replace
  the single `repo_root` that 001 used for both.
- **Configuration**: the project holds `devloops.json` (shared) and `devloops.local.json`
  (per developer). They become two new layers in 001's configuration merge, still frozen at the
  first run [ER: FR-010; RC, P-4].
- **New commands**:
  - `devloops init`: writes the project files, renders seven Claude Code skills, appends an ignore
    block, and records a fingerprint manifest;
  - `init --upgrade`: uses the manifest to update without losing local changes;
  - `devloops check`: checks the environment.
- **Spec-kit bridge**: feeds `spec.md`, `plan.md`, and a deterministically parsed `tasks.md` to
  the planner. A plan check makes sure every in-scope spec-kit task is planned or explicitly left
  out [ER: FR-023–026; RC, P-16].
- **Full dashboard**: the new full dashboard embeds every artifact and every Claude Code
  conversation. The conversations are copied into the workspace when each call ends, because
  Claude Code deletes its transcripts after 30 days by default [ER: FR-035–042; RC, P-9–P-11].

**What does not change**: loop behavior, statuses, exit codes, and the workspace layout [ER: FR-033].

## Technical Context

**Language/Version**: Python ≥ 3.10, standard library only at runtime (unchanged). 3.14.7 locally
[RD].

**Primary Dependencies**:
- *Runtime*: unchanged from 001 (Claude Code CLI ≥ 2.1.283, curl, the Playwright MCP server via
  npx, git).
- *Build only*: setuptools ≥ 68 (84.0.0 locally) as the PEP 517 backend [RC, P-1].
- *Installation*: `uv tool install` (uv 0.12.19 locally) [RD]. Any installer that understands
  PEP 517 also works.

**Storage**: JSON files (`devloops.json`, `devloops.local.json`, `manifest.json`), the 001
workspace files, JSONL conversation copies, and HTML full dashboards.

**Testing**: the 001 `unittest` suite with the fake `claude` [RD]. It adds:
- a temporary `CLAUDE_CONFIG_DIR` with fake transcripts;
- a pseudo-terminal (`pty`) for interactive `init`;
- a wheel build-and-install test that is skipped when `uv` is absent.

**Target Platform**: Linux and macOS developer machines (unchanged).

**Project Type**: CLI tool plus packaged assets (developer tooling).

**Performance Goals**:
- `init` and `check` finish in seconds;
- the full dashboard for a T076-sized workspace is generated in under 5 s and is under 10 MB
  [RC, P-10].

**Constraints**:
- No runtime dependencies (FR-001).
- No file moves under `loops/` (001's documentation stays true) [RC, P-1].
- Old workspaces keep working (FR-033).
- The Claude Code transcript format is undocumented, so it is rendered defensively [RD, P-9].

**Scale/Scope**:
- 6 new modules: `kit`, `project`, `initcmd`, `checkcmd`, `speckit`, `fulldash`;
- about 8 changed modules;
- 7 skill templates;
- 4 additive schema changes.

**NEEDS CLARIFICATION**: none. Every unknown is resolved in research P-1 to P-18.

## Constitution Check

*GATE: checked before Phase 0 and again after Phase 1.*

| # | Principle | How this plan complies | Pre | Post |
|---|-----------|------------------------|-----|------|
| I | Requirements-driven | Every design element maps to an FR or a clarification. With spec-kit input, any planned task with no spec-kit counterpart and any spec-kit task left out are surfaced at approval (FR-023b) | ✅ | ✅ |
| II | Reusability | The project holds only configuration and overrides. The kit stays application-agnostic, and prompt overrides are per project, not edits to the kit (FR-030). The 001 `test_no_app_specifics` test still covers the kit | ✅ | ✅ |
| III | Verifiable increments | spec-kit `[x]` marks are not trusted. Tasks are still validated (spec edge case). Following `tasks.md` is checked deterministically (P-16) | ✅ | ✅ |
| IV | Controlled, recoverable automation | `init` never overwrites (FR-005); `--upgrade` keeps local changes (FR-027); settings are edited only on request (FR-022b); the configuration stays frozen, and drift is reported (FR-015, FR-032); targets can never overlap the kit or `.devloops/` (FR-014) | ✅ | ✅ |
| V | Bounded execution | No new loops or retries. `check` is advisory; the run's own preflight still guards it | ✅ | ✅ |
| VI | Separation of concerns | Installation (`initcmd`), environment (`checkcmd`), discovery (`project`), assets (`kit`), input bridge (`speckit`), and reporting (`fulldash`) are separate modules. The loop engine only receives resolved inputs | ✅ | ✅ |
| VII | Existing infrastructure first | It reuses 001's configuration merge, schema validator, redactor, dashboard collector, and skill pattern; spec-kit's own file formats; the Claude Code skill `allowed-tools` and settings permission rules; and standard Python packaging. New: one build-time dependency (justified below) | ✅ | ✅ |
| VIII | Testability and traceability | The new behavior is covered offline. Invocation records gain prompt sources and conversation copies. Plans keep spec-kit task IDs, giving a trace from spec-kit task to milestone to trial to conversation | ✅ | ✅ |
| IX | Documentation | README sections for install, init, check, upgrade, the project layout, configuration precedence, the visible browser, overrides, the spec-kit bridge, the full dashboard, and the migration of this repository (FR-034) | ✅ | ✅ |
| X | Simplicity | No new service, no merge engine (`.devloops-new` instead), no file moves, and a page with no JavaScript beyond 001's theme toggle. Additions beyond the obvious are listed in Complexity Tracking | ✅ | ✅ |
| — | Constitutional boundary | Defaults (`main`, directories, the minimum Claude version) live in configuration and code constants, not in the constitution | ✅ | ✅ |

**Gate result**: PASS, before and after design.

## Project Structure

### Documentation (this feature)

```text
specs/002-devloops-init/
├── spec.md  plan.md  research.md  data-model.md  quickstart.md
├── contracts/
│   ├── cli.md  project-layout.md  skills.md  full-dashboard.md
│   └── project-config.schema.json  manifest.schema.json
├── checklists/requirements.md
└── tasks.md            # created by /speckit-tasks
```

### Source code (repository root)

```text
pyproject.toml                         # NEW: packaging (P-1)
bin/devloops                           # unchanged entry point for source checkouts
loops/
├── README.md                          # + install/init/check/upgrade/project/spec-kit/full dashboard (FR-034)
├── backend-dev/  frontend-dev/  orchestrator/          # unchanged
└── shared/
    ├── config/defaults.json           # playwright: headless, executable_path, mcp_command: null (P-15)
    ├── prompts/steps/plan.md          # + spec-kit section (P-16)
    ├── schemas/                       # additive fields (data-model § Changes); + project-config, manifest
    ├── skills/devloops-*/SKILL.md     # NEW: 7 templates (P-7)
    ├── devloops/
    │   ├── kit.py                     # NEW: kit root, mode, reserved paths, command (P-2)
    │   ├── project.py                 # NEW: discovery, project/local config, path resolution (P-3, P-4, P-6)
    │   ├── initcmd.py                 # NEW: init, --upgrade, manifest, .gitignore, --allow-skills, prompts (P-12, P-13)
    │   ├── checkcmd.py                # NEW: devloops check (P-14)
    │   ├── speckit.py                 # NEW: feature resolution, tasks.md parser, story headings (P-16)
    │   ├── fulldash.py                # NEW: full dashboard and conversation rendering (P-10, P-11)
    │   ├── cli.py                     # new commands/options, project resolution, version warning, full-dashboard hook
    │   ├── config.py                  # project and local layers; derived MCP command; drift computation (P-4, P-5, P-15)
    │   ├── workspace.py               # workspaces_dir, relative paths, new guard (P-6)
    │   ├── engine.py                  # Kit instead of repo_root; spec-kit inputs; prompt-source events
    │   ├── claude.py                  # prompt overrides + prompt_sources; conversation copy (P-8, P-9)
    │   ├── plan.py                    # spec-kit coverage and phase-order checks (P-16)
    │   ├── inputs.py                  # spec-kit inputs, US<n> story matching
    │   ├── orchestrator.py, render.py, boundary.py, dashboard.py, state.py   # Kit paths, plan-summary lists, full-dashboard links, new event
    │   └── __init__.py                # __version__ = "0.2.0" (P-18)
    └── tests/                         # + test_kit, test_project, test_init, test_upgrade, test_check,
                                       #   test_speckit, test_prompt_overrides, test_conversations,
                                       #   test_full_dashboard, test_packaging; TempEnv writes a devloops.json
.devloops/devloops.json  .devloops/manifest.json  .devloops/prompts/README.md   # NEW: this repository as a project (P-17)
.claude/skills/devloops-*/SKILL.md     # rendered by init; replaces .claude/skills/loops-*
```

**Structure decisions**:
- `loops/` stays the kit's source; packaging maps it, so nothing moves [RC, P-1].
- The new behavior goes into new modules. The existing modules change only where `repo_root`
  splits into kit and project, or where spec-kit inputs and conversations plug in (Principle VI).
- This repository becomes a project with `workspaces_dir: "workspaces"` and tracked workspaces, so
  001's committed evidence stays in place [RC, P-17].

## Key flows

### Command start (all commands except `init` and `check`)

```mermaid
sequenceDiagram
    participant Dev as Developer
    participant CLI as devloops CLI
    participant P as project
    participant K as kit
    participant E as engine / orchestrator
    Dev->>CLI: devloops orchestrate --speckit-feature (from a subfolder)
    CLI->>K: resolve kit (source or installed)
    CLI->>P: find .devloops/devloops.json upward
    P-->>CLI: root, merged shared + local config, manifest
    CLI->>CLI: warn on version mismatch (FR-029)
    CLI->>P: resolve workspace (default "main"), targets, requirements
    CLI->>E: run with resolved options (layers: defaults < shared < local < --config < flags)
    E-->>CLI: final status
    CLI->>CLI: lightweight dashboard; full dashboard when the status is final (FR-039)
```

### One Claude call (additions to 001)

1. Compose the prompt from override-or-packaged parts, and record `prompt_sources` (P-8).
2. Run `claude -p` as in 001.
3. Copy `<CLAUDE_CONFIG_DIR>/projects/<encoded cwd>/<session>.jsonl` into
   `state/conversations/`, redacted. Record `conversation_path` or `unavailable` (P-9).

## Implementation order (for /speckit-tasks)

1. **Foundation**: `kit` + `project` + `config` layers + `workspace` paths and guard, with
   `TempEnv` updated. The whole 001 suite must stay green before anything else (SC-008).
2. **US1** `init` (with interactive questions, the manifest, and the ignore block) + the skill
   templates + migrating this repository.
3. **US2** project defaults in `run`/`orchestrate`, drift in `status`, and the visible-browser
   settings.
4. **Full dashboard**: conversation copies, `fulldash`, and the command hooks (clarifications 1, 6–8).
5. **US3** `check`.
6. **US4** skills polish + `--allow-skills`.
7. **US5** the spec-kit bridge.
8. **US6** `--upgrade`.
9. **US7** prompt overrides.
10. **Polish**: packaging test, README, and the real run (SC-007), recorded in
    `validation-results.md`.

## Known limitations (accepted)

- **A target cannot be the project root**, because `.devloops/` and the workspaces live inside it.
  Each loop gets a subfolder [RC, P-6].
- **Transcript rendering depends on an undocumented format.** It is rendered defensively, and raw
  JSON is shown for unknown records [RD, P-9].
- **Conversations of pre-002 calls** are recovered only while Claude Code still holds them
  (30-day default retention).

## Complexity Tracking

| Addition | Why needed | Simpler alternative rejected because |
|----------|------------|---------------------------------------|
| Build-time dependency on setuptools | Installing as a tool requires a PEP 517 backend (FR-001) | A zipapp gives no console script, no upgrade path, and no `uv tool` support |
| Two-package mapping (`devloops_kit` → `loops/`) | Ships the assets with no file moves | Moving to `src/` would rewrite 001's layout docs and every test path |
| Fingerprint manifest | The only way to tell "changed locally" from "older version" on upgrade (FR-027) | Overwrite-always loses edits; never-overwrite leaves projects stale |
| Conversation copies in the workspace | Claude Code deletes transcripts after 30 days, and the full dashboard must stay complete (FR-042) | Reading the history at render time loses data silently |
| Deterministic `tasks.md` parser + plan coverage check | Makes "the plan follows spec-kit" verifiable (FR-023a/b, Principle III) | Prompt-only guidance cannot be checked |
