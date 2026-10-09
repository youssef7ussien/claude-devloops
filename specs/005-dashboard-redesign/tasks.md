---

description: "Task list for 005: dashboard redesign"
---

# Tasks: Dashboard Redesign

**Input**: Design documents from `specs/005-dashboard-redesign/` (spec.md, plan.md, research.md,
data-model.md, contracts/api.md, contracts/cli.md, contracts/export.md, quickstart.md)

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Included. Each story has an independent test, and SC-004, SC-005, SC-007, SC-008, and
SC-009 are checked by tests. Run the suite with `VISUAL=true EDITOR=true timeout 900 python3 -m
unittest discover -s loops/shared/tests` (655 tests, 2 skipped, about 9 minutes before this
feature). Run one module with `-p 'test_x.py'` from the repository root (modules need `import
helpers` first).

**Organization**: Tasks are grouped by user story. Paths are repository-relative. Python code is
in `loops/shared/devloops/`, browser code in `loops/shared/devloops/assets/app/`, tests in
`loops/shared/tests/`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: The user story the task belongs to (US1–US7)

## Keeping the suite green (used by every phase)

The old outputs stay until their replacement lands, so every phase ends with a passing suite:
- the **served page** switches to the new app in US1 (the old served HTML route and its tests go
  then);
- the **summary page** (`dashboard.html`) and the **full dashboard** (`fulldash.render_full`) keep
  using the old HTML functions of `dashboard.py` and `ui.py` until US7 and Phase 10 remove them;
- new data builders are added to `dashboard.py` next to the old HTML functions, which Phase 10
  deletes.

## Browser code rules (used by every JS task)

- Plain JavaScript (ES2020), no modules, no build: each file starts with
  `(function (DL) { 'use strict'; … })(window.DL = window.DL || {});` and adds to `DL`.
- Logic that does not need the DOM (parsing, routing, formatting, sums, matching) lives in
  functions that take and return plain values, so `node --test` can load the file with a stub
  `window` (`assets/app/tests/load.js`).
- Model-written and file text is only ever set with `textContent` or built as elements; never
  `innerHTML` (FR-026).
- A new file is added to `assets/app/scripts.txt` in dependency order; `test_app_js` fails for a
  `.js` file under `assets/app/` (except `tests/`) that is not listed.

---

## Phase 1: Setup

**Purpose**: the app's folder, packaging, and the browser test harness.

