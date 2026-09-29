# Validation results: real Claude Code runs (T076)

**Date**: 2026-09-27 · **Claude Code**: 2.1.283 · **Playwright MCP**: 0.0.82 (system Chromium)
**Scope**: quickstart §2–4, using only the commands in `loops/README.md` (SC-008).

## Outcome

| Step | Workspace | Result | Claude calls | Cost (USD) |
|------|-----------|--------|--------------|------------|
| §2 backend-dev, `smoke` | `workspaces/smoke/backend-dev` | completed (M01 on trial 3, after a retry) | 5 | |
| §2 frontend-dev, `smoke` | `workspaces/smoke/frontend-dev` | completed (M01 on trial 1) | 3 | |
| | `smoke` total | | 8 | 1.99 |
| §3 orchestrate, `smoke` fixture | `workspaces/smoke-orch` | completed; paused (exit 10) at each approval | 6 | 1.12 |
| §4 backend-dev + frontend-dev, `smoke-alt` | `workspaces/smoke-alt` | completed | 6 (+1 interrupted, unrecorded) | 1.50 |

The counts and costs come from `bin/devloops export-sessions`. The target directories were
throwaway directories in the session scratchpad, so the `targets` recorded in each
`workspace.json` point at paths that no longer exist.

**SC-011** (both loops end to end, directly and orchestrated) and **SC-006** (a second, unrelated
application: a counter, not a status endpoint, with a different plan, port, and criteria) are met.
After fixing the defects below, `git status loops/ bin/` shows only those fixes; the runs
themselves wrote nothing there, as the per-call write audit also confirmed.

### What was checked

- **§2 backend.** Every task in `outputs/milestone-01-health-endpoint.md` is `[x]`, and
  `outputs/openapi.json` documents only `GET /health`. The passing trial's `validation.json` has
  `passed: true`, the exact `curl` command lines, and the 200 and 404 responses. `progress.md`
  lists start, end, tokens, cost, and session IDs for planning and M01.
- **§2 frontend.** `outputs/ui-url.txt` is `http://127.0.0.1:5173`. The screenshots in
  `evidence/` are real ("Service status / Status: ok"). The page's live call
  `GET http://127.0.0.1:8000/health` matched the contract, and `unmatched_operations` is empty.
- **§3 orchestrate.** `orchestrator/state.json` is `completed`. The handoff records
  `backend-dev/outputs/openapi.json` with a sha256 that matches the file, plus the backend runtime
  with `cwd` resolved to the backend target. The frontend never started before the backend
  completed. The step timestamps in this workspace show the defect fixed in item 3 below.
- **§4 smoke-alt.** The backend counter API (5 criteria) and the frontend page (5 criteria, 7
  screenshots) passed. The page's `GET /counter` and `POST /counter/increment` both matched the
  contract. The planner raised one open question (should the backend serve the page?), which was
  answered at approval.
- **Recovery, not planned but exercised.** The frontend run was killed during trial 1. The next
  `run` stopped with exit 40 and a "stale lock" message. `run --force-unlock` recorded
  `lock-cleared`, marked trial 1 `interrupted` (counted), and passed on the fix trial, exactly as
  the README's recovery table says. The killed call's invocation record was never written, so
  its cost is missing from the export.
- `status --json` reports `large_evidence: []` for these workspaces.

## Defects found and fixed

1. **Claude Code rejected every structured-output schema** (blocking). `--json-schema` received
   our schema files verbatim, and Claude Code 2.1.x cannot resolve their draft 2020-12 `$schema`
   URI: `--json-schema is not a valid JSON Schema: no schema with key or ref
   "https://json-schema.org/draft/2020-12/schema"`. Every call failed, so the first `smoke`
   workspace used all 3 planning trials and stopped for good. It was deleted and recreated.
   - **Fix**: `claude.py` `cli_schema()` drops `$schema` and `$id` from what it sends, and the
     driver still validates against the full schema.
   - **Tests**: the fake `claude` now rejects a `$schema` the way the real one does, so the offline
     suite catches a regression; `test_claude` asserts the markers are not sent.
2. **A check that an endpoint does not exist could never pass** (blocking). The planner added a
   criterion "unknown routes return 404", so the frozen checks included `GET /does-not-exist → 404`.
   The contract rule (research R-8) required every checked `(method, path)` to be documented. The
   model raised the conflict as `needs-input`, which was the correct behavior, but the checks are
   frozen, so no answer could fix it.
   - **Fix** (decision by the developer): a check that expects 404 or 405 on an undocumented
     `(method, path)` now agrees with the contract and never counts as covering an operation.
     `curl.py`, the author-checks prompt, and research R-8 are updated.
   - **Tests**: `test_validator_curl` covers a live 404 check, an undocumented path that is
     expected to succeed (still a failure), and 405.
   - **Run**: `smoke` was resumed with the README's `retry` after the answer, and passed.
3. **Orchestrator step times contradicted the order rule** (cosmetic). Each `orchestrate` call
   re-ran the completed backend, which did nothing, but overwrote its step's `ended_at`. So the
   backend appeared to end after the frontend started.
   - **Fix**: a completed step is left untouched.
   - **Tests**: `test_orchestrator` asserts that the backend's `ended_at` is not later than the
     frontend's `started_at`.

## README gaps found and fixed

1. **Browser prerequisite.** `@playwright/mcp` uses the Google Chrome channel by default, so the
   README's `npx playwright install chromium` was not enough. The README now says to install
   Chrome (`npx playwright install chrome`) or to set `playwright.mcp_command` with
   `--executable-path`, and gives an example. These runs used `/usr/bin/chromium`.
2. **The quick start's frontend step had no backend.** Without a `backend` block in the config,
   the frontend is validated with no backend, and every criterion that needs one fails. The quick
   start now passes `--config frontend-config.json` and shows the block to copy from the backend's
   `plan-summary.md` (`orchestrate` fills it in automatically).

## Observations, not changed

- Both stacks were proposed by the planner (Node's built-in `http`, no dependencies), which the
  empty targets allowed. Nothing in `loops/` steered that choice.
- Ports come from the plan (8000, 3000, 5173, 8080). Two workspaces planned in parallel could
  collide. The runs here were sequential.
- Known gaps recorded earlier and still open: a run stopped by `max_invocations_per_run` cannot
  be resumed, and `runtime.install_command` is not run by the driver (see `loops/README.md`).
