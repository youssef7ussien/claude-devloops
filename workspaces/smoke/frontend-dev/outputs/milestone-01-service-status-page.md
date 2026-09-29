# M01: Service status page

- **Status**: achieved
- **Goal**: Serve a page that calls GET /health on the configured backend and shows the returned status to the user, with a visible error state if the call fails.
- **Depends on**: none

## Tasks

- [x] **M01-T01** Static server with runtime config (achieved): Create package.json with no dependencies and a `test` script that runs `node --test`. Create server.js using node:http. It listens on PORT (default 5173) at host 127.0.0.1 and serves public/index.html at /, public/app.js, and a generated /config.js that sets window.APP_CONFIG = { backendBaseUrl } from the BACKEND_BASE_URL env var (default http://127.0.0.1:8000). Any other path returns 404. (refs: HEALTH-1)
- [x] **M01-T02** Status page UI (achieved): Create public/index.html with a heading 'Service status' and a status element (id="status", role="status", aria-live="polite") that first reads 'Checking…'. Load config.js and then app.js. (refs: HEALTH-1)
- [x] **M01-T03** Fetch and render health (achieved): In public/app.js, on load, send exactly one GET to `${backendBaseUrl}/health`. On a 200 response with JSON {status}, set the status element text to 'Status: ok' (the returned value) and add data-state="ok". On a network error, a non-2xx response, or invalid JSON, show 'Status: unavailable' with data-state="error". Call no other endpoint. (refs: HEALTH-1)
- [x] **M01-T04** Unit tests (achieved): Add node:test tests covering the status rendering logic: an ok response gives 'Status: ok'; a failed fetch or a non-2xx response gives 'Status: unavailable'. Put the logic in a small pure function that can be imported and tested without a browser. (refs: HEALTH-1)

## Acceptance criteria

- **M01-AC1** Opening http://127.0.0.1:5173/ in a browser shows a heading 'Service status'. (refs: HEALTH-1)
- **M01-AC2** While the backend is running, the page sends GET http://127.0.0.1:8000/health, and within a few seconds the status element (id="status") reads 'Status: ok'. (refs: HEALTH-1)
- **M01-AC3** The only backend request the page makes is GET /health, which matches the operation getHealth in the API spec. (refs: HEALTH-1)
- **M01-AC4** If the backend is unreachable, the status element reads 'Status: unavailable' instead of staying on 'Checking…' or showing a blank. (refs: HEALTH-1)

## Trials

| Trial | Kind | Status | Reason | Started | Ended |
|---|---|---|---|---|---|
| 1 | implement | passed |  | 2026-09-27T13:48:47.637Z | 2026-09-27T13:51:05.908Z |

## Assumptions

- The status text shows the status value the backend returns ('Status: ' + body.status), so with the spec's only value this reads 'Status: ok'. A 2xx body that has no non-empty string status is treated as unavailable. (trial 1; affects: M01-T03, M01-AC2)
- The health request stops after 5 seconds so that an unreachable backend that never answers still leads to 'Status: unavailable' instead of staying on 'Checking…'. (trial 1; affects: M01-T03, M01-AC4)
- The backend must allow cross-origin requests (CORS) from http://127.0.0.1:5173, because the page (port 5173) calls the backend (port 8000) directly from the browser. The frontend can't enable this itself. If the backend doesn't allow it, the browser blocks the call and the page shows 'Status: unavailable'. (trial 1; affects: M01-AC2)
- The server also answers HEAD requests, returns 405 for other methods, and sends Cache-Control: no-store. These are small hardening choices that go beyond the task text. (trial 1; affects: M01-T01)
