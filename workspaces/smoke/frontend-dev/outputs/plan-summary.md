# Plan summary

## Stack

- **Summary**: Proposed: a static HTML page with vanilla JavaScript, served by a small dependency-free Node.js HTTP server (server.js) that uses only built-in modules. The page is a single status display, so it needs no framework or build step. Node is already used by the backend (`node server.js`). The backend base URL comes from an environment variable (BACKEND_BASE_URL, default http://127.0.0.1:8000) and reaches the page through a generated /config.js, so it is not hard-coded.
- **Source**: proposed
- **Conflicts**: none

## Runtime

- **start_command**: `node server.js`
- **cwd**: `.`
- **base_url**: `http://127.0.0.1:5173`
- **ready_url**: `http://127.0.0.1:5173/`
- **unit_test_command**: `node --test`

## Milestones

- **M01** Service status page (depends on: none; 4 task(s), 4 criteria)

## Requirements covered

- **HEALTH-1** GET /health returns {"status":"ok"}, and a page shows that status.

## Planning assumptions

- **A1** The target directory is empty, so the stack is proposed: vanilla HTML/JS served by a dependency-free Node server. (source: Target directory inspection (no files found))
- **A2** The browser calls the backend directly (cross-origin). The backend sends Access-Control-Allow-Origin: *, so no proxy is needed. (source: Backend server.js sets a CORS header; context gives backend_base_url http://127.0.0.1:8000)
- **A3** The frontend serves on 127.0.0.1:5173. The port can be overridden with the PORT env var. (source: Proposed; no port was specified in the requirements or configuration)
- **A4** The status is fetched once, on page load. Auto-refresh and a manual refresh button are not required. (source: HEALTH-1 only says the page 'shows that status')
- **A5** An error state ('Status: unavailable') is shown when the call fails. This is added so the page never shows a misleading status. It does not change what the page shows in the success case HEALTH-1 describes. (source: Reasonable reading of HEALTH-1)

Open questions: 0 (see open-questions.md)
