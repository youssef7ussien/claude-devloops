# Research: Dashboard Redesign

Each decision states what was chosen, why, and what else was considered. Tags as in the plan:
**[ER]** explicit requirement, **[RD]** repository-derived, **[RC]** recommendation.

## Baseline (measured 2026-10-09)

On the largest real workspace (quickflow `main`: 85 calls, 2,322 files, 46 MB) with today's
`serve.py` [RD]:

| Step | Time |
|------|------|
| Workspace version (walk + stat of every file) | 0.08 s |
| `dashboard.collect` | 0.22 s |
| Rendering the whole page (`fulldash.render_full`, lazy embedder) | 0.79 s |
| Page size | 2.9 MB of HTML |

The browser then parses 2.9 MB and `dashboard.js` walks the whole document (views, explorer,
calls) before anything is usable: that is the several seconds the developer sees. Every change in
the workspace repeats the render and, in the page, a parse of the whole page to replace the views
whose hash changed.

## R-1 One app, served and exported, with no build step

**Decision**: The dashboard is a static app shipped in `devloops/assets/app/`: an HTML shell, a
stylesheet, and plain JavaScript files (no framework, no modules, no transpiling). Each script
adds itself to one global namespace (`DL`), and the files are joined in a fixed order (listed in
`assets/app/scripts.txt`) into one script by Python, at startup for the server and at export time
for the export [ER: Clarifications, FR-028; RC].

**Rationale**:
- No Node, npm, or bundler at install or run time; the package stays standard-library only
  (`pyproject.toml`: `dependencies = []`).
- One code path for both outputs: the served page loads the joined script from the server; the
  export inlines the same text.
- Plain scripts joined in order work from `file://`, where ES module imports of other files are
  blocked by browsers; an inline `<script type="module">` cannot import siblings either.
- One file per view and per concern keeps views independent (FR-029).
- This is how lean-ctx ships its dashboard: plain JS components and libraries in a `static/` folder,
  each embedded into the binary, with no framework and no build [external: github.com/yvgude/lean-ctx,
  `rust/src/dashboard/static/`].

**Alternatives**:
- *React/Vue/Svelte with Vite*: a build step and a Node toolchain in a tool that has neither; most
  of the value (components, routing) is small here. Rejected by the developer.
- *ES modules served separately*: clean in the served case, but the export would need a different
  loader. Rejected for two code paths.
- *Keep server-rendered HTML, render only the open view*: fixes speed, but every view stays split
  between Python HTML strings and JS fix-ups. Rejected.

## R-2 The data API: one GET per view, cached by workspace version

**Decision**: The server answers JSON under `/w/<ws>/api/…` (contracts/api.md). Each route maps to
one function in `dashboard.py` that returns plain data (no HTML) from the workspace's records,
redacted with the workspace's redactor. Results are cached per workspace, route, and workspace
version; a new version empties that workspace's cache [ER: FR-002, FR-007; RC].

**Rationale**:
- The overview needs `collect`-level totals, not every call's prompt sources or every file's kind:
  splitting by view cuts the first response from 2.9 MB of HTML to tens of KB of JSON.
- The version digest (R-3) already exists and costs 0.08 s; it is the cache key.
- Redaction stays on the server, so no unredacted value ever reaches the browser (FR-006, SC-008).

**Alternatives**: one `/api/workspace` blob (too big again); server-sent events or websockets
(a streaming server in the standard library adds threads and edge cases for little gain over a
3-second poll; lean-ctx also polls).

## R-3 Following a run: poll the version, refresh only the open view

**Decision**: Keep `GET version` every 3 s (POLL_SECONDS) while the page is visible and not paused.
When it changes, the API layer drops its cached responses and the router asks the open view, the
navigation, and the now panel to reload; other views reload when next opened. A view re-renders
into a new element and replaces the old one only after its data arrived, restoring open sections,
filters, scroll, and focus with the logic `dashboard.js` has today (`keep`/`restore`) [ER: FR-003,
FR-004; RD; RC].

**Rationale**: the open view is one request; no page-wide parse; the reader's place is kept as
today. The version walk stays at most once a second per workspace.

**Alternatives**: per-view versions (more server state for little gain: one view request is
cheap once cached).

## R-4 Routing by hash, one address per view and item

**Decision**: Hash routes, so the same addresses work served and from `file://` [ER: FR-024; RC]:

