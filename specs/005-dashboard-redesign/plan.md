# Implementation Plan: Dashboard Redesign

**Branch**: `005-dashboard-redesign` (work is committed on `main`) | **Date**: 2026-10-09 |
**Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/005-dashboard-redesign/spec.md` (8 clarifications in
Session 2026-10-09). Plan scope confirmed by the developer: the agreed scope (A1, A2, A3, A5, B6,
B8, B10) and both reported bugs; browser actions and cross-run history are designed for, not built.

**Decision tags**: the same as 001's to 003's plans.

| Tag | Meaning |
|-----|---------|
| **[ER]** | Explicit requirement (spec FR, SC, or clarification) |
| **[RD]** | Repository-derived (verified in this repository) |
| **[RC]** | Recommendation (the rationale is in [research.md](./research.md), R-n) |

## Summary

The dashboard becomes one plain-JavaScript app that the server feeds with JSON, one request per
view, and that the export carries with its data inside.

**What changes**:
- **Server sends data, not pages:** `serve.py` answers `/w/<ws>/api/…` with redacted JSON built by
  `dashboard.py`, cached by workspace version; the page is a small shell plus one script and one
  stylesheet [ER: FR-002, FR-006, FR-007; RC: R-1, R-2].
- **The app:** `assets/app/` holds the shell, the stylesheet, and one script per concern and per
  view, joined in a fixed order; a hash router; an API layer that fetches (served) or reads
  embedded data (export); following a run refreshes only the open view [ER: FR-003, FR-004,
  FR-024, FR-028, FR-029; RC: R-1, R-3, R-4].
- **Serving modes:** foreground by default, `--daemon`, `--stop`; `--serve`/`--open` removed
  [ER: FR-001, FR-001a; RC: R-11].
- **Summary page and full dashboards removed:** commands write no dashboard file and print the
  server's address or `devloops dashboard --daemon`; `--export` writes one self-contained file to
  `<workspace>/exports/` or a given path [ER: FR-008–FR-015; RC: R-5].
- **New views:** now panel (A1), tokens and cost at every level (A2, the developer's bug 1), trial
  view with "why it failed" (A3, B6), plan view (A5), conversation upgrades (B8), faster search
  (B10) [ER: FR-016–FR-022; RC: R-7–R-10].
- **Markdown fix** (the developer's bug 2): multi-line list items keep all their lines [ER: FR-025;
  RC: R-12].
- **Docs and skills:** the dashboard skill, the run/decision skills' JSON fields, the README, and
  the 001/002 contracts [ER: FR-031, FR-032].

**What does not change**: the engine's behaviour, run records (one new view file, `live.json`,
R-8), exit codes of run and decision commands, the server's protections, redaction rules, the
file kinds and viewers, and the conversation rendering rules.

## The two reported problems

| Problem | Where it is solved |
|---------|--------------------|
| 1. Tokens per loop | R-9 / FR-017: loop cards and loop view show tokens (with input, output, cache write, cache read, cache-hit rate, cost per milestone achieved); the same totals at milestone, trial, step, and call |
| 2. Markdown list item cut to its first line | R-12 / FR-025: the root cause is in `assets/dashboard.js` `list()` (a one-paragraph item's `<p>` is replaced by its first child only); `md.js` builds a tree and unwraps every child, with Node tests |

## Technical Context

**Language/Version**: Python ≥ 3.10, standard library only at runtime (unchanged) [RD]; browser
code in plain JavaScript (ES2020, no modules, no build) [ER: FR-028].

**Primary Dependencies**: none new. `http.server` (unchanged), `subprocess` for `--daemon`.

**Storage**: the workspace's existing JSON/JSONL records; new view file `<loop>/state/live.json`;
exports under `<workspace>/exports/`. The server's record and the daemon's log in the user's
runtime folder (unchanged location) [RD; RC: R-8, R-11].

**Testing**:
- `unittest` with the fake `claude`: `VISUAL=true EDITOR=true timeout 900 python3 -m unittest
  discover -s loops/shared/tests` (655 tests, 2 skipped today) [RD].
- Browser logic with `node --test` from a Python test, skipped without node (test-only tool)
  [RC: R-13].

**Target Platform**: Linux and macOS developer machines; current desktop browsers.

**Project Type**: CLI tool with packaged assets (`pyproject.toml` package data `assets/*` becomes
`assets/app/**/*`).

**Performance Goals**: first view usable ≤ 1 s and any other view ≤ 1 s on 200 calls / 5,000 files
(SC-001, SC-002); search first results ≤ 1 s (SC-006). Baseline today: 0.8 s server render of a
2.9 MB page, then a whole-page parse in the browser (research, Baseline).

**Constraints**: no network resources; redaction before anything leaves the server; read-only
server; no build step; the export works from `file://`.

**Scale/Scope**: workspaces up to a few hundred calls, thousands of files, and tens of MB.

## Constitution Check

*GATE: before Phase 0 research, and again after Phase 1 design.*

