# M01: Service status page

- **Status**: achieved
- **Goal**: A user opening the frontend sees the backend's service status, fetched via the documented GET /health operation.
- **Depends on**: none

## Tasks

- [x] **M01-T01** Static server and runtime config (achieved): Create package.json (commonjs, scripts start/test) and server.js using Node's built-in http module, listening on 127.0.0.1:PORT (default 5173). Serve index.html at /, static app.js and styles.css, and a generated /config.js that sets window.APP_CONFIG = { backendBaseUrl } from env BACKEND_BASE_URL (default http://127.0.0.1:8000). Unknown paths return 404. The frontend server must not itself expose or proxy /health. (refs: HEALTH-1)
- [x] **M01-T02** Status page UI (achieved): Create index.html with a heading 'Service status' and a status element (e.g. data-testid="service-status") that initially reads 'Checking…'. app.js on load calls fetch(`${backendBaseUrl}/health`, { method: 'GET' }) only; on a 200 JSON response it shows the returned status value (e.g. 'ok') with an OK styling; on network error or non-2xx it shows 'unavailable' with an error message. No other backend calls. (refs: HEALTH-1)
- [x] **M01-T03** Unit tests (achieved): Add node --test tests: server serves / with the status element, /config.js contains the configured backend URL, and a pure render/format function maps {status:'ok'} to the displayed 'ok' text and failures to 'unavailable'. (refs: HEALTH-1)

## Acceptance criteria

- **M01-AC1** Opening http://127.0.0.1:5173/ in a browser shows a page with the heading 'Service status'. (refs: HEALTH-1)
- **M01-AC2** With the backend running, within a few seconds of load the status element on the page displays the text 'ok', taken from the GET /health response body's status field. (refs: HEALTH-1)
- **M01-AC3** The only backend request the page makes is GET http://127.0.0.1:8000/health (the documented getHealth operation); no undocumented endpoints are called. (refs: HEALTH-1)
- **M01-AC4** If the backend is unreachable, the status element shows 'unavailable' and an error message instead of staying on 'Checking…'. (refs: HEALTH-1)

## Trials

| Trial | Kind | Status | Reason | Started | Ended |
|---|---|---|---|---|---|
| 1 | implement | passed |  | 2026-09-27T13:54:50.471Z | 2026-09-27T13:56:40.200Z |

## Assumptions

- The display mapping lives in public/status.js (exported as window.StatusView in the browser and via module.exports in Node). The browser and the unit tests therefore run the same pure function. (trial 1; affects: M01-T02, M01-T03)
- A 200 response whose body has no string 'status' field is treated as a failure: the page shows 'unavailable' and the message 'Unexpected response from the service.' (trial 1; affects: M01-T02, M01-AC4)
- The error message appears in a separate element (#service-error, data-testid="service-error", role=alert), which stays hidden until an error happens. (trial 1; affects: M01-AC4)
- The server answers requests other than GET/HEAD with 405. (trial 1; affects: M01-T01)