| Route | View |
|-------|------|
| `#/` | Overview |
| `#/run` | Run |
| `#/loop/<loop>` | Loop |
| `#/loop/<loop>/plan` | Plan |
| `#/loop/<loop>/m/<milestone>/t/<n>` | Trial (`n` with a `.k` suffix for a voided re-run's earlier attempt) |
| `#/calls`, `#/call/<loop>/<seq>` | Calls; one conversation (`?at=<block>` jumps to a tool call) |
| `#/files`, `#/file/<id>` | Files; one file in the viewer (`?line=<n>`) |
| `#/questions`, `#/events` | Questions, events |

A route names a view and its parameters; the router keeps a table `route → view module`, so a
new view is one entry (FR-029, FR-030).

## R-5 The export: the same app with per-route data embedded

**Decision**: `dashboard_export.py` writes one HTML file: the shell, the stylesheet and joined script
inline, and one `<script type="application/json" id="d:<route key>">` element per API response
the app can ask for (every view, every call's conversation, every file's content as text or
base64 within the 5 MB limit, the search corpus). The API layer reads from these elements instead
of fetching when the page has `data-source="embedded"`; it parses an element only when that data is
first asked for [ER: FR-011–FR-015; RC].

**Rationale**:
- Lazy parsing keeps opening a large export fast: only the overview's JSON is parsed at first.
- `<script type="application/json">` is not executed and is not HTML-parsed; `</` is written as
  `<\/` inside it so text cannot close the element.
- The same view code runs on both sources, so the export cannot drift from the served UI.

**Default location** [ER: Clarifications]: `<workspace>/exports/<YYYYMMDDTHHMMSSZ>[-n].html`, created
exclusively (as `fulldash._create` does today); `--export <path>` writes that file, replacing it.

**Alternatives**: one big JSON blob (parsed at once: slower for a 30 MB export); data in
`data-*` attributes (escaping cost and DOM size).

## R-6 Content Security Policy

**Decision**: Served page: `script-src 'self'` and `style-src 'self'` (the script and stylesheet are
served from `/assets/…`, so inline script is no longer allowed), `img-src 'self' data:`,
`connect-src 'self'`, and the other directives as today. Export: a `<meta http-equiv=
"Content-Security-Policy">` with `default-src 'none'; script-src 'unsafe-inline'; style-src
'unsafe-inline'; img-src data:` (it can only run its own inline script and load nothing) [RC].

**Rationale**: the served page becomes stricter than today (no inline script); the export keeps
today's level, which is the only one possible for a single file.

## R-7 Conversations rendered in the browser from parsed records

**Decision**: `GET api/calls/<loop>/<seq>` returns the call's header data, prompt parts, and its
transcript as a list of redacted records (each JSONL line parsed; an unparsable line as
`{"raw": "…"}`), plus derived lists: failed tool results (`errors`: block indexes) and files
changed (`files_changed`: `[{path, tool, block}]`, the last change per path, from `Edit`, `Write`,
`MultiEdit`, `NotebookEdit` tool uses, `fulldash.EDIT_TOOLS`). `conversation.js` renders the
blocks with today's rules (contracts/full-dashboard.md, Conversation rendering), folds tool calls
to one line, counts and steps through errors, and lists the files [ER: FR-021, FR-023; RC].

**Rationale**: the derived lists are computed once on the server, where the trial view also needs
them (FR-018: files changed during a trial, from the trial's calls). The Python HTML renderer
(`fulldash.render_conversation` and helpers) is removed.

## R-8 The "now" panel: a small live-call file written by the progress reporter

**Decision**: `progress.Progress` already hears `call_started`, `tool_use`, and `call_ended`
[RD]. A `LiveCall` writer, owned by `ClaudeRunner`, writes `<loop>/state/live.json`
(`{loop, step, milestone_id, trial, model, session_id, started_at, tools: [{at, name,
summary}]}`, at most the last 200 tools), replaced atomically at the call's start and after each
tool, and removed when the call ends. `GET api/now` returns it when the loop's lock is held by a
live process (`dashboard.running`), otherwise the run's status and next action [ER: FR-016; RC].

**Rationale**: parsing `run.log` text would tie the dashboard to the log's human format; a JSON
file is exact and cheap (a few hundred bytes per tool). A file left by a crash is ignored because
the lock check fails. This revises the spec's assumption that no new recording is needed; it is
a view file only, never read by the engine (Assumptions updated).

**Alternatives**: reading Claude Code's own live transcript from `~/.claude/projects` by session
ID (its location and timing are Claude Code internals); tailing `run.log` (format coupling).

## R-9 Tokens and cost at every level

**Decision**: `dashboard.py` sums `tokens` (`input`, `output`, `cache_creation`, `cache_read`) and
`cost_usd` of invocation records at call, step (per trial and per loop), trial, milestone,
planning, loop, and workspace level, with one helper. A level is `partial` when any of its calls
lacks `tokens` or `cost_usd`; the UI shows "partial". Derived: cache-hit rate =
`cache_read / (input + cache_creation + cache_read)`; cost per milestone achieved = loop cost /
achieved milestones (none achieved: not shown) [ER: FR-017, SC-004; RD].

## R-10 Search: a cached, redacted text index on the server; the same search in the export

**Decision**: Names (views, loops, milestones, trials, calls, files) come from `GET api/index`
and are matched in the browser as the developer types. Content search (`GET api/search?q=`)
scans an in-memory index of redacted texts — files (viewer text, ≤ 20 MB each), conversations
(the decoded strings, as `_conversation_hit` does today), and events — built on the first search
and kept per item by size and modification time, so later searches re-read only changed items.
The index is capped at 256 MB per workspace (larger: items beyond the cap are read per search, as
today). Results: first match per item, at most 40, files then conversations then events. The
export embeds the same corpus and the browser runs the same matching [ER: FR-022, FR-014, SC-006;
RC].

**Rationale**: today each search re-reads, re-sniffs, and re-redacts every file and conversation
(the slow part); scanning 46 MB already in memory takes tens of milliseconds.

## R-11 `--daemon` and `--stop`

**Decision** [ER: Clarifications, FR-001a; RC]:
- `--daemon`: the command starts `python -m devloops.cli dashboard --foreground …` (same options,
  plus `--no-open`) with `subprocess.Popen(start_new_session=True)`, stdin from `/dev/null`, and
  stdout/stderr appended to `serve-<project hash>.log` beside the server record
  (`$XDG_RUNTIME_DIR/devloops/`, as today). It waits up to 10 s for the record to appear and the
  URL's `version` to answer, then prints the address and the log path, opens the browser unless
  `--no-open`, and exits 0; if the child exits or the wait times out, it prints the log's last
  lines and exits 1.
- `--stop`: reads the record; if its host is this machine and the pid is alive, sends SIGTERM and
  waits up to 5 s (then SIGKILL), removes the record, and prints `stopped`. No record or a dead pid:
  removes a stale record and prints `not running`, exit 0.
- The child's environment puts the folder holding the `devloops` package first on `PYTHONPATH`,
  so a source checkout (run through `bin/devloops`) and an installed package both start it.
- `DEVLOOPS_NO_BROWSER=1` stops any browser from being opened (the address is still printed); the
  test helpers set it, so the suite never opens one.
- The foreground server keeps today's record handling; a SIGTERM stops it cleanly (it already
  handles SIGTERM).

**Alternatives**: double-fork daemonisation (more code; `start_new_session` is enough on Linux and
macOS); a pid file in the project (the project must not be written, 002 FR-042c).

## R-12 Markdown renderer: build a tree, then DOM; fix multi-line list items

**Decision**: `md.js` parses Markdown into a plain tree (`{t: 'p'|'ul'|…, c: [...]}`) and a small
`toDom` turns it into elements, so the parser can be tested without a browser. The list-item bug
(`list()` replaces a one-paragraph item's `<p>` with only that paragraph's first child, dropping
every line after the first) is fixed by unwrapping all of the paragraph's children [ER: FR-025;
RD: `assets/dashboard.js`, `list()`].

