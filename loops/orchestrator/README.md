# Orchestrator

`devloops orchestrate` runs `backend-dev`, then `frontend-dev`, in one workspace, and hands the
backend's verified contract to the frontend (FR-040–042, FR-052, FR-056; research R-15).

The logic lives in [`../shared/devloops/orchestrator.py`](../shared/devloops/orchestrator.py). This
directory holds no code and no prompts: each loop runs through the same engine as
`devloops run <loop>`, and neither loop has orchestrator-specific code.

## Usage

```sh
bin/devloops orchestrate --workspace <ws> --requirements <prd.md> --target-root <dir>
bin/devloops orchestrate --workspace <ws> --requirements <prd.md> --story-id US-2 \
    --backend-target <dir> --frontend-target <dir>
```

- `--requirements`, `--story-id` / `--story-file`, and `--config` are passed to both loops.
- `--target-root <dir>` gives the default targets `<dir>/backend` and `<dir>/frontend`;
  `--backend-target` and `--frontend-target` override them.
- Both targets are recorded in `workspace.json` on the first `orchestrate`. Later calls need
  only `--workspace`: omitted flags fall back to the recorded requirements, story selection, and
  targets, and flags that are given must match them.

## Behavior

1. Run `backend-dev`. If it does not complete, record the step and exit with its code: 10 while it
   awaits approval, 20 or 30 when it stopped, 50 on a service error.
2. Build the handoff from the backend's own state:
   - `api_spec`: `workspaces/<ws>/backend-dev/outputs/openapi.json` and its sha256;
   - `backend_runtime`: `start_command`, `cwd` (resolved against the backend target), `base_url`,
     and `ready_url` from the backend plan's runtime, overlaid by the backend's config.
3. Run `frontend-dev` with `--api-spec` set to that document and `backend.*` set to that runtime,
   and exit with its code in the same way.
4. Record `completed`.

The frontend never starts unless the backend is `completed`. Approvals and retries are done per
loop (`devloops approve backend-dev`, `devloops retry frontend-dev ...`); running `orchestrate`
again resumes each loop from its own state, and a completed run does nothing.

## Files

`workspaces/<ws>/orchestrator/`:

- `state.json`: `{status: running | paused | completed | stopped, steps: [{loop, status, reason,
  started_at, ended_at}], handoff: {api_spec: {path, sha256}, backend_runtime: {start_command,
  cwd, base_url, ready_url}}}`. It is written before each action it records.
- `progress.md`: rendered from `state.json`, with the next action when a loop is paused or stopped.
