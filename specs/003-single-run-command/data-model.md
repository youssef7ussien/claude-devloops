# Data Model: One Command to Run Devloops

Only what changes is listed. Everything else (run.json, plan, milestones, events, the handoff's
content) is as in specs 001 and 002.

## Project configuration: `targets` (`.devloops/devloops.json`)

| Field | Type | Meaning (changed) |
|-------|------|-------------------|
| `targets.backend-dev` | string \| null \| missing | A folder: the project uses backend-dev, writing there. `null` or missing: the project does not use backend-dev. |
| `targets.frontend-dev` | string \| null \| missing | Same, for frontend-dev. |

The JSON schema (`loops/shared/schemas/project-config.schema.json`, and its copy in 002 contracts)
already allows `string | null`. Only the property descriptions change.

**Validation**:
- `init` never writes both as `null` (FR-014).
- A hand-edited file with both `null` is valid JSON. `devloops run` reports it (exit 30,
  `no-loop`), and `devloops check` reports a `missing` `loops` item (exit 30) and both loops'
  tools as unused.

## Loop selection (computed, not stored)

`{loop: absolute target}` in `LOOP_ORDER` (`backend-dev`, `frontend-dev`), computed by every
`devloops run` and decision command (research R-2):

```text
for each loop:
  workspace.targets[loop]                         # recorded here (a different flag → exit 2)
  else --<loop>-target flag                       # explicit
  else project.targets[loop] (non-null)           # the project uses it
       placed at <target-root>/<backend|frontend> when --target-root is given
  else: not included
```

**Validation** (research R-3), before any write:
- no loop selected → exit 30, `no-loop`;
- frontend-dev selected without backend-dev → exit 30, `frontend-needs-backend`.

`devloops check` uses the same rule with no flags and the project's default workspace when it
exists.

## Run (formerly "orchestrator") — `<workspace>/run/state.json`

The fields are unchanged from 001's orchestrator state; only the folder and the name change.

| Field | Type | Notes |
|-------|------|-------|
| `status` | `running` \| `paused` \| `stopped` \| `completed` | `completed` when every selected loop is completed. It returns to `running` when a newly selected loop has work left (R-5). |
| `loops` | `[loop]` | The loops the last command included, in `LOOP_ORDER` (shown in `progress.md`). Added after code review. |
| `steps[]` | `{loop, status, reason, started_at, ended_at}` | One per loop selected at least once, in `LOOP_ORDER`. A completed loop with no step yet (an older workspace) gets one with its status and no times. |
| `handoff` | `{api_spec: {path, sha256}, backend_runtime}` \| null | Written when backend-dev completes, whether or not frontend-dev is selected. |
| `questions` | `ask` \| `accept-suggested` | As today. |
| `project_root` | string | As today, so a moved project's paths can be updated (FR-013). |

`<workspace>/run/progress.md` is rendered from it (the title says "Run").

### State transitions

```text
(none) --devloops run, selection valid--> running
running --a loop pauses for approval--> paused --approve/replan--> running
running --a loop stops on failure--> stopped --retry--> running
running --a loop stops on a service error--> stopped --devloops run--> running
running --a loop stops on an input error--> stopped (final, as in 001)
running --last selected loop completes--> completed
completed --devloops run with a newly selected loop that has work--> running
```

## Workspace layout (changed part)

```text
<workspace>/
├── workspace.json
├── backend-dev/ …          # unchanged
├── frontend-dev/ …         # unchanged
├── run/                    # was orchestrator/
│   ├── state.json
│   └── progress.md
└── dashboard.html
```

An `orchestrator/` folder from an older devloops is ignored, neither read nor deleted. `devloops
run` creates `run/` and continues, skipping completed loops (spec FR-016a).

## Check result (`devloops check --json`)

| Field | Change |
|-------|--------|
| `loops` | **New**: the loops the project includes (both outside a project). |
| `items[].status` | **New value** `unused`: the item is needed only by loops the project does not include. It never makes `ready` false. |
| `items[]` `loops` | **New item**, only when the project includes no loop: status `missing`, so `ready` is false (exit 30). |
