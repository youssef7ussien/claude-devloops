# Plan summary

## Stack

- **Summary**: Proposed: Node.js (>=18) using only the built-in http module, with no third-party dependencies. The target directory is empty and neither the requirements nor the configuration name a stack. A dependency-free Node server is the simplest common option for a single JSON endpoint: nothing to install, it starts fast, and unit tests run with the built-in node:test runner.
- **Source**: proposed
- **Conflicts**: none

## Runtime

- **install_command**: `npm install`
- **start_command**: `node server.js`
- **cwd**: `.`
- **base_url**: `http://127.0.0.1:8000`
- **ready_url**: `http://127.0.0.1:8000/health`
- **unit_test_command**: `node --test`
- **openapi_path**: `openapi.json`

## Milestones

- **M01** Health endpoint (depends on: none; 4 task(s), 4 criteria)

## Requirements covered

- **HEALTH-1** GET /health returns {"status":"ok"}, and a page shows that status (the page is the frontend's part; this backend plan covers the endpoint).

## Planning assumptions

- **A1** The "page shows that status" part of HEALTH-1 is a frontend concern and will be built by a frontend step. This backend plan covers only the GET /health endpoint. It adds a permissive CORS header so that page can call the endpoint from another origin. (source: HEALTH-1; backend-dev loop role)
- **A2** The server listens on 127.0.0.1, on port 8000 by default, and the PORT environment variable can override the port. The requirements do not specify a host or port. (source: proposed)
- **A3** The stack is proposed (dependency-free Node.js >= 18) because the target directory is empty and neither the requirements nor the configuration name a stack. (source: empty target_dir; configuration.backend is empty)
- **A4** A 404 for unknown paths and a 405 for non-GET methods on /health are reasonable defaults. They do not add to the requirement or change it. (source: proposed)

Open questions: 0 (see open-questions.md)
