# Final report: backend-dev

- **Workspace**: smoke
- **Outcome**: completed
- **OpenAPI artifact**: outputs/openapi.json (sha256 4c992baf40acea982f7342c87718c6f3aa74e605d95b88c68adf3b3c1ed17f68)

## Milestones

| Milestone | Title | Status | Trials used |
|---|---|---|---|
| M01 | Health endpoint | achieved | 3 of 5 |

## Validation summary

| Milestone | Validation | Criteria passed | Contract | Unit tests |
|---|---|---|---|---|
| M01 | passed | 4 of 4 | passed | disabled |

## Assumptions for review

- **A1** (planning) The "page shows that status" part of HEALTH-1 is built by a separate frontend step (the target is a backend/ directory). The backend only provides GET /health, and allows cross-origin reads (CORS *) so that page can call it. (source: requirements HEALTH-1 plus the target_dir layout (smoke/backend))
- **A2** (planning) The server listens on 127.0.0.1:8000 by default; PORT and HOST environment variables can override this. (source: proposed; no port in the requirements or configuration)
- **A3** (planning) The response body must equal {"status":"ok"} exactly, with no extra fields. (source: requirements HEALTH-1)
- **A4** (planning) Node.js 18 or newer is available on the machine running the driver. There are no npm dependencies, so the install step is a no-op. (source: proposed stack)
- **A5** (planning) Returning 404 JSON for unknown routes and 405 for other methods on /health is standard error handling. It does not add any new feature. (source: proposed)
- (M01, trial 1) The 405 response for non-GET methods on /health has the JSON body {"error":"method not allowed"} and also includes Access-Control-Allow-Origin: *. (affects: M01-T02)
- (M01, trial 1) Content-Type is sent as 'application/json; charset=utf-8', which starts with application/json as M01-AC1 requires. (affects: M01-AC1)
- (M01, trial 1) The OpenAPI schema for /health sets additionalProperties: false and includes an example, so it matches exactly {"status":"ok"}. (affects: M01-T03, M01-AC4)
- (M01, trial 1) The unit tests use the global fetch, which needs Node >=18 (package.json declares it in engines). (affects: M01-T04)
- (M01, trial 3) Trial 2 failed only on the driver's contract check (needs-input OQ1), not on HTTP behavior. The OQ1 answer says the driver now accepts 404/405 checks on undocumented paths, so the fix is to leave the implementation and openapi.json as they are. (affects: M01-AC3, M01-AC4)