## R-13 Testing the browser code

**Decision** [RC]:
- Python `unittest` covers the API (shapes, redaction, caching, totals), the export (structure,
  embedded data, no external references, CSP), the CLI (`--daemon`, `--stop`, removed options),
  and `live.json`.
- Pure browser logic (Markdown tree, routing table, formatting, search matching, token sums) is
  written without DOM access and tested with Node's built-in runner (`node --test`), run from a
  Python test that is skipped when `node` is not installed — the pattern `test_dashboard_ui`
  already uses for `node --check`. Node is a test tool only, never a runtime need.
- A smoke test serves a fixture workspace and checks that every route the app's route table
  names answers with valid JSON, and that every script file is listed in `scripts.txt`.
- The quickstart includes a manual browser walk-through (and timings for SC-001–SC-003).

**Alternatives**: a headless browser in tests (Playwright/Chromium is not available to the suite and
would be a heavy test dependency).

## R-14 Module layout and what is removed

**Decision** [RC; RD]:

| Module | After this feature |
|--------|--------------------|
| `dashboard.py` | View data only: `collect_loop`, totals, and one builder per API route; every HTML function removed |
| `fulldash.py` → `artifacts.py` | Workspace files (listing, kinds, sniffing), the redactor, reading and parsing conversations; HTML embedding and `render_full` removed |
| `ui.py` | Removed; file kinds move to `artifacts.py`, the SVG sprite to `assets/app/` |
| `serve.py` | HTTP server, API routes, static assets, daemon/stop |
| `dashboard_export.py` | New: the export writer (`export.py` would be confused with `export-sessions`) |
| `assets/dashboard.js`, `assets/dashboard.css` | Replaced by `assets/app/` |
| `cli.py` | `dashboard` options as in contracts/cli.md; `_write_dashboard`, `_light_on`, `_full_on_stop`, the summary page path and full dashboard writes removed |

Removed configuration: `dashboard.light`, `dashboard.full_on_stop`, `dashboards_dir`; `init
--track-dashboards`; the dashboards git-ignore rule (projects created with them keep a harmless
line). devloops is in development; no migration [ER: Scope].
