# Quickstart: Validating the Reusable Development Loops

This guide shows how to prove the loop infrastructure works. It does **not** build the reference
application; that is the later consumer phase. Command and file formats are defined in
[contracts/](./contracts/), and behavior in [plan.md](./plan.md).

## Prerequisites

- Claude Code (`claude`) is logged in. `claude -p "ok" --output-format json` returns a JSON result.
- `python3` ≥ 3.10, `curl`, and `git` are installed.
- `node`/`npx` is installed, for the Playwright MCP server used by `frontend-dev`.
- Playwright browsers are installed: `npx playwright install chromium`.

## 1. Offline infrastructure tests (no model, no network)

```bash
python3 -m unittest discover -s loops/shared/tests -v
```

**Expected**: all tests pass. They use the fake `claude` binary (`DEVLOOPS_CLAUDE_BIN`) and
cover the following:

| Scenario | Expected result | Spec |
|----------|-----------------|------|
| Missing requirements file, story ID absent, missing `--api-spec` for frontend-dev, target not writable | Exit 30, status `stopped-on-input-error`, reason recorded | FR-013, FR-010b, FR-035c |
| `--api-spec` is not OpenAPI 3; `curl`, `claude`, or the Playwright MCP command is missing from `PATH` | Exit 30, reason `invalid-api-spec` or `missing-tool` naming the tool | FR-013a, FR-013b |
| Valid plan | Milestone files rendered, `open-questions.md` written, exit 10 `awaiting-approval` | FR-014, FR-053 |
| Invalid plan (cycle, missing refs, a task outside the story in story mode) | Counted as a failed planning trial | R-5, FR-010a |
| A milestone that always fails validation, with `max_trials=3` | Exactly 3 trials, then exit 20 `stopped-on-failure`; no later milestone starts | FR-005, D-1, SC-004 |
| A kill in the middle of a trial, then `run` again | The trial is marked failed with reason `interrupted` and counts; achieved tasks are not re-run | FR-030, FR-030a, SC-003 |
| Fake Claude returns `api_error_status: 429`, then succeeds on the next `run` | First run: exit 50, trial `void`. Second run: the same trial number, and the trial count is unchanged | FR-067 |
| Fake Claude returns `needs_input` | The milestone fails immediately (exit 20, `needs-input`) with trials left over. `retry --milestone` after answering resumes it | FR-055a, FR-063 |
| `run` again on `stopped-on-failure` without `retry` | No calls, no changes | FR-063 |
| A second `run` while the first holds the lock | Exit 40, names the active run | FR-065 |
| A configured secret appears in a prompt and a curl response | Only `***` appears in `state/` and `evidence/` | FR-070 |
| Approved answers edited after approval | Exit 30, `input-changed` (input `answers`) | FR-051a |
| A milestone result missing one criterion, or a Playwright criterion with no evidence | Validation fails | FR-068, FR-023 |
| `run` on a `completed` workspace | No calls made, no files changed, exit 0 | FR-029 |
| Requirements file edited after planning | Exit 30, reason `input-changed`, state unchanged | D-8, SC-010 |
| Fake Claude writes outside the target (Edit, and Bash) | The Edit is blocked by the hook; the Bash write is caught by the audit; the trial fails with `boundary-violation` | FR-035b, SC-009 |
| The model claims a pass but curl gets a wrong status | Validation fails; tasks are not marked achieved | FR-027, SC-002 |
| Orchestrator with backend `awaiting-approval` | `frontend-dev` is never started | FR-042, FR-056 |
| `git diff --stat loops/` after the full suite | Empty | FR-037, FR-050 |

## 2. End-to-end smoke test on a throwaway requirement (real Claude; SC-011, SC-008)

Use a two-line fixture, `loops/shared/tests/fixtures/smoke/requirements.md`: one story that asks
for a health endpoint and one page showing its value. It exists only to exercise the loops.

```bash
bin/devloops run backend-dev --workspace smoke \
  --requirements loops/shared/tests/fixtures/smoke/requirements.md \
  --target /tmp/devloops-smoke/backend
# → exit 10: review workspaces/smoke/backend-dev/outputs/, answer open-questions.md if any
bin/devloops approve backend-dev --workspace smoke
bin/devloops run backend-dev --workspace smoke          # → exit 0
bin/devloops status backend-dev --workspace smoke --json
```

**Expected**:
- `outputs/milestone-*.md` show every task as `[x]`.
- `outputs/openapi.json` exists.
- Each trial directory has `validation.json` with `passed: true` and the curl command lines and
  responses.
- `progress.md` shows, for each milestone, its start time, end time, tokens, cost, and session IDs.

Then the frontend:

```bash
bin/devloops run frontend-dev --workspace smoke \
  --requirements loops/shared/tests/fixtures/smoke/requirements.md \
  --api-spec workspaces/smoke/backend-dev/outputs/openapi.json \
  --target /tmp/devloops-smoke/frontend \
  --config workspaces/smoke/frontend-config.json   # backend.start_command / base_url (R-12)
bin/devloops approve frontend-dev --workspace smoke && \
bin/devloops run frontend-dev --workspace smoke
```

**Expected**:
- `outputs/ui-url.txt` holds the served UI URL.
- Each trial's `validation.json` has one result per acceptance criterion, with screenshot or
  snapshot evidence under `evidence/`.
- The `contract.unmatched_operations` list is empty.

## 3. Orchestrated run

```bash
bin/devloops orchestrate --workspace smoke-orch \
  --requirements loops/shared/tests/fixtures/smoke/requirements.md \
  --target-root /tmp/devloops-smoke-orch
# pauses (exit 10) at each loop's planning approval; approve, then re-run orchestrate
```

**Expected**: `workspaces/smoke-orch/orchestrator/state.json` shows backend-dev `completed` before
frontend-dev started, and the handoff recorded the OpenAPI fingerprint. Together with step 2, this
satisfies SC-011. Running steps 2 and 3 using only the commands in `loops/README.md` is the SC-008
walkthrough.

## 4. Reusability check (SC-006)

Run step 2 again with a second, unrelated fixture
(`loops/shared/tests/fixtures/smoke-alt/requirements.md`) in a new workspace. "Unrelated" means it
shares no entities or endpoints with the first fixture and needs a different milestone plan
(SC-006).

**Expected**: it succeeds, and `git status loops/ bin/` shows no changes.

## 5. Reference application (later consumer phase, not part of this feature)

Once the steps above pass, point the orchestrator at `quickflow/PRD.md` with its own workspace and
target. Nothing under `loops/` may change to make that run succeed (FR-037). SC-007 is measured
there; it is not part of this feature's acceptance.
