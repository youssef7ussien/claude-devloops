# Plan summary

## Stack

- **Summary**: Proposed: Node.js (>=18) using only the built-in http module, no third-party dependencies, with in-memory state. The target directory is empty and neither the requirements nor the configuration name a stack; a zero-dependency Node server is the simplest common choice for two JSON endpoints and needs no install step.
- **Source**: proposed
- **Conflicts**: none

## Runtime

- **start_command**: `node server.js`
- **cwd**: `.`
- **base_url**: `http://127.0.0.1:3000`
- **ready_url**: `http://127.0.0.1:3000/counter`
- **unit_test_command**: `node --test`
- **openapi_path**: `openapi.json`

## Milestones

- **M01** Counter API (depends on: none; 4 task(s), 5 criteria)

## Requirements covered

- **COUNTER-1** Counter: POST /counter/increment adds one and returns the new value; GET /counter returns {"value": <n>}; a page has a button that increments and shows the value.

## Planning assumptions

- **A1** POST /counter/increment returns the new value in the same shape as GET /counter: {"value": <n>}, with status 200. (source: COUNTER-1 says it 'returns the new value' without a shape; reusing the GET shape is the consistent reading.)
- **A2** The counter starts at 0 and is held in memory; it resets when the server restarts. No persistence is required. (source: COUNTER-1 names no initial value or persistence.)
- **A3** The page with the button is out of scope for this backend loop (pending OQ1); the backend enables permissive CORS so a separate frontend can call it. (source: Target directory is 'backend'; COUNTER-1 page requirement.)
- **A4** The server listens on port 3000 by default (overridable via the PORT environment variable) and binds to all interfaces. (source: Proposed; no port given in requirements or configuration.)
- **A5** The counter is a single global counter with no authentication. (source: COUNTER-1 describes one counter and mentions no users or auth.)

Open questions: 1 (see open-questions.md)