| Principle | Check | Result |
|-----------|-------|--------|
| I. Requirements-driven | Every change traces to an FR/SC or a recorded clarification; assumptions are listed in the spec and the R-8 revision is recorded there | Pass |
| II. Reusability | The dashboard reads loop records only; nothing application-specific | Pass |
| III. Incremental and verifiable | Delivered by user story (P1 first); each has an independent test; SC timings and SC-004/005/008 are checked by tests | Pass |
| IV. Controlled and recoverable automation | The engine's state is untouched; `live.json` is a view file, ignored when stale | Pass |
| V. Bounded execution | Not affected (no loop behaviour change) | Pass |
| VI. Separation of concerns | View data (`dashboard.py`), files and conversations (`artifacts.py`), HTTP (`serve.py`), export (`dashboard_export.py`), and UI (`assets/app/`) are separate; one script per view | Pass |
| VII. Existing infrastructure first | Reuses the server, its protections, version digest, redactor, file listing, kinds, viewers, and conversation rules; adds no dependency | Pass |
| VIII. Testability and traceability | API, export, CLI tested in `unittest`; browser logic tested with Node when present; fixtures are not app-specific | Pass |
| IX. Documentation | README, skills, and 001/002 contracts updated (FR-031, FR-032) | Pass |
| X. Simplicity | No framework, no build, no streaming server; three removed outputs become two; see Complexity Tracking | Pass |

**Post-design re-check (after Phase 1)**: unchanged — all pass. The design adds one view file
(`live.json`, R-8) and an optional test tool (Node, R-13), both recorded below.

## Project Structure

### Documentation (this feature)

```text
specs/005-dashboard-redesign/
├── plan.md              # this file
├── research.md          # R-1 to R-14, baseline timings
├── data-model.md        # view data shapes, live call, export
├── quickstart.md        # validation guide
├── contracts/
│   ├── api.md           # server routes and data rules (replaces 002 full-dashboard.md "Live dashboard")
│   ├── cli.md           # dashboard command, run/decision output, init, configuration
│   └── export.md        # the export file (replaces 002 full-dashboard.md file sections)
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
loops/shared/devloops/
├── dashboard.py         # view data: collect_loop, totals, one builder per API route (no HTML)
├── artifacts.py         # from fulldash.py: file listing, kinds, sniffing, redactor, conversations
├── serve.py             # HTTP server, API routes, assets, --daemon/--stop
├── dashboard_export.py  # new: the export writer
├── progress.py          # + LiveCall writer hooks (live.json)
├── claude.py            # owns the LiveCall for each call
├── cli.py               # dashboard options; summary page and full-dashboard writes removed
├── initcmd.py           # --track-dashboards and dashboards_dir removed
├── config.py            # removed keys reported with a "delete it" message
├── ui.py, fulldash.py   # removed
└── assets/
    └── app/
        ├── index.html   # the shell (sidebar, top bar, now panel slot, view slot, viewer, palette)
        ├── app.css      # from dashboard.css
        ├── icons.svg    # the sprite (from ui.py)
        ├── scripts.txt  # the join order
        ├── core.js      # DOM helpers, store, theme, icons, format (money, tokens, durations)
        ├── api.js       # fetch or embedded source, response cache, version polling, offline
        ├── router.js    # route table, hash routing, view lifecycle, keep/restore
        ├── md.js        # Markdown → tree → DOM (bug fix)
        ├── highlight.js # syntax highlighting, JSON tree
        ├── viewer.js    # file viewer dialog and kinds
        ├── charts.js    # bar chart, trial timeline
        ├── palette.js   # go to + search
        ├── now.js       # the now panel
        ├── views/       # overview, run, loop, plan, trial, calls, conversation, files,
        │                #   questions, events (one file each)
        └── tests/       # node --test: md, router, format, totals, search
loops/shared/tests/
├── test_dashboard_data.py   # totals, view builders, redaction (replaces test_dashboard.py)
├── test_serve.py            # routes, caching, safety, daemon/stop
├── test_dashboard_export.py # export file (replaces test_full_dashboard.py's file checks)
├── test_live_call.py        # live.json lifecycle
├── test_dashboard_cli.py    # options, removed outputs, output hints, JSON fields
└── test_app_js.py           # node --check on the joined script, node --test on assets/app/tests
loops/shared/skills/devloops-run/SKILL.md (the dashboard and decision skills were removed)
loops/shared/schemas/config.schema.json, project-config.schema.json
loops/README.md; specs/001-…/contracts/{cli.md,workspace-layout.md}; specs/002-…/{spec.md,
contracts/cli.md, contracts/full-dashboard.md, contracts/skills.md, contracts/project-layout.md}
pyproject.toml           # package data assets/app/**
```

**Structure Decision**: Single project, as today. The dashboard stays inside the `devloops`
package; its browser code is package data under `assets/app/`.

## Delivery order (for /speckit-tasks)

1. **Foundation**: `artifacts.py` split, API skeleton with caching, the shell and core scripts,
   router and API layer, Markdown fix — then the overview and loop views with tokens (US1 + bug 1
   + bug 2: the MVP).
2. **US2**: now panel (`live.json`) and totals at every level.
3. **US3**: trial view and "why it failed".
4. **US4**: plan view. **US5**: conversation view. **US6**: search index.
5. **US7**: export. Then `--daemon`/`--stop`, removal of the summary page, full dashboards, old
   modules and keys, and docs/skills.

## Complexity Tracking

| Addition | Why Needed | Simpler Alternative Rejected Because |
|----------|------------|-------------------------------------|
| `live.json` view file (R-8) | The now panel needs the running call and its tools as they happen | Parsing `run.log` ties the UI to a human-readable format; reading Claude Code's own files depends on its internals |
| Node as an optional test tool (R-13) | The Markdown parser, router, and search are logic worth unit tests | No browser test runner in the standard library; a headless browser is a far heavier test dependency |
| Server-side search index (R-10) | SC-006 (≤ 1 s) on tens of MB | Today's per-search re-read and re-redaction of every file is what makes search slow |