- [X] T001 Create `loops/shared/devloops/assets/app/` with `scripts.txt` (one path per line, in join order: `core.js`, `api.js`, `router.js`, `md.js`, `highlight.js`, `viewer.js`, `charts.js`, `palette.js`, `now.js`, then `views/*.js`, then `main.js`), and update `pyproject.toml` package data from `devloops = ["assets/*"]` to `devloops = ["assets/*", "assets/app/*", "assets/app/views/*"]` (tests are not packaged). Update `loops/shared/tests/test_packaging.py` if it lists package data.
- [X] T002 [P] Add `loops/shared/devloops/appbundle.py` with `script()` (the files of `scripts.txt` joined with a `\n;\n` separator, read once and cached), `stylesheet()` (`app.css`), `shell(attrs)` (`index.html` with `{{…}}` placeholders filled and HTML-escaped: title, workspace, `data-*` attributes), and `ASSETS_VERSION` (the devloops version plus a short hash of the joined script).
- [X] T003 [P] Add `loops/shared/tests/test_app_js.py`: every `.js` under `assets/app/` (except `tests/`) is listed in `scripts.txt` and every listed file exists; `node --check` passes on `appbundle.script()` written to a temp file; `node --test loops/shared/devloops/assets/app/tests/` passes. Both node tests are skipped when `shutil.which("node")` is None (as `test_dashboard_ui.test_the_script_parses`). Without node, also check the sources (FR-026, FR-027): no `.js` under `assets/app/` (except `tests/`) contains `innerHTML`, `outerHTML`, `insertAdjacentHTML`, or `document.write`; `app.css` and `index.html` contain no `@import`, no `url(http`, and no `src=`/`href=` to `http:`/`https:` other than the project's GitHub link. Add `assets/app/tests/load.js`, which evaluates the listed files in a `vm` context with a stub `window`/`document` and returns `DL`.

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: data helpers, the API skeleton, the app shell, and the shared browser modules. Every
story depends on these. Includes the Markdown fix (the developer's bug 2).

### Python

- [X] T004 Create `loops/shared/devloops/artifacts.py` by moving from `fulldash.py` everything that is not HTML: `workspace_redactor`, `_classify`, `_walk`, `collect_artifacts`, `_label`, `read_conversation`, `human_bytes`, `sniff`/`_sniff`, `viewer_text`, `_json_text`, `MAX_EMBED_BYTES`, `EDIT_TOOLS`, `CALL_FILE`, `PLAN_OUTPUTS`, `call_id`; and from `ui.py` the file kinds (`KINDS`, `kind_of`, `looks_like_json`, `IMAGE_TYPES`). `fulldash.py` and `ui.py` import them from `artifacts` (no behaviour change). Update imports in `serve.py` and the tests that use the moved names.
- [X] T005 Add to `artifacts.py`: `file_content(path, redactor, max_bytes)` → `{kind, lang, size, text}` for text (redacted; JSON indented), `{kind, size, type, base64}` for images and other binary files, `{kind: "large", size, not_embedded: true}` over `max_bytes`, or None when unreadable; and a file listing `file_index(ws, data)` → `(trees, by_id)` where each tree node is `{name, children?, file?: {id, path, kind, lang, size, version, missing?}}` in today's order (per loop: Inputs, Plan, Milestones → each trial → evidence, Calls, Outputs, Run state, `progress.md`; then `run/` and the workspace's own files), ids as today's anchors (`f-<slug>`), and `by_id` mapping each id to its real path (inputs flagged as allowed outside the workspace). Port the logic of `fulldash.loop_tree`, `other_trees`, and `LazyEmbedder.item` without HTML.
- [X] T006 Add `artifacts.parse_conversation(text, redactor)` → `{records, errors, files_changed}` (research R-7): each JSONL line parsed and redacted (`redactor.redact_obj`), an unparsable line as `{"raw": <redacted text>}`, a line separator inside a string not splitting a record (as `_conversation_hit` handles today); `errors` = indexes of records holding a `tool_result` with `is_error: true`; `files_changed` = `[{path, tool, block}]`, one per path (the last change), from `tool_use` blocks named in `EDIT_TOOLS` (`file_path` or `notebook_path` input). Add tests in `loops/shared/tests/test_conversations.py` (records, raw line, errors, files changed with a repeated path keeping the last).
- [X] T007 Add totals to `dashboard.py` (research R-9, data-model Totals): `totals(records)` → `{calls, cost, tokens: {input, output, cache_creation, cache_read, total}, partial, seconds}` where `partial` is true when any record lacks `tokens` or `cost_usd`; `add(*totals)` for summing levels (partial propagates); `loop_extras(totals, achieved)` → `cache_hit_rate` (`cache_read / (input + cache_creation + cache_read)`, null when 0) and `cost_per_achieved` (null when none achieved). In `collect_loop`, add `totals` at call, step-within-trial (`steps: [{step, totals, calls}]` in run order), trial, milestone, planning, and loop level, keeping the existing keys the old HTML still reads.
- [X] T008 Add `loops/shared/tests/test_dashboard_data.py` with a `StubLoopMixin` run (completed, plus one with a failed trial and a voided re-run, as `test_dashboard.test_a_voided_trial_and_its_rerun_keep_their_own_calls`): for every loop, milestone, trial, and step, totals equal the sum of the recorded calls (SC-004); a record without `tokens` makes every level above it `partial`; `cache_hit_rate` and `cost_per_achieved` as defined.
- [X] T009 Add the API skeleton to `serve.py` (contracts/api.md): a route table `API = [(regex, builder_name)]` dispatched under `/w/<ws>/api/`; each builder is a `dashboard.py` function `(ws, **params) -> dict`; responses are `json.dumps(redactor.redact_obj(data))`, `application/json`, with `X-Devloops-Version`; unknown params → 404 `{"error": …}`; a per-workspace cache `{(path, query): body}` dropped when `Site.version(ws)` changes (FR-007); keep `version`, the host check, the token, GET/HEAD-only (501 otherwise), and the security headers. Add `/assets/app.js` and `/assets/app.css` from `appbundle` (`Cache-Control: max-age=31536000, immutable`, keyed by `?v=ASSETS_VERSION`) and serve `/w/<ws>/` as `appbundle.shell(...)` with `data-source="api"`, `data-poll=POLL_SECONDS`, `data-workspace`, `data-version`, under the page CSP of research R-6 (`script-src 'self'; style-src 'self'`). Keep `file/<anchor>` as `api/files/<id>` using `artifacts.file_index` for the listing.
- [X] T010 Remove the old served HTML page from `serve.py` (`Site.rendered`/`page` using `fulldash.render_full`, the `call/<loop>/<seq>` fragment route) and make `Site.file` and `Site.search` use `artifacts.file_index`'s `by_id`. Rewrite `loops/shared/tests/test_serve.py` for the API, using a stub builder the test registers in `serve.API` (the real builders arrive in T021; the checks that need `summary` and the other views go in T019): shell and assets served with the CSP; a JSON response holding `SECRET` arrives redacted; a builder runs once per version (request twice, change a workspace file, request again); unknown loop/call/file → 404 JSON; only listed files sent; and keep the existing safety tests (read-only 501, loopback host check, token cookie, token beyond loopback, `--no-token`, server record, workspace not found).

### Browser

