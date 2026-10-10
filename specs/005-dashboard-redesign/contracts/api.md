# Contract: dashboard server and data API

Served by `devloops dashboard` (`serve.py`). Replaces the "Live dashboard" section of
specs/002-devloops-init/contracts/full-dashboard.md. Shapes are in [data-model.md](../data-model.md).

## Routes

GET and HEAD only; any other method gets 501 (FR-006, FR-030: writing routes are a later feature).

| Path | Response |
|------|----------|
| `/` | redirect to `/w/<default workspace>/` |
| `/assets/app.js`, `/assets/app.css` | the joined script and the stylesheet (`?v=<devloops version>`; `Cache-Control: max-age=31536000, immutable`) |
| `/w/<ws>/` | the app shell: `data-source="api"`, `data-poll=<seconds>`, `data-workspace` |
| `/w/<ws>/version` | `{"version": "<digest>"}` (as today) |
| `/w/<ws>/api/summary` | Workspace summary |
| `/w/<ws>/api/now` | Now |
| `/w/<ws>/api/loops/<loop>` | Loop |
| `/w/<ws>/api/loops/<loop>/milestones/<id>/trials/<key>` | Trial |
| `/w/<ws>/api/calls` | `{calls: [CallRef], by_model, loops, steps}` (`steps`: the driver's step order, FR-020i) |
| `/w/<ws>/api/calls/<loop>/<seq>` | Call |
| `/w/<ws>/api/files` | `{trees: [Tree], count}` |
| `/w/<ws>/api/files/<id>` | the file's content (as today's `file/<anchor>`) |
| `/w/<ws>/api/events` | `{events: [Event]}` |
| `/w/<ws>/api/questions` | `{questions: [Question]}` |
| `/w/<ws>/api/index` | `{items: [IndexItem]}` |
| `/w/<ws>/api/search?q=<text>` | `{results: [SearchHit]}`, at most 40 |

Unknown loop, milestone, trial, call, or file: 404 with `{"error": "<what>"}`. `<loop>` must be one
of the loops the run includes.

## Data rules

- Every JSON response is built from the workspace's records and passes through the workspace's
  redactor (`artifacts.workspace_redactor`) before it is sent (FR-006, SC-008).
- JSON responses carry `X-Devloops-Version: <workspace version>`, so the page can tell data from an
  older version apart.
- The server caches each response per workspace, path, and version; the cache of a workspace is
  dropped when its version changes (FR-007). The version is computed at most once a second per
  workspace (as today).
- File contents: text redacted (JSON indented); over 16 MB streamed a block of lines at a time;
  images with their type; other files as attachments. Only ids in the workspace's file listing
  for the current version are served, opened by their real path (as today).

## Safety (unchanged from 002 FR-042b, except the page's policy)

- Listens on `127.0.0.1` unless `--host`; on loopback, a `Host` that is not a loopback name gets
  403; beyond loopback a token is required by default (cookie, constant-time compare).
- Every response: `Cache-Control: no-store` (assets: as above), `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`.
- Page CSP: `default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:;
  connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`.
- File CSP: `default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox` (as today).
- Nothing is written to the project.

## The app's use of the API

- On load, the router opens the route in the address (default `#/`) and requests only that view's
  data, plus `summary` (navigation and status) and `now`.
- Every `data-poll` seconds while visible and not paused: `version`. On a change: drop cached
  responses, reload the open view's data, `summary`, and `now`. Other views reload when opened.
- No answer: show **Offline** and keep the data shown; retry on the next tick.
