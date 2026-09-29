# M01: Health endpoint

- **Status**: achieved
- **Goal**: Add a runnable Node.js HTTP server whose GET /health endpoint returns {"status":"ok"} as JSON, and document it in openapi.json.
- **Depends on**: none

## Tasks

- [x] **M01-T01** Project scaffold (achieved): Create package.json (name, private, "type": "commonjs", scripts: start = "node server.js", test = "node --test") with no dependencies, so that `npm install` succeeds as a no-op. (refs: HEALTH-1)
- [x] **M01-T02** HTTP server with GET /health (achieved): Create app.js, which exports a request handler, and server.js, which listens on process.env.PORT (default 8000) at host 127.0.0.1. GET /health answers 200 with Content-Type application/json and the body {"status":"ok"}. Any other path answers 404 with a JSON error body {"error":"not found"}. Any other method on /health answers 405 with a JSON error body and an Allow: GET header. Every response carries Access-Control-Allow-Origin: *, so a separately served status page can fetch the endpoint. (refs: HEALTH-1)
- [x] **M01-T03** OpenAPI document (achieved): Create openapi.json (OpenAPI 3.0.3) that documents only GET /health, with a 200 response whose application/json schema is an object with a required string property `status` (enum ["ok"]) and example {"status":"ok"}. (refs: HEALTH-1)
- [x] **M01-T04** Unit tests (achieved): Add test/health.test.js using node:test. It starts the handler on an ephemeral port and checks that GET /health returns 200 with the JSON body {"status":"ok"}, and that an unknown path returns 404. (refs: HEALTH-1)

## Acceptance criteria

- **M01-AC1** GET http://127.0.0.1:8000/health responds with status 200, a Content-Type header starting with application/json, and a body that parses as JSON equal to {"status":"ok"}. (refs: HEALTH-1)
- **M01-AC2** The GET /health response includes the header Access-Control-Allow-Origin: *, so a status page served from another origin can read it. (refs: HEALTH-1)
- **M01-AC3** GET http://127.0.0.1:8000/does-not-exist responds with status 404 and a JSON error body. (refs: HEALTH-1)
- **M01-AC4** openapi.json is a valid OpenAPI 3 document whose paths contain exactly one operation, `get` on /health, with a 200 application/json response schema that has the property `status`. (refs: HEALTH-1)

## Trials

| Trial | Kind | Status | Reason | Started | Ended |
|---|---|---|---|---|---|
| 1 | implement | passed |  | 2026-09-27T13:52:44.605Z | 2026-09-27T13:53:57.323Z |

## Assumptions

- HEAD /health is answered like GET (200, same headers, no body) rather than 405, because HEAD is the standard companion of GET. The Allow header still lists only GET, as the task specifies. (trial 1; affects: M01-T02)
- Content-Type is sent as 'application/json; charset=utf-8', which satisfies 'starts with application/json'. (trial 1; affects: M01-T02, M01-AC1)
- The 'page shows that status' part of HEALTH-1 is out of scope for this backend milestone, which only adds CORS support for a separately served page. (trial 1; affects: M01-AC2)