- [X] T011 [P] Create `assets/app/index.html` (the shell: sidebar with brand, workspace switcher `<select>`, navigation list; top bar with breadcrumb, status pill, Live/Paused/Offline button, theme button, search button; `<section id="now">`; `<main id="view">`; the viewer `<dialog id="viewer">`; the palette `<dialog id="palette">`; `<noscript>` saying the dashboard needs scripts; `<link href="/assets/app.css?v={{v}}">` and `<script src="/assets/app.js?v={{v}}" defer>`), `assets/app/icons.svg` (the sprite from `ui.sprite()`, inlined into the shell by `appbundle.shell`), and `assets/app/app.css` (from `assets/dashboard.css`: keep the tokens, light/dark themes, layout, cards, pills, tables, explorer, viewer, palette, charts; drop selectors only the old page used).
- [X] T012 [P] Create `assets/app/core.js`: `$`, `$$`, `el`, `icon`, `btn`, `store` (try/catch localStorage), theme toggle (as `dashboard.js`), and pure formatters `DL.fmt.money`, `number`, `duration`, `tokens` (e.g. `12.3k`), `percent`, `time` matching `dashboard.money/number/duration`; add `assets/app/tests/format.test.js`.
- [X] T013 [P] Create `assets/app/api.js`: `DL.api.source` = `"api"` or `"embedded"` from the root's `data-source`; `get(path)` returns a promise of JSON (served: `fetch` with `credentials: 'same-origin'`, `cache: 'no-store'`; embedded: parse `<script type="application/json" id="d:<path>">` once, unescaping nothing beyond JSON); `text(path)` for file contents; an in-memory cache dropped by `invalidate()`; `follow()`: every `data-poll` seconds while `!document.hidden` and not paused, `GET version`; on change `invalidate()` and emit `DL.api.on('changed')`; on failure set offline and emit `'offline'`; Live button toggles pause (stored). Embedded: no polling.
- [X] T014 [P] Create `assets/app/router.js` (research R-4): `DL.router.parse(hash)` → `{view, params, query}` and `href(view, params, query)` for the routes `#/`, `#/run`, `#/loop/<loop>`, `#/loop/<loop>/plan`, `#/loop/<loop>/m/<id>/t/<key>`, `#/calls`, `#/call/<loop>/<seq>`, `#/files`, `#/file/<id>`, `#/questions`, `#/events` (pure); `DL.router.register(name, {title, data(params) -> [paths], render(data, params, el)})`; `go`/`popstate`; mounting renders into a new element and swaps it in only after its data arrived; on `'changed'`, re-mount only the open view, keeping open `<details>`, typed filters, pressed chips, scroll, and focus (port `keep`/`restore` from `dashboard.js`); unknown route → overview. A view's responses must come from one workspace version: when the `X-Devloops-Version` of its responses differ (served) the router invalidates and fetches the view's paths once more before rendering (spec Edge Cases). Add `assets/app/tests/router.test.js` covering `parse`/`href`, the version re-fetch, and that on `'changed'` only the mounted view's `data()` paths are requested (SC-003).
- [X] T015 [P] Create `assets/app/md.js` (research R-12; FR-025, the developer's bug 2): port `INLINE`, `inline`, `blocks`, `list`, `cells`, `isBlockStart` from `assets/dashboard.js` to build a plain tree `{t, c, a}` (`DL.md.parse(src)`), and `DL.md.render(src)` → DOM via `toDom` (links to files resolved through a callback; other links shown as non-followed spans, as today). Fix the bug: when a list item's body is one paragraph, the item takes **all** the paragraph's children (today `li.replaceChild(li.firstChild.firstChild, …)` keeps only the first). Add `assets/app/tests/md.test.js` covering: the reported case (`- Work only on … milestone\nand its listed tasks.` → one item with the whole text), a wrapped item followed by another item, nested lists, a task item, a table, a fenced code block, emphasis and code spans, and a blank line inside an item.
- [X] T016 [P] Create `assets/app/highlight.js` (port `codeView`, the language rules, `langOf`, `pretty`, and `jsonTree` from `assets/dashboard.js`) and `assets/app/viewer.js` (port the viewer dialog: `VIEWERS` per kind, modes, wrap/line-number prefs, siblings navigation, a file over 20 MB asks first; contents from `DL.api.text('files/<id>')` served, or the embedded `{text|base64}`; images from the served URL or a `data:` URI; a file open in the viewer whose `version` changed is reloaded at the same scroll position, or its end when scrolled to the end; `DL.viewer.open(fileRef, {line})`).
- [X] T017 [P] Create `assets/app/charts.js`: `DL.charts.bars(rows, {format, title, columns})` and `DL.charts.timeline(loops)` as DOM (port `dashboard.bar_chart` and `dashboard.timeline`, keeping their accessible hidden table and `data-tip` tooltips), with timeline bars linking to `DL.router.href('trial', …)`.
- [X] T018 Create `assets/app/main.js`: on `DOMContentLoaded`, bind the theme, the workspace switcher (served: `location.assign('../<name>/')`), the Live button, the menu; load `summary` to build the navigation (Overview, Run when present, one entry per loop with its status dot, Calls, Files, Questions with a count, Events) and the status pill; start `DL.api.follow()`; mount the route in the address. Re-render the navigation and status on `'changed'`.

**Checkpoint**: the shell opens, navigation and routing work, the Markdown and format tests pass,
and the API answers with redacted, cached JSON.

---

## Phase 3: User Story 1 - A dashboard that opens fast and follows the run (Priority: P1) 🎯 MVP

**Goal**: every existing view in the new app, each loading only its own data, refreshing in place
during a run; loop cards and the loop view show tokens (the developer's bug 1); the server runs in
the foreground or as a daemon, and stops on request.

**Independent Test**: serve a workspace with many calls and files; refresh — only `summary`,
`now`, and `version` are requested and the overview is usable within 1 s; open other views — each
requests only its own data; change a workspace file — only the open view reloads; run
`devloops dashboard` twice — one server.

### Tests for User Story 1

- [X] T019 [P] [US1] In `loops/shared/tests/test_dashboard_data.py`, test the builders of T021: `summary` (loops with status, next action, milestones, trials, first-try, totals including tokens; `attention` items of every kind of today's panel, each with a `route`; `workspaces`; `running`), `loop` (totals with breakdown, planning, milestones with trial summaries and `route`, `by_step`, outputs as file refs), `calls` (one `CallRef` per record with `route` and `conversation` state, cost by model), `events`, `questions`, `files` (trees and count). Also, through the server (`test_serve.py`): `api/summary` and `api/loops/<loop>` answer redacted (`SECRET` absent) and `api/summary` lists the workspaces to switch to.
- [X] T020 [P] [US1] In `loops/shared/tests/test_dashboard_perf.py`, generate a workspace with 200 calls (invocation records and copied conversations) and 5,000 small files, and assert that a cold `GET api/summary` (version computed, cache empty) answers within 1 s and a warm one within 0.1 s on the test machine (SC-001 server side); mark it to skip when `DEVLOOPS_SKIP_PERF=1`.

### Implementation for User Story 1

- [X] T021 [US1] Add the builders to `dashboard.py` (data-model Workspace summary, Loop, CallRef, Files, Events, Questions): `summary(ws)`, `loop(ws, loop)`, `calls(ws)`, `files(ws)`, `events(ws)`, `questions(ws)`; convert `attention()` and `_next_action()` to return data (text plus `route`) — the old HTML functions call the new data versions; register the routes in `serve.API`.
- [X] T022 [P] [US1] Create `assets/app/views/overview.js`: KPI row (status, milestones achieved, first-try rate, trials, calls, cost, **tokens**, elapsed), the Needs-attention panel (each item links to its route), loop cards (progress, milestones, trials, calls, cost, **tokens**, duration, next action), the trial timeline, cost by milestone and cost by step charts; empty workspace message.
- [X] T023 [P] [US1] Create `assets/app/views/run.js` (steps table with status, reason, started, ended; handoff card) and `assets/app/views/loop.js` (status reason and next action callouts; KPIs including **tokens** with input/output/cache write/cache read; outputs toolbar opening files in the viewer; UI URL; milestones with their trials, each trial linking to the trial route; links to the plan view and calls).
- [X] T024 [P] [US1] Create `assets/app/views/calls.js` (filterable calls table: loop chips, text filter, columns as today, cost by model when more than one; a row opens `#/call/<loop>/<seq>`), `assets/app/views/questions.js`, and `assets/app/views/events.js` (filterable table).
- [X] T025 [P] [US1] Create `assets/app/views/files.js`: the explorer from `api/files` (folders, kind chips, filter, arrow keys as today), a file opens in `DL.viewer`; `#/file/<id>` opens the explorer with that file in the viewer.
- [X] T026 [US1] Add to `cli.py` the serving modes (contracts/cli.md): `devloops dashboard` serves in the foreground (no `--serve` needed), opens the browser unless `--no-open`; a running server for the project → print its address, open it, return 0; remove `--serve`, `--open`, `--light`, `--out` (usage error naming the replacement); `--host`, `--port`, `--token`, `--no-token`, `--no-open` only with serving. Update `serve.serve` for `open_browser` default true, except when the environment sets `DEVLOOPS_NO_BROWSER=1` (no browser is opened, and the address is still printed). Set `DEVLOOPS_NO_BROWSER=1` in the test environment built by `loops/shared/tests/helpers.py` (and in `os.environ` for tests that call `serve.serve` directly), so the suite never opens a browser; test that the variable suppresses `webbrowser.open` (patched) and that without it the browser is opened.
- [X] T027 [US1] Add `--daemon` and `--stop` (research R-11): `serve.start_daemon(project, argv, env)` runs `[sys.executable, "-m", "devloops.cli", "dashboard", *argv, "--no-open"]` with `start_new_session=True`, an environment whose `PYTHONPATH` starts with the folder holding the `devloops` package (`os.path.dirname(os.path.dirname(devloops.__file__))`, so a source checkout run through `bin/devloops` and an installed package both import it), stdin `/dev/null`, stdout/stderr appended to `serve-<project hash>.log` beside the record; waits up to 10 s for the record and `GET version`; prints `serving: <url>` and `log: <path>` (or `--json` `{serving, workspace, token, pid, daemon: true, log}`), opens the browser unless `--no-open`; on failure prints the log's last 20 lines, exit 1. `serve.stop(project, env)`: record on this host with a live pid → SIGTERM, wait 5 s, SIGKILL, remove the record, `stopped`; otherwise remove a stale record, `not running`; exit 0. Record gains `daemon` and `log`.
- [X] T028 [US1] Add CLI tests in `loops/shared/tests/test_dashboard_cli.py`: removed flags are usage errors; serving flags with `--stop`/`--export` are usage errors; a second `devloops dashboard` with a server running prints its address and returns; `--daemon` starts a server that answers and records `daemon: true` and its log, a second `--daemon` reuses it, `--stop` stops it (`stopped`) and then says `not running`; a `--daemon` child that fails (port taken with `--port`) → exit 1 with the log's lines; the daemon starts from this source checkout (the child imports `devloops` through the `PYTHONPATH` it is given).

**Checkpoint**: US1 independently testable — the served dashboard is the new app with every view
of today, fast and live, with tokens on loop cards and the loop view.

---

## Phase 4: User Story 2 - See what is running and what it costs (Priority: P1)

**Goal**: the now panel on every view; tokens and cost with the full breakdown at milestone,
trial, step, and call level.

**Independent Test**: run a fake loop and open the dashboard during a call: the now panel shows the
call and its tools as they happen; after the run, compare each level's tokens and cost with the
sums of the recorded calls.

### Tests for User Story 2

- [X] T029 [P] [US2] Add `loops/shared/tests/test_live_call.py`: during a fake call with tool uses (fake_claude `tool_uses`), `<loop>/state/live.json` holds `{loop, step, milestone_id, trial, model, session_id, started_at, pid, tools: [{at, name, summary}]}` (observe by patching `LiveCall.write` to record each written document); the file is gone after the call, also after a failed call; at most the last 200 tools are kept; `dashboard.now(ws)` returns `{running: true, call, elapsed_seconds}` only while the loop's lock is held by a live process, and `{running: false, status, next_action}` for a stale file (no lock) or no file.

### Implementation for User Story 2

- [X] T030 [US2] Add `LiveCall` to `loops/shared/devloops/progress.py` (data-model Live call): `start(loop_dir, loop, step, milestone_id, trial, model, session_id)` writes `state/live.json` atomically (temp file + `os.replace`); `tool(name, input, target_dir)` appends `{at, name, summary: tool_summary(...)}`, keeps the last 200, and rewrites; `end()` removes the file. Every write is best effort (an `OSError` never changes a run). In `claude.py` `ClaudeRunner`, create one per call (start before the process, `tool` from `_on_stream_line` for each `tool_use` block, `end` in a `finally`), independent of `self.progress`.
- [X] T031 [US2] Add `dashboard.now(ws)` (data-model Now: the running loop's `live.json` when `running(ws, loop)`, with `elapsed_seconds`; otherwise the run's overall status, `next_action`, and `waiting_for` — `approval`, `questions`, or `retry` — from the run and loop states) and the route `api/now`.
- [X] T032 [P] [US2] Create `assets/app/now.js`: the panel above every view — running: loop, milestone, trial, step, model, elapsed time (ticking each second), and the tools so far (newest last, the last 20 shown with "show all"); idle: status pill and the next action or what it waits for. Reloads on `'changed'`; ticks locally between polls.
- [X] T033 [US2] Show the full totals: a `DL.fmt` helper `totalsCell(totals)` (tokens total with a tooltip listing input, output, cache write, cache read; "partial" marker); use it in `views/loop.js` (milestone rows, planning row, by-step table; the KPI block shows cache-hit rate and cost per milestone achieved), and in `views/calls.js` rows. Extend `assets/app/tests/format.test.js`.

**Checkpoint**: US1 and US2 work independently.

---

## Phase 5: User Story 3 - Find out why a trial failed (Priority: P1)

**Goal**: a trial view reached from the timeline, with steps, calls, validation, evidence, files
changed, and a "why it failed" section.

**Independent Test**: on a workspace with a failed backend trial and a failed frontend trial, open
each from the timeline: every failing item is shown with its evidence, and each step's calls open
their conversations.

### Tests for User Story 3

- [X] T034 [P] [US3] In `loops/shared/tests/test_dashboard_data.py`, test `dashboard.trial(...)`: a backend trial with a failing check lists `{kind: "check", check_id, command, status, failures, evidence}`; a frontend trial (build `validation.json` with `helpers.network_log` and the playwright validator, as `test_validator_playwright`) lists failing criteria with steps, observed, and evidence images, the contract `problem`/`unmatched_operations` with `network_requests`, and unit tests with `exit_code` and the log file ref; a boundary violation; a voided trial and an interrupted one give `{kind: "voided"|"interrupted", message}` and no validation; steps in run order with their calls and totals; `files_changed` from the trial's conversations; every reason in validation.json appears (SC-005); 404 for an unknown key.

### Implementation for User Story 3

- [X] T035 [US3] Add `dashboard.trial(ws, loop, milestone, key)` (data-model Trial; key `n` or `n.k` for an earlier voided attempt sharing the number, as `collect_loop` tells them apart today), with `why` ordered checks, criteria, contract, unit tests, boundary, voided/interrupted; evidence as file refs from `artifacts.file_index`; `files_changed` merged from `artifacts.parse_conversation` of each of the trial's calls (cache the parsed result per conversation path, size, and mtime); register `api/loops/<loop>/milestones/<id>/trials/<key>`.
- [X] T036 [P] [US3] Create `assets/app/views/trial.js`: header (milestone, trial, kind, outcome pill, duration, totals); "Why it failed" first when not passed (each reason as a card with its evidence: screenshots as thumbnails opening the viewer, logs and bodies opening the viewer, network requests as a table with errors marked); steps with their calls (each opens `#/call/…`); the full validation result (criteria and checks tables); evidence files; files changed (path → step → call, jumping to `#/call/<loop>/<seq>?at=<block>`).
- [X] T037 [US3] Link trials from `views/loop.js` milestone rows, `charts.timeline`, and Needs-attention items (failing criteria → the trial).

**Checkpoint**: US1–US3 work independently.

---

## Phase 6: User Story 4 - Read the plan and its progress (Priority: P2)

**Goal**: a plan view per loop.

**Independent Test**: open the plan view of a workspace with an approved plan and some achieved
milestones; every milestone, criterion, task, and dependency is shown with the right status.

- [ ] T038 [P] [US4] In `loops/shared/tests/test_dashboard_data.py`, test `dashboard.plan(...)`: milestones in plan order with goal, status, trials used, dependencies, tasks (status, requirement refs), criteria with `state` passing/failing/unchecked from the latest counted trial and a `trial_route` when failing; open questions with answers; assumptions; awaiting approval → `approval.status` and the command (`devloops approve` / `devloops replan`, with the workspace flag when not the default).
- [ ] T039 [US4] Add `dashboard.plan(ws, loop)` (data-model Plan) and the route `api/loops/<loop>/plan`.
- [ ] T040 [P] [US4] Create `assets/app/views/plan.js`: approval callout when waiting; per milestone a card with status, goal, dependencies (linking to those milestones), criteria list with state icons (failing → trial link), tasks list with status and requirement refs; then open questions and assumptions; link from `views/loop.js` and the navigation.

---

## Phase 7: User Story 5 - Read a conversation quickly (Priority: P2)

**Goal**: conversations rendered in the browser with folded tool calls, error navigation, and
files changed.

**Independent Test**: open a recorded conversation with errors and file edits; tool calls are
folded, errors are counted and stepped through, and each changed file jumps to its tool call.

- [ ] T041 [P] [US5] In `loops/shared/tests/test_dashboard_data.py`, test `dashboard.call(ws, loop, seq)`: header fields, prompt and settings file refs, prompt sources, records redacted (`SECRET` absent, including a secret escaped by JSON), `errors` and `files_changed` from T006, a copied conversation, one read from history, and an unavailable one with its reason; 404 for an unknown call.
- [ ] T042 [US5] Add `dashboard.call(ws, loop, seq)` (data-model Call, using `artifacts.read_conversation` and `parse_conversation`) and the route `api/calls/<loop>/<seq>`.
- [ ] T043 [P] [US5] Create `assets/app/views/conversation.js` with the rendering rules of 002 `contracts/full-dashboard.md` "Conversation rendering" (user text as a block collapsed over 40 lines; assistant text as Markdown via `DL.md`; thinking collapsed; tool use as one folded line "Tool: <name> — <hint>" (command, path, or URL; `Edit`/`Write` show path and old/new text when unfolded); tool result collapsed over 12 lines unless an error, errors marked; other records under "System records"); a header with the call's facts, totals, and "N errors" with previous/next buttons (keys `[`/`]`); a "Files changed" list jumping to `?at=<block>` (unfold and scroll); prompt parts; the prompt and settings files open in the viewer. Pure helpers (`hint(block)`, `fold(records)`) tested in `assets/app/tests/conversation.test.js`.

---

## Phase 8: User Story 6 - Search everything (Priority: P2)

**Goal**: names as you type; content search within 1 s; the same in an export.

**Independent Test**: in a workspace with 200 calls, search for a string that appears in one
conversation and one file; both results appear within 1 s and open at the match.

- [ ] T044 [P] [US6] Add search tests to `loops/shared/tests/test_serve.py` and `test_dashboard_perf.py`: `api/index` lists views, loops, milestones, trials, calls, and files with routes; `api/search` finds a file line, a decoded conversation string, and an event, redacted, at most 40, files then calls then events; a changed file is re-read and an unchanged one is not (patch the reader); a 2-character query returns nothing; on the 200-call workspace a cold search answers within 1 s and a warm one within 0.2 s (SC-006).
- [ ] T045 [US6] Add `dashboard.index(ws)` (data-model Index) and a `SearchIndex` in `serve.py` (research R-10): per workspace, `{item key: (size, mtime_ns, text)}` for listed text files (viewer text, ≤ 20 MB), conversations (decoded, redacted strings joined by newlines, as `_conversation_hit` reads them), and events (one line per event); refreshed per search by stat, capped at 256 MB (items beyond the cap read per search); matching shared with the export through one function `search_corpus(items, query, limit)` returning `SearchHit`s with `route`. Routes `api/index` and `api/search`.
- [ ] T046 [P] [US6] Create `assets/app/palette.js` (Ctrl+K or `/`): names from `api/index` matched as the developer types (pure `DL.search.names(items, query)`), content from `api/search` after a 250 ms pause from three characters (served) or `DL.search.content(corpus, query)` over `d:search-corpus` (embedded), results opening at their route and line; the JS content matcher returns the same hits as `search_corpus` for the same corpus (`assets/app/tests/search.test.js` with a fixture shared with a Python test that writes the expected hits).

---

## Phase 9: User Story 7 - Export a dashboard to keep or share (Priority: P3)

**Goal**: `devloops dashboard --export [<path>]` writes the same app with its data embedded; the
old full dashboard is removed.

**Independent Test**: export a workspace, copy the file alone elsewhere, go offline, open it:
every view, file, and conversation within the size limit opens; search works; nothing polls.

### Tests for User Story 7

- [ ] T047 [P] [US7] Add `loops/shared/tests/test_dashboard_export.py` (contracts/export.md): default path `<workspace>/exports/<YYYYMMDDTHHMMSSZ>.html`, a same-second second export gets `-2` (patch the clock), a given path is written and replaced; the root has `data-source="embedded"` and the export attributes; the CSP meta as specified; one `d:` element per API path of `api/index` (every view, trial, call, file) plus `d:search-corpus`, each valid JSON equal to the server's response for that path; `</` never appears inside a data element; no `src=`/`href=` to another file or the network (the GitHub link excepted); a configured secret appears nowhere (SC-008); a file over 5 MB is `{not_embedded: true, size, path}` and listed in the report; images are base64; conversations whole; the report (path, bytes, five largest, unavailable conversations, not embedded); a copy alone in another folder still holds everything (SC-007); exporting during a run sets `data-running="true"`.

### Implementation for User Story 7

- [ ] T048 [US7] Create `loops/shared/devloops/dashboard_export.py`: `write(ws, path=None, env=None, now=None, max_bytes=artifacts.MAX_EMBED_BYTES)` builds every API response with the same builders and redactor as the server (summary, now, loops, plans, trials, calls list and each call, files and each file's `artifacts.file_content`, events, questions, index, search corpus), writes the shell with the stylesheet and `appbundle.script()` inline, one `<script type="application/json" id="d:<path>">` per response (`</` written `<\/`), the root attributes, and the CSP meta; creates `<workspace>/exports/` and the file exclusively (port `fulldash._create`), or writes the given path; returns `{path, bytes, largest, unavailable, not_embedded}`.
- [ ] T049 [US7] In `cli.py`, make `--export [<path>]` (optional value) call `dashboard_export.write` and print the report (port `_print_full`'s format) or `--json` `{workspace, export: {…}}`; remove `_write_full_dashboard`'s use here.
- [ ] T050 [P] [US7] In the app, the embedded source: `views` read `d:` data through `DL.api.get` unchanged; `main.js` shows "Snapshot · <exported-at> · devloops <version>", "run in progress" when `data-running`, and the notice "Contains full Claude Code conversations — review before sharing"; hide Live/Offline and the workspace switcher; the viewer shows `not_embedded` files as "too large to embed (size)".
- [ ] T051 [US7] Remove the old full dashboard: `fulldash.write`, `render_full`, `Embedder`/`EmbeddedLinks`, the conversation HTML renderer, `call_sources`, and `_create` once ported; the automatic write at a final status in `cli.py` (`_full_on_stop`, `_ends_final`, `_event_marks`, `_write_full_dashboard`, `_print_full` if unused); delete `loops/shared/tests/test_full_dashboard.py` (its export checks now live in `test_dashboard_export.py`) and `test_run_command.test_one_full_dashboard_when_the_loop_it_ran_ends_final`, and the `full_on_stop` case in `test_project_runs.py`.

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: remove the summary page and every old dashboard piece (FR-008–FR-010), update
skills and docs (FR-031, FR-032), and validate.

### Removed outputs

- [ ] T052 Remove the summary page: `cli._write_dashboard`, `_light_on`, `_dashboard_path`, and every call that writes `dashboard.html`; `_emit` drops `dashboard`/`full_dashboard` and adds `dashboard_url` only when `serve.running(...)` (contracts/cli.md); `_files_hint`/`_print_dashboards`/`_start_hint` print `dashboard: <url>` or `dashboard: devloops dashboard --daemon[ --workspace <ws>]`, never starting a server (FR-009). Update tests that read `dashboard.html` or the old hint: `test_progress.py` (line ~150), `test_recovery.py` (~66), `test_suggested_answers.py` (~48), `test_run_command.py` (~370 uses `dashboard.collect`: keep if the function stays), and add to `test_dashboard_cli.py`: a completed `devloops run` writes no `dashboard.html` and nothing under `exports/` (SC-009), its output ends with the hint, and `--json` has `dashboard_url` only with a server running.
- [ ] T053 Delete the old HTML code: every HTML function in `dashboard.py` (`write`, `render_page`, `overview_view`, `run_view`, `loop_view`, `milestone_card`, `calls_view`, `questions_view`, `events_view`, `full_dashboards_view`, `sidebar`, `detail_links`, `kpi_row`, `bar_chart`, `timeline`, `table`, `pill`, `tone`, the link classes, `serve_command`/`serve_hint` if unused, `FILENAME`, `full_dashboards_dir`, `list_full_dashboards`) and its module docstring rewritten as "view data for the dashboard API"; `ui.py`; what is left of `fulldash.py` (callers import `artifacts`); `assets/dashboard.js`, `assets/dashboard.css`; `pyproject.toml` package data back to `assets/app/*` patterns only. Delete `loops/shared/tests/test_dashboard.py` and `test_dashboard_ui.py` after moving the file-kind tests to a new `test_artifacts.py`.
- [ ] T054 Remove configuration and init pieces (contracts/cli.md): `dashboard` from `loops/shared/schemas/config.schema.json` and `loops/shared/config/defaults.json`, `config.LIVE_KEYS` and its uses; `dashboards_dir` from `loops/shared/schemas/project-config.schema.json`, `project.DEFAULT_DASHBOARDS_DIR`, `Project.dashboards_dir`, `initcmd` (`track_dashboards`, the default written, the git-ignore rule), `cli` `--track-dashboards`; `engine.full_dashboards` and the `full_dashboards` status field. Copy the two schemas byte-identically to `specs/001-reusable-dev-loops/contracts/config.schema.json` and `specs/002-devloops-init/contracts/project-config.schema.json` (`test_schemas_sync`). Report a removed key with the message of contracts/cli.md (`… "dashboards_dir" was removed (the dashboard is served or exported now); delete it`). Update `tests/samples.py` (lines ~119, ~154), `test_project.py` (~128–140), `test_init.py` (~181), and add a test for the removed-key message.

### Skills and documentation

- [ ] T055 [P] Check `loops/shared/skills/devloops-run/SKILL.md` against FR-031 once T052 lands (`dashboard_url` in the result; no summary page or full-dashboard paths); run `test_skills.py`. *Revised during implementation: the dashboard, approve, replan, and retry skills were removed, and the run skill asks for the decisions; this repository no longer installs the skills.*
- [ ] T056 [P] Update `loops/README.md`: the dashboard section (serving, `--daemon`, `--stop`, export, the views including now, tokens, trial, plan, conversation, search), remove the summary page, full dashboards, `dashboard.light`, `dashboard.full_on_stop`, `dashboards_dir`, `--track-dashboards`; the workspace layout gains `exports/` and `state/live.json`.
- [ ] T057 [P] Add "Revised by specs/005-dashboard-redesign" notes in place: `specs/001-reusable-dev-loops/spec.md` (the per-command dashboard), `contracts/cli.md`, `contracts/workspace-layout.md`; `specs/002-devloops-init/spec.md` (FR-035 to FR-042d, Key Entities, SC-009/SC-010), `contracts/cli.md`, `contracts/skills.md`, `contracts/project-layout.md`; replace the body of `specs/002-devloops-init/contracts/full-dashboard.md` with a pointer to `specs/005-dashboard-redesign/contracts/export.md` and `api.md`, keeping its "Conversation rendering" table (still the rules `conversation.js` follows).

### Validation

- [ ] T058 Run the full suite (`VISUAL=true EDITOR=true timeout 900 python3 -m unittest discover -s loops/shared/tests`) with `node` installed; fix every failure.
- [ ] T059 Walk through `specs/005-dashboard-redesign/quickstart.md` on the quickflow project (after deleting `"dashboards_dir"` from its `.devloops/devloops.json`) and record the timings for SC-001–SC-003 and SC-006 and the export checks (SC-007, SC-008) in `specs/005-dashboard-redesign/validation-results.md`.

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: none.
- **Foundational (Phase 2)**: after Setup; blocks every story. T004 → T005 → T009 → T010; T006 and
  T007 → T008 after T004; T011–T017 in parallel after T001–T002; T018 after T012–T014.
- **US1 (Phase 3)**: after Phase 2. The MVP.
- **US2–US6 (Phases 4–8)**: after US1 (they add views and builders to the app US1 delivers); they
  are independent of each other except that US3's files-changed and US5 share T006 (Foundational),
  and US6's index lists the routes the other stories add (do US6 after the views it should find).
- **US7 (Phase 9)**: after the views it embeds (US1–US6); T051 last in the phase.
- **Polish (Phase 10)**: T052–T054 after US7; T055–T057 in parallel after T052–T054; T058, T059 last.

### Within each story

Tests first (they fail), then builders (`dashboard.py`), then routes (`serve.py`), then views
(`assets/app/views/`), then links from other views.

### Parallel opportunities

- Phase 2: T011, T012, T013, T014, T015, T016, T017 (different files).
- US1: T019 and T020; T022, T023, T024, T025 (one view file each) after T021.
- US2: T029 with T032.
- US3–US6: each story's test task and view task in parallel with the other stories' (different
  files), once US1 is done; builders in `dashboard.py` are sequential (same file).
- Phase 10: T055, T056, T057.

### Parallel example: User Story 1

```text
After T021 (builders):
  T022 views/overview.js
  T023 views/run.js + views/loop.js
  T024 views/calls.js + views/questions.js + views/events.js
  T025 views/files.js
```

## Implementation Strategy

### MVP first (User Story 1, with both reported bugs)

1. Phase 1 and Phase 2 (includes the Markdown fix, bug 2).
2. Phase 3: every existing view in the new app, with tokens on loop cards and the loop view (bug 1),
   and `--daemon`/`--stop`.
3. **Stop and validate**: quickstart section 2 on quickflow — refresh time, per-view requests,
   live updates.

### Incremental delivery

US2 (now panel, full totals) → US3 (trial and why) → US4 (plan) → US5 (conversations) → US6
(search) → US7 (export, old full dashboard removed) → Phase 10 (summary page and old code removed,
skills, docs, validation). Each phase ends with a passing suite (see "Keeping the suite green").

## Notes

- [P] tasks touch different files and have no dependency on an incomplete task.
- Commit after each phase, on `main`, with Conventional Commits; the removal phase is breaking
  (`feat(devloops)!:` with a `BREAKING CHANGE:` footer naming the removed options, keys, and files).
- No `Co-Authored-By` trailer.
