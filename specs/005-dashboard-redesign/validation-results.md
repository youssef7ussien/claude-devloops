# Validation results: dashboard redesign

*Recorded 2026-10-10 (T059), against the quickstart, on a copy of the quickflow project
(`quickflow/tmp`, workspace `main`: 2 loops, 20 milestones, 85 Claude calls, 2,240 listed files,
79 MB of workspace), with `"dashboards_dir"` deleted from the copy's `.devloops/devloops.json`
(the key is removed: an unchanged file now stops with `"dashboards_dir" was removed (the
dashboard is served or exported now); delete it`). Linux, Python 3.14, Chromium (headless).*

## 1. Automated tests

`VISUAL=true EDITOR=true python3 -m unittest discover -s loops/shared/tests`: 706 tests, OK
(2 skipped), 545 s. `node --test loops/shared/devloops/assets/app/tests/`: 75 pass.

## 2. Serving (SC-001–SC-003)

`devloops dashboard --daemon --port 0`, then each request timed with `curl` (first request after
the server started, so nothing was kept yet):

| Request | Time | Size |
|---|---|---|
| page (`/w/main/`) | 0.06 s | 9 KB |
| `api/summary` (overview) | 0.08 s | 47 KB |
| `api/now` | 0.002 s | 0.1 KB |
| `version` | 0.002 s | 0.03 KB |
| `api/loops/backend-dev` (loop view) | 0.27 s | 175 KB |
| `api/loops/backend-dev/milestones/M01/trials/1` (trial) | 0.01 s | 22 KB |
| `api/calls` | 0.007 s | 50 KB |
| `api/calls/backend-dev/29` (largest conversation) | 0.03 s | 569 KB |
| `api/files` | 0.02 s | 740 KB |
| `api/index` | 0.07 s | 498 KB |
| `api/summary`, again (kept for the version) | 0.002 s | 47 KB |

Every view's data arrives well within 1 s (SC-001, SC-002); a refresh of the overview asks for
`summary`, `now`, and `version` only. Following a live run (SC-003) was not repeated here: it is
covered by `test_serve` and `test_live_call`.

## 3. Search (SC-006)

`api/search?q=openapi.json` over every file, conversation, and event: 0.23 s (first search,
texts read and kept), results opening at the match.

## 4. Export (SC-007, SC-008)

`devloops dashboard --export <path>`: 5.0 s, 57.5 MB (2,240 files, 85 conversations whole, the
search corpus 4.8 MB, its file items reading their text from the files' own elements instead of a
copy, which took the file from 71 MB to 57.5 MB). The copy, alone in another folder, opened from
`file://` in headless Chromium: Overview, the loop view, a trial, Claude calls, a conversation,
Files, Questions, and Events all rendered from the embedded data, with "Snapshot · <time> ·
devloops 0.2.0", the conversations notice, and no Live button; no console errors, and nothing is
fetched (the page's CSP has no `connect-src`). quickflow configures no secrets; SC-008 is checked
by `test_dashboard_export.test_redacted_and_self_contained` (a configured secret appears nowhere).

## 5. No dashboard files from commands (SC-009)

`devloops status` ends with `dashboard: devloops dashboard --daemon` and writes nothing; a run
writes no `dashboard.html` and nothing in `exports/` (`test_dashboard_cli.
test_a_run_writes_no_dashboard_and_points_to_it`). The copy's `dashboard.html` is an old file from
before this feature; it is listed as a workspace file until deleted.
