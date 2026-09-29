# M01: Counter API

- **Status**: achieved
- **Goal**: Serve GET /counter and POST /counter/increment backed by an in-memory counter, and document both in openapi.json.
- **Depends on**: none

## Tasks

- [x] **M01-T01** HTTP server skeleton (achieved): Create server.js using Node's built-in http module, listening on PORT env var (default 3000). Unknown routes return 404 with a JSON error body; wrong methods on known paths return 405. Add CORS headers (Access-Control-Allow-Origin: *) and answer OPTIONS preflight with 204 so a separately served page can call the API. (refs: COUNTER-1)
- [x] **M01-T02** GET /counter (achieved): Return 200 with Content-Type application/json and body {"value": n}, where n is the current in-memory counter value, starting at 0 when the server starts. (refs: COUNTER-1)
- [x] **M01-T03** POST /counter/increment (achieved): Increment the in-memory counter by one and return 200 with Content-Type application/json and body {"value": n} holding the new value. No request body is required. (refs: COUNTER-1)
- [x] **M01-T04** OpenAPI document and unit tests (achieved): Write openapi.json (OpenAPI 3.0) documenting only GET /counter and POST /counter/increment with the {value: integer} response schema. Add node:test unit tests that start the server on an ephemeral port and exercise both endpoints. (refs: COUNTER-1)

## Acceptance criteria

- **M01-AC1** On a freshly started server, GET /counter returns 200 with a JSON body exactly {"value": 0}. (refs: COUNTER-1)
- **M01-AC2** POST /counter/increment returns 200 with JSON body {"value": n+1}, where n is the value GET /counter returned immediately before. (refs: COUNTER-1)
- **M01-AC3** After three consecutive POST /counter/increment calls on a fresh server, the responses are {"value": 1}, {"value": 2}, {"value": 3} and a following GET /counter returns 200 with {"value": 3}. (refs: COUNTER-1)
- **M01-AC4** GET /counter does not change the value: two consecutive GET /counter calls return the same {"value": n}. (refs: COUNTER-1)
- **M01-AC5** GET /counter/increment returns 405 and GET /does-not-exist returns 404, and neither changes the value reported by GET /counter. (refs: COUNTER-1)

## Trials

| Trial | Kind | Status | Reason | Started | Ended |
|---|---|---|---|---|---|
| 1 | implement | passed |  | 2026-09-27T13:58:13.795Z | 2026-09-27T13:59:08.820Z |

## Assumptions

- OPTIONS preflight on an unknown path returns 404 (not 204); 204 is only for the known paths /counter and /counter/increment. (trial 1; affects: M01-T01)
- The counter is per-process in-memory state and resets to 0 on restart; no persistence is needed. (trial 1; affects: M01-T02, M01-AC1)
- Query strings are ignored when matching routes (e.g. GET /counter?x=1 is the same as GET /counter). (trial 1; affects: M01-T01)
