# Final report: frontend-dev

- **Workspace**: smoke-orch
- **Outcome**: completed
- **UI URL**: http://127.0.0.1:5173

## Milestones

| Milestone | Title | Status | Trials used |
|---|---|---|---|
| M01 | Service status page | achieved | 1 of 3 |

## Validation summary

| Milestone | Validation | Criteria passed | Contract | Unit tests |
|---|---|---|---|---|
| M01 | passed | 4 of 4 | passed | disabled |

## Assumptions for review

- **A1** (planning) The target directory is empty, so a new dependency-free Node static server + vanilla JS page is an acceptable proposed stack. (source: Empty target_dir; no stack named in requirements or configuration)
- **A2** (planning) The page calls the backend directly (cross-origin) at the configured backend_base_url; this works because the backend sets Access-Control-Allow-Origin: *. (source: Backend app.js sendJson headers; configuration.backend.base_url)
- **A3** (planning) The frontend serves on 127.0.0.1:5173 (overridable via PORT) to avoid clashing with the backend on port 8000. (source: Proposed; configuration.backend.base_url uses port 8000)
- **A4** (planning) Showing 'unavailable' plus an error message when the backend cannot be reached is a reasonable UI detail within HEALTH-1 and does not add a new requirement. (source: Interpretation of HEALTH-1 'a page shows that status')
- **A5** (planning) The displayed status text is the raw status value from the response ('ok'), rendered in a single element on the page. (source: HEALTH-1 and openapi.json getHealth response schema)
- (M01, trial 1) The display mapping lives in public/status.js (exported as window.StatusView in the browser and via module.exports in Node). The browser and the unit tests therefore run the same pure function. (affects: M01-T02, M01-T03)
- (M01, trial 1) A 200 response whose body has no string 'status' field is treated as a failure: the page shows 'unavailable' and the message 'Unexpected response from the service.' (affects: M01-T02, M01-AC4)
- (M01, trial 1) The error message appears in a separate element (#service-error, data-testid="service-error", role=alert), which stays hidden until an error happens. (affects: M01-AC4)
- (M01, trial 1) The server answers requests other than GET/HEAD with 405. (affects: M01-T01)
