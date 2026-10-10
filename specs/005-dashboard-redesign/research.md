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

## R-15 Readable conversations: actions, names, summaries, result kinds (User Story 8)

Added 2026-10-10, after profiling the 85 recorded quickflow conversations and agreeing on a mockup
of frontend call #52 (validate-ui) and backend calls #3 and #4 [ER: FR-021a–FR-021f].

**What the records hold** [RD]: a tool use (`assistant` record, `tool_use` block with `id`, `name`,
`input`) and its result (a later `user` record, `tool_result` block with `tool_use_id`,
`is_error`, and `content` as a string or text and `image` parts) are separate records. Records
carry `timestamp`; thinking blocks have empty text, and the record carries `thinkingDurationMs`
when it was measured. Browser screenshots arrive as base64 `image` parts (`source.media_type`,
`source.data`). The browser tools answer in Markdown ("### Ran Playwright code" with a code block,
"### Page" with "- Page URL", "- Page Title", "- Console: N errors, M warnings", "### Snapshot",
"### Result", "### Error"). `Read` results prefix each line with its number and `→` (or a tab).
The call's final answer is its last `StructuredOutput` tool use: `{tasks, assumptions,
needs_input, files_changed}` for implement and fix steps, `{criteria}` for validation steps.

**Decision** [RC]:

1. **Where**: the server keeps sending records (data-model Call; no API change, so the export
   embeds the same data). A new pure script `assets/app/actions.js` (`DL.actions`) turns records
   into a model, `build(records) → {prompt, answer, turns, actions, stats}`, tested under Node;
   `views/conversation.js` only renders it. Each action keeps the indexes of its use and result
   records, so `?at=`, `errors`, search hits, and "Files changed" map a record to its action.
2. **Pairing**: a tool use pairs with the first later `tool_result` whose `tool_use_id` is its
   `id`. Outcome: ✕ when `is_error`, ✓ otherwise, "unfinished" with no result. Duration: result
   `timestamp` − use `timestamp`, shown only when both parse. A result with no matching use is
   shown as a row of its own ("Result").
3. **Turns**: each `assistant` text block starts a turn headed by the text (Markdown) and "+m:ss"
   since the first record's `timestamp`; the actions after it belong to it until the next text.
   An empty thinking block shows "thought for N s" from `thinkingDurationMs`, or nothing.
4. **Names and summaries** (the family sets the icon and the filter chip):

   | Tool | Name | Family | Summary |
   |------|------|--------|---------|
   | `Bash` | Shell | shell | `description`, else the command's first line; opened: `$ command` |
   | `Read` | Read | read | file name · line range when `offset`/`limit`, result line count |
   | `Edit`, `MultiEdit` | Edit | edit | file name · +added −removed (line diff of old and new) · first changed line when found |
   | `Write` | Write | edit | file name · line count |
   | `NotebookEdit` | Edit notebook | edit | file name |
   | `Grep` | Search | read | pattern · in path or glob |
   | `Glob` | Find files | read | pattern |
   | `WebFetch` | Fetch | web | URL |
   | `WebSearch` | Web search | web | query |
   | `TodoWrite` | Todos | other | N items, M done |
   | `Agent`, `Task` | Agent | other | `description` |
   | `ToolSearch` | Load tools | other | `query` |
   | `StructuredOutput` | (the result card, FR-021e; no row) | | |
   | `mcp__playwright__browser_<action>` | the action in words: Click, Type, Fill form, Navigate, Snapshot, Screenshot, Evaluate, Requests, Console, Wait, Press key, Select, Hover, Close… (any other: the action's words) | browser | the target: role and name from "Ran Playwright code" (`getByRole('button', { name: 'Save' })` → button "Save"), else `element`; plus the typed text, the URL navigated to, the fields filled (N fields), the page after it ("→ /path" when the URL changed), or for Requests the count and statuses |
   | any other `mcp__<server>__<tool>` | "<Server> · <Tool>" (underscores and dashes as spaces, first letter upper case) | other | first meaningful input |
   | any other name | the name, words split | other | first meaningful input |

   *First meaningful input*: the first non-empty string among `description`, `command`,
   `file_path`, `path`, `url`, `query`, `pattern`, `element`, `text`, `name`, then any other string
   input in key order; else "N inputs". One line, at most 160 characters. File paths are shown
   relative to the loop's target when inside it, as "Files changed" does.
5. **Result kinds** (opened row; FR-021c):
   - *image* parts: thumbnails from `data:` URLs (`image/png`, `image/jpeg`, `image/gif`,
     `image/webp` only; the page CSP allows `img-src data:`), opening in the file viewer.
   - *browser Markdown*: "Ran Playwright code" shown as one code line; the "### Page" block reduced
     to one line (URL · title · "console N errors" mark when N > 0); "### Snapshot" (a YAML
     accessibility tree, or a link to one) folded with its line count; the rest as Markdown.
   - *Markdown*: text with a Markdown heading, list, or fence → `DL.md`.
   - *read*: the `N→` prefixes moved to a line-number gutter, highlighted by the file's extension.
   - *edit*: a line diff of `old_string` and `new_string` (each edit of a `MultiEdit`), removed
     lines red, added green, unchanged lines as context; `Write` shows its content as added lines.
   - *terminal* (`Bash`): the output in a terminal block; exit code from the result's "Exit code
     N" line or `is_error`.
   - *text*: anything else; JSON pretty-printed when it parses.
   - Over 40 lines: the first 15 and the last 10, with "⋯ N more lines · Show all".
6. **Failure lines** (a hint, never the outcome): in shell output, a line is a failure line when it
   matches `✖`, `✗`, `✕`, `not ok`, `FAIL`, `FAILED`, `ERR!`, `Error:`, `Traceback`, or a
   whole-word `fail`/`failed`/`failing`/`failures` followed by something other than a zero count —
   so "ℹ fail 0", "0 failed", "failures: 0" are not. The row shows "N failure lines" and the lines
   are highlighted when it opens.
7. **Result card** (FR-021e): from the last `StructuredOutput` input. `tasks` → one line per task
   (id, ✓ when its status is implemented or done, ✕ when failed, else its status; note);
   `files_changed`, `assumptions` (with what they affect), `needs_input`/questions; `criteria` →
   one line per criterion (✓/✕ from `passed`, `observed`), headed "N of M criteria passed"; any
   other object as its fields. The first `user` text record becomes a "Prompt" row (step, line
   count) opening `call.prompt` in the viewer.
8. **Summary and filters** (FR-021f): "N actions · per family · E errors · duration" (duration from
   the call); chips "Errors only" and one per family present; a filter hides other actions and
   any turn left empty. "Files changed" adds +added −removed per path, summed over its edits.

**Rationale**: the records already hold everything (pairs, times, images, the answer), so a
browser-side model keeps one source for the served and exported dashboards and needs no new data
in the export. Rules by tool name are about Claude Code and its tools, not about an application
(constitution II). Unknown tools still get a readable row, so the view works for any
conversation. The failure-line rule is a hint because a pipe (`npm test | tail`) hides the real
exit code (backend call #3).

**Alternatives**: building actions on the server (a second representation of the same records in
every export, and the browser still needs the records for "System records"); rendering every
tool's result as Markdown (shell output and diffs lose their meaning); hiding images behind a link
(the screenshots are what the validator saw; the trial view already shows them).
