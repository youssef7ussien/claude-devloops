# The run

`devloops run` runs the loops the project includes, `backend-dev` then `frontend-dev`, in one
workspace, and hands the backend's verified contract to the frontend (FR-040–042, FR-052, FR-056;
research R-15; spec 003).

> Changed by [spec 003](../../specs/003-single-run-command/spec.md): `devloops run` (no loop name)
> replaces `devloops orchestrate` and `devloops run <loop>`, a project may include the backend
> alone, and the run's record moved from `<ws>/orchestrator/` to `<ws>/run/`.

The logic lives in [`../shared/devloops/orchestrator.py`](../shared/devloops/orchestrator.py). This
directory holds no code and no prompts: each loop runs through the same engine, and neither loop
has run-specific code.

## Usage

```sh
bin/devloops run --workspace <ws> --requirements <prd.md> --target-root <dir>
bin/devloops run --workspace <ws> --requirements <prd.md> --story-id US-2 \
    --backend-target <dir> --frontend-target <dir>
```

- `--requirements` / `--speckit-feature`, `--story-id` / `--story-file`, `--config`, and
  `--max-trials` apply to every loop the command starts or resumes.
- The loops come from `select_loops`: for each loop, the target recorded in the workspace, then
  `--backend-target` / `--frontend-target`, then the project's `targets.<loop>` when it is neither
  null nor missing (placed under `--target-root <dir>` as `<dir>/backend` or `<dir>/frontend`). A
  loop with none of these is not part of the run. A flag that differs from a recorded target is a
  usage error (exit 2).
- `check_selection` stops a run that cannot go on before anything is written (exit 30): no loop
  (`no-loop`), or `frontend-dev` without `backend-dev` (`frontend-needs-backend`).
- `--review-plan` (pause after each plan) or `--accept-suggested` (the default) applies to every
  loop and is recorded in `state.json`, so a later call without it keeps it. Without a recorded
  mode, the frontend takes the backend's frozen one.
- The selected targets are recorded in `workspace.json` on the first run. Later calls need only
  `--workspace`: omitted flags fall back to the recorded requirements, story selection, and
  targets, and flags that are given must match them.

## Behavior

0. Check the tools of each selected loop that has work left, before anything is recorded or
   spent. A missing tool exits 30 (`missing-tool`, naming the loop).
1. Run `backend-dev` when the run includes it. A loop already completed is skipped. If it does not
   complete, record the step and exit with its code: 10 while it awaits approval (only when plans
   are reviewed), 20 or 30 when it stopped, 50 on a service error.
2. Build the handoff from the backend's own state, and record it even when the run has no
   frontend, so one added later starts from it:
   - `api_spec`: `workspaces/<ws>/backend-dev/outputs/openapi.json` and its sha256;
   - `backend_runtime`: `start_command`, `cwd` (resolved against the backend target), `base_url`,
     and `ready_url` from the backend plan's runtime, overlaid by the backend's config.
3. Run `frontend-dev`, when the run includes it, with that document as its API spec and
   `backend.*` set to that runtime, and exit with its code in the same way.
4. Record `completed`.

The frontend never starts unless the backend is `completed`. `approve`, `replan`, and `retry`
take no loop name: they find the loop that is waiting (`awaiting-approval` or
`stopped-on-failure`), record the decision, and continue the run from that loop
(`Orchestrator.run(action)`). Nothing is written to `state.json` until the decision is recorded,
so a refused one, or one that meets another driver's lock, leaves it as it was. With
`--no-continue`, only the decision is recorded. Running `devloops run` again also resumes each
loop from its own state, and a completed run does nothing.

## Files

`workspaces/<ws>/run/` (an `orchestrator/` folder left by an older devloops is ignored):

- `state.json`: `{status: running | paused | completed | stopped, loops: [<loop>, ...], steps:
  [{loop, status, reason, started_at, ended_at}], handoff: {api_spec: {path, sha256},
  backend_runtime: {start_command, cwd, base_url, ready_url}}, questions: ask | accept-suggested
  (when given)}`. It is written before each action it records.
- `progress.md`: rendered from `state.json`, with the next action when a loop is paused or stopped.
