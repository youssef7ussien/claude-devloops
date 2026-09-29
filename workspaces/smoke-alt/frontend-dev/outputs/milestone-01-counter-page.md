# M01: Counter page

- **Status**: achieved
- **Goal**: Serve one page that shows the current counter value from GET /counter and has a button that calls POST /counter/increment and shows the returned value.
- **Depends on**: none

## Tasks

- [x] **M01-T01** Static server with runtime config (achieved): Create package.json (type: module, with start and test scripts) and server.js. server.js uses node:http to serve index.html, app.js, api.js and styles.css from the target directory on PORT (default 8080) and host 127.0.0.1. It also serves /config.js, which sets window.APP_CONFIG = { backendBaseUrl } from the BACKEND_BASE_URL environment variable (default http://127.0.0.1:3000, the backend_base_url given in configuration). Unknown paths return 404. (refs: COUNTER-1)
- [x] **M01-T02** API client limited to the spec's operations (achieved): api.js exports getCounter(), which sends GET {base}/counter, and incrementCounter(), which sends POST {base}/counter/increment with no body. Each one parses the JSON response and returns its integer value. A non-2xx response or a network failure throws an error. No other endpoints are called. (refs: COUNTER-1)
- [x] **M01-T03** Counter UI (achieved): index.html has a heading 'Counter', a value display element (id="counter-value", aria-live="polite"), an 'Increment' button (id="increment-button") and an error area (id="error", role="alert"). On load, app.js calls getCounter and shows the value; until then the display shows 'Loading…'. When the button is clicked, app.js disables the button, calls incrementCounter, shows the returned value, then enables the button again. If a request fails, the error area shows a readable message and the last value stays on screen. (refs: COUNTER-1)
- [x] **M01-T04** Unit tests (achieved): Add node:test tests. They check that api.js calls the correct method and URL and parses {value}, using a stubbed global fetch, and that server.js serves index.html and a config.js that reflects BACKEND_BASE_URL. (refs: COUNTER-1)

## Acceptance criteria

- **M01-AC1** Opening the base URL shows a page with a 'Counter' heading, an 'Increment' button, and a number that equals the value GET /counter returns (for example 0 on a freshly started backend). (refs: COUNTER-1)
- **M01-AC2** Clicking 'Increment' once sends exactly one POST /counter/increment to the backend, and the number on the page goes up by one to match the value in the response. (refs: COUNTER-1)
- **M01-AC3** Clicking 'Increment' three times makes the number go up by three. Reloading the page then shows the same number, fetched again with GET /counter. (refs: COUNTER-1)
- **M01-AC4** Every network request the page makes to the backend is either GET /counter or POST /counter/increment on the configured backend base URL. No other backend endpoint is requested. (refs: COUNTER-1)
- **M01-AC5** If the backend is unreachable when the page loads or when 'Increment' is clicked, the page shows a visible error message instead of failing silently. (refs: COUNTER-1)

## Trials

| Trial | Kind | Status | Reason | Started | Ended |
|---|---|---|---|---|---|
| 1 | implement | failed | interrupted | 2026-09-27T14:00:06.367Z | 2026-09-27T14:01:56.871Z |
| 2 | fix | passed |  | 2026-09-27T14:01:57.441Z | 2026-09-27T14:05:13.028Z |

## Assumptions

- The trial 1 failure was 'interrupted' and left no validation.json or evidence, and the target directory was empty. So this fix builds the whole milestone rather than patching a specific defect. (trial 2; affects: M01-T01, M01-T02, M01-T03, M01-T04)
- If the first GET /counter fails, the value display shows '—' instead of staying on 'Loading…', and the error message appears in #error. (trial 2; affects: M01-T03)
- The server passes an empty BACKEND_BASE_URL through, and config.js then uses the default http://127.0.0.1:3000. (trial 2; affects: M01-T01)
