# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

devloops drives headless Claude Code (`claude -p`) through two development loops that turn
requirements into validated code, one milestone at a time: `backend-dev` (validated by real HTTP
requests, publishes a verified OpenAPI document) and `frontend-dev` (validated in a real browser via
the Playwright MCP server, checked against that document). `devloops run` runs the loops a project
uses, in one workspace. The model's own claims are never trusted: a milestone passes only when the
driver's validation passes. User documentation is `loops/README.md`.

The runtime is Python ≥ 3.10, **standard library only** (no runtime dependencies; setuptools only
to build). Run it from the checkout with `bin/devloops <command>`. This repository is not itself
a devloops project (no `.devloops/`, no `devloops-*` skills): try the loops on another project,
e.g. `cd <app> && <this checkout>/bin/devloops run`. The skills `devloops init` installs are
templates in `loops/shared/skills/`.

## Commands

Run tests from the repository root. `VISUAL=true EDITOR=true` keeps a plan-review prompt from
opening your real editor.

```sh
# Full suite (offline, uses a fake `claude`; ~10 minutes, so run it in the background)
VISUAL=true EDITOR=true python3 -m unittest discover -s loops/shared/tests

# One module, or one test (from the tests folder, where `helpers` is importable)
VISUAL=true EDITOR=true python3 -m unittest discover -s loops/shared/tests -p 'test_serve.py'
cd loops/shared/tests && VISUAL=true EDITOR=true python3 -m unittest test_serve.ServeTest.test_read_only

# The dashboard app's browser code (node is a test tool only; test_app_js runs these too)
node --test loops/shared/devloops/assets/app/tests/
```

- `DEVLOOPS_TEST_PACKAGING=1` (with `uv` on PATH) enables `test_packaging.py` (builds the wheel).
- `DEVLOOPS_SKIP_PERF=1` skips `test_dashboard_perf.py` on a slow or busy machine.
- There is no linter or formatter configured.

## Architecture

- **Kit vs. project.** `loops/` is the *kit* (loop definitions, prompts, schemas, hooks, defaults,
  skill and project templates), shipped as the `devloops_kit` package; `loops/shared/devloops/` is
  the driver, shipped as `devloops` (see `pyproject.toml`). A *project* is any folder with
  `.devloops/devloops.json` (`devloops init`); its *workspaces* hold all run state.
- **Driver flow.** `cli.py` → `orchestrator.py` (which loops a run includes, their order, the
  backend→frontend handoff; `run/state.json`) → `engine.py` (one loop: plan, approve, then per
  milestone implement/fix trials and validation) → `claude.py` (each `claude -p` call, its
  invocation record and copied transcript). Validators are in `devloops/validators/` (`curl.py`,
  `playwright.py`, `unit_tests.py`); `boundary.py` and `loops/shared/hooks/` keep writes inside
  the loop's target.
- **State is files.** Everything is in `<workspace>/<loop>/state/` (`run.json`, `plan.json`,
  `invocations.jsonl`, `events.jsonl`, `milestones/<id>/trials/<n>/…`) and `outputs/`; a run
  resumes from it. Writes are atomic (`state.py`). JSON shapes are in `loops/shared/schemas/`.
- **Dashboard** (being redesigned by spec 005): `serve.py` is a stdlib HTTP server whose JSON API
  is built by builder functions in `dashboard.py` (registered in `serve.API`) and `artifacts.py`
  (file listing, file contents, conversations), every answer redacted. The browser app is plain
  JavaScript in `assets/app/` (no framework, no build), joined by `appbundle.py` in the order of
  `assets/app/scripts.txt`. `ui.py`, `fulldash.py`, the HTML parts of `dashboard.py`, and
  `assets/dashboard.{js,css}` are the old server-rendered dashboard, pending removal (spec 005
  T051–T053).
- **Tests** run the real CLI against temporary checkouts with a fake `claude`
  (`tests/fake_claude.py`, driven by scenario files; see `helpers.py` and `stub_loop.py`).

## Rules that tests enforce

- **No application specifics** in the loops, prompts, defaults, or driver code
  (`test_no_app_specifics.py`; constitution II): requirements, targets, and config are inputs.
- **Schemas are byte-identical to their spec contracts** (`test_schemas_sync.py`): change a schema
  in `specs/<feature>/contracts/` and `loops/shared/schemas/` together.
- **Browser code** (`test_app_js.py`): every `.js` file is listed in `scripts.txt`; no
  `innerHTML`/`outerHTML`/`insertAdjacentHTML`/`document.write` (build DOM with `DL.el`/`DL.add`;
  model-written text is only ever `textContent`); no `style=` attributes or inline scripts (the
  page's CSP is `script-src 'self'; style-src 'self'`); nothing loads from outside the page. Each
  file is an IIFE over `window.DL` and touches no DOM when it loads, so its pure parts run under
  `node --test` (`tests/load.js`).

## Specs and process

- Features are specified with spec-kit (`.specify/`, `/speckit-*` skills) in `specs/<NNN-name>/`
  (`spec.md`, `plan.md`, `tasks.md`, `contracts/`, `data-model.md`, `research.md`). Mark tasks
  `[X]` in `tasks.md` as they are done. Code comments and docstrings cite requirement IDs
  (`FR-…`, `SC-…`, research `R-…`) from these specs.
- `.specify/memory/constitution.md` governs design; plans include a constitution check.
- When a later spec changes earlier behavior, the earlier spec and `loops/README.md` get a
  "Changed by / Revised by spec NNN" note in place, and the README must describe the implemented
  system.
- devloops is in development: breaking changes need no migration path (no shims or deprecations).
