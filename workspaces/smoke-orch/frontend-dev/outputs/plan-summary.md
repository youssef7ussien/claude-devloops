# Plan summary

## Stack

- **Summary**: Target directory is empty and neither the requirements nor the configuration name a frontend stack. Proposed: a dependency-free static page (index.html + vanilla JS + CSS) served by a tiny Node.js built-in `http` server (server.js), matching the backend's zero-dependency Node/CommonJS style. The server also serves /config.js exposing the backend base URL from the BACKEND_BASE_URL env var (default http://127.0.0.1:8000, the configured backend), so the address is not hard-coded in page code. The page calls the backend directly via fetch; the backend already sends Access-Control-Allow-Origin: *. Unit tests use node --test.
- **Source**: proposed
- **Conflicts**: none

## Runtime

- **install_command**: `true`
- **start_command**: `node server.js`
- **cwd**: `.`
- **base_url**: `http://127.0.0.1:5173`
- **ready_url**: `http://127.0.0.1:5173/`
- **unit_test_command**: `node --test`

## Milestones

- **M01** Service status page (depends on: none; 3 task(s), 4 criteria)

## Requirements covered

- **HEALTH-1** A GET /health endpoint returns {"status":"ok"}, and a page shows that status. (Frontend scope: the page that calls GET /health and displays the status.)

## Planning assumptions

- **A1** The target directory is empty, so a new dependency-free Node static server + vanilla JS page is an acceptable proposed stack. (source: Empty target_dir; no stack named in requirements or configuration)
- **A2** The page calls the backend directly (cross-origin) at the configured backend_base_url; this works because the backend sets Access-Control-Allow-Origin: *. (source: Backend app.js sendJson headers; configuration.backend.base_url)
- **A3** The frontend serves on 127.0.0.1:5173 (overridable via PORT) to avoid clashing with the backend on port 8000. (source: Proposed; configuration.backend.base_url uses port 8000)
- **A4** Showing 'unavailable' plus an error message when the backend cannot be reached is a reasonable UI detail within HEALTH-1 and does not add a new requirement. (source: Interpretation of HEALTH-1 'a page shows that status')
- **A5** The displayed status text is the raw status value from the response ('ok'), rendered in a single element on the page. (source: HEALTH-1 and openapi.json getHealth response schema)

Open questions: 0 (see open-questions.md)
