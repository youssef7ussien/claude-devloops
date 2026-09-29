# Plan summary

## Stack

- **Summary**: Proposed: the target directory is empty and neither the requirements nor the configuration name a frontend stack. Use a static page (HTML, CSS, vanilla ES-module JavaScript) served by a small Node.js server that uses only built-in modules (node:http, node:fs), with tests run by node:test. It needs no dependencies or build step and matches the Node backend. The server also serves /config.js, which sets the backend base URL from the BACKEND_BASE_URL environment variable at run time. The browser calls the backend directly, which works because the backend sends Access-Control-Allow-Origin: *.
- **Source**: proposed
- **Conflicts**: none

## Runtime

- **install_command**: `true`
- **start_command**: `node server.js`
- **cwd**: `.`
- **base_url**: `http://127.0.0.1:8080/`
- **ready_url**: `http://127.0.0.1:8080/`
- **unit_test_command**: `node --test`

## Milestones

- **M01** Counter page (depends on: none; 4 task(s), 5 criteria)

## Requirements covered

- **COUNTER-1** A page with a button that increments the counter (POST /counter/increment) and shows the current value (GET /counter returns {"value": n}).

## Planning assumptions

- **A1** The frontend is served on 127.0.0.1:8080; the PORT environment variable overrides the port. (source: proposed; the configuration does not specify a frontend port)
- **A2** The backend base URL is read at run time from the BACKEND_BASE_URL environment variable. If it is not set, the default is http://127.0.0.1:3000, the backend_base_url given in the context. (source: context.frontend.backend_base_url)
- **A3** The browser calls the backend cross-origin with no proxy. The backend's server.js sends Access-Control-Allow-Origin: * and answers OPTIONS preflights. (source: existing backend code (backend/server.js))
- **A4** The page loads the current value with GET /counter when it opens, and after each click shows the value returned by POST /counter/increment. It does not call GET /counter again after incrementing. (source: COUNTER-1 and the openapi.json response schemas)
- **A5** Showing an error message when a request fails, and disabling the button while a request is in flight, are basic UX. They do not add new requirements. (source: proposed)

Open questions: 0 (see open-questions.md)
