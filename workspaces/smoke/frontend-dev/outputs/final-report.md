# Final report: frontend-dev

- **Workspace**: smoke
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

- **A1** (planning) The target directory is empty, so the stack is proposed: vanilla HTML/JS served by a dependency-free Node server. (source: Target directory inspection (no files found))
- **A2** (planning) The browser calls the backend directly (cross-origin). The backend sends Access-Control-Allow-Origin: *, so no proxy is needed. (source: Backend server.js sets a CORS header; context gives backend_base_url http://127.0.0.1:8000)
- **A3** (planning) The frontend serves on 127.0.0.1:5173. The port can be overridden with the PORT env var. (source: Proposed; no port was specified in the requirements or configuration)
- **A4** (planning) The status is fetched once, on page load. Auto-refresh and a manual refresh button are not required. (source: HEALTH-1 only says the page 'shows that status')
- **A5** (planning) An error state ('Status: unavailable') is shown when the call fails. This is added so the page never shows a misleading status. It does not change what the page shows in the success case HEALTH-1 describes. (source: Reasonable reading of HEALTH-1)
- (M01, trial 1) The status text shows the status value the backend returns ('Status: ' + body.status), so with the spec's only value this reads 'Status: ok'. A 2xx body that has no non-empty string status is treated as unavailable. (affects: M01-T03, M01-AC2)
- (M01, trial 1) The health request stops after 5 seconds so that an unreachable backend that never answers still leads to 'Status: unavailable' instead of staying on 'Checking…'. (affects: M01-T03, M01-AC4)
- (M01, trial 1) The backend must allow cross-origin requests (CORS) from http://127.0.0.1:5173, because the page (port 5173) calls the backend (port 8000) directly from the browser. The frontend can't enable this itself. If the backend doesn't allow it, the browser blocks the call and the page shows 'Status: unavailable'. (affects: M01-AC2)
- (M01, trial 1) The server also answers HEAD requests, returns 405 for other methods, and sends Cache-Control: no-store. These are small hardening choices that go beyond the task text. (affects: M01-T01)
