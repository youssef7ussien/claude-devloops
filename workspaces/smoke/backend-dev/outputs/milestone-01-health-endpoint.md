# M01: Health endpoint

- **Status**: achieved
- **Goal**: Serve GET /health returning {"status":"ok"} as JSON, documented in openapi.json, so a page can fetch and show the service status.
- **Depends on**: none

## Tasks

- [x] **M01-T01** Create HTTP server (achieved): Add package.json (name, "type": "commonjs", scripts start/test) and server.js with a Node http server that listens on PORT (default 8000) at host 127.0.0.1 (HOST env overrides it). Export the request handler so tests can use it. Unknown routes return 404 with JSON {"error":"not found"}. (refs: HEALTH-1)
- [x] **M01-T02** Implement GET /health (achieved): GET /health responds 200 with Content-Type application/json and body {"status":"ok"}. Also send Access-Control-Allow-Origin: * so a separately served status page can read it from the browser. Other methods on /health return 405 with an Allow: GET header. (refs: HEALTH-1)
- [x] **M01-T03** OpenAPI document (achieved): Create openapi.json (OpenAPI 3.0.3) that documents only GET /health, with a 200 response whose application/json schema is an object with a required string property status (enum ["ok"]). (refs: HEALTH-1)
- [x] **M01-T04** Unit tests (achieved): Add test/health.test.js using node:test that starts the handler on an ephemeral port and checks GET /health (200, JSON {"status":"ok"}) and an unknown path (404). (refs: HEALTH-1)

## Acceptance criteria

- **M01-AC1** GET http://127.0.0.1:8000/health responds with HTTP 200, a Content-Type header starting with application/json, and a body that parses as JSON and equals exactly {"status":"ok"}. (refs: HEALTH-1)
- **M01-AC2** The GET /health response includes the header Access-Control-Allow-Origin: *, so a browser page served from another origin can read the status. (refs: HEALTH-1)
- **M01-AC3** GET http://127.0.0.1:8000/does-not-exist responds with HTTP 404 and a JSON body containing an "error" field. (refs: HEALTH-1)
- **M01-AC4** openapi.json in the target directory is valid OpenAPI 3 JSON whose paths contain only /health with a get operation, and a 200 response schema matching {"status":"ok"}. (refs: HEALTH-1)

## Trials

| Trial | Kind | Status | Reason | Started | Ended |
|---|---|---|---|---|---|
| 1 | implement | failed | validation-failed | 2026-09-27T13:42:49.972Z | 2026-09-27T13:43:50.231Z |
| 2 | fix | failed | needs-input | 2026-09-27T13:43:51.969Z | 2026-09-27T13:44:37.148Z |
| 3 | fix | passed |  | 2026-09-27T13:47:02.145Z | 2026-09-27T13:47:31.276Z |

## Assumptions

- The 405 response for non-GET methods on /health has the JSON body {"error":"method not allowed"} and also includes Access-Control-Allow-Origin: *. (trial 1; affects: M01-T02)
- Content-Type is sent as 'application/json; charset=utf-8', which starts with application/json as M01-AC1 requires. (trial 1; affects: M01-AC1)
- The OpenAPI schema for /health sets additionalProperties: false and includes an example, so it matches exactly {"status":"ok"}. (trial 1; affects: M01-T03, M01-AC4)
- The unit tests use the global fetch, which needs Node >=18 (package.json declares it in engines). (trial 1; affects: M01-T04)
- Trial 2 failed only on the driver's contract check (needs-input OQ1), not on HTTP behavior. The OQ1 answer says the driver now accepts 404/405 checks on undocumented paths, so the fix is to leave the implementation and openapi.json as they are. (trial 3; affects: M01-AC3, M01-AC4)
