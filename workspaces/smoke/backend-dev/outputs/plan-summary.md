# Plan summary

## Stack

- **Summary**: Node.js (>=18) using only the built-in http module, no third-party dependencies. The target directory is empty and neither the requirements nor the configuration name a stack, so this is the simplest stack for a one-endpoint service: nothing to install and it starts instantly. Unit tests use the built-in node:test runner.
- **Source**: proposed
- **Conflicts**: none

## Runtime

- **install_command**: `true`
- **start_command**: `node server.js`
- **cwd**: `.`
- **base_url**: `http://127.0.0.1:8000`
- **ready_url**: `http://127.0.0.1:8000/health`
- **unit_test_command**: `node --test`
- **openapi_path**: `openapi.json`

## Milestones

- **M01** Health endpoint (depends on: none; 4 task(s), 4 criteria)

## Requirements covered

- **HEALTH-1** GET /health returns {"status":"ok"}, and a page shows that status (page is the frontend's part; the backend provides the endpoint).

## Planning assumptions

- **A1** The "page shows that status" part of HEALTH-1 is built by a separate frontend step (the target is a backend/ directory). The backend only provides GET /health, and allows cross-origin reads (CORS *) so that page can call it. (source: requirements HEALTH-1 plus the target_dir layout (smoke/backend))
- **A2** The server listens on 127.0.0.1:8000 by default; PORT and HOST environment variables can override this. (source: proposed; no port in the requirements or configuration)
- **A3** The response body must equal {"status":"ok"} exactly, with no extra fields. (source: requirements HEALTH-1)
- **A4** Node.js 18 or newer is available on the machine running the driver. There are no npm dependencies, so the install step is a no-op. (source: proposed stack)
- **A5** Returning 404 JSON for unknown routes and 405 for other methods on /health is standard error handling. It does not add any new feature. (source: proposed)

Open questions: 0 (see open-questions.md)
