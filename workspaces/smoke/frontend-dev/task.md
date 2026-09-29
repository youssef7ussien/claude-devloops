# Task: frontend-dev (workspace `smoke`)

Build the frontend described by the requirements below, milestone by milestone, until every
milestone's acceptance criteria pass in a real browser. See `Loop-instructions.md` in this
directory for the full rules; this file only records the current run's inputs and outputs.

## Inputs

- **Requirements**: `/data/space/workspace/claude-loops/loops/shared/tests/fixtures/smoke/requirements.md` (sha256 `de55f3ed9f5bbcb0d3af56c6bee0acfe0de6478dff3a5d9641909b0cbe015210`)
- **Mode**: `prd`; story: `none`
- **Target directory** (the only place you may write): `/tmp/claude-1000/-data-space-workspace-claude-loops/19246cf3-3402-4e12-8fb8-9e1c0e715583/scratchpad/t076/smoke/frontend`
- **API spec** (the backend contract; call only the operations it declares): `/data/space/workspace/claude-loops/workspaces/smoke/backend-dev/outputs/openapi.json`

## Effective configuration

```json
{
  "max_trials": 3,
  "max_invocations_per_run": 60,
  "invocation_timeout_seconds": 1800,
  "max_budget_usd_per_invocation": null,
  "model": null,
  "implement_tools": [
    "Read",
    "Edit",
    "Write",
    "Glob",
    "Grep",
    "Bash"
  ],
  "unit_tests": {
    "enabled": false,
    "command": null
  },
  "runtime": {
    "ready_timeout_seconds": 120
  },
  "backend": {
    "start_command": "node server.js",
    "cwd": "/tmp/claude-1000/-data-space-workspace-claude-loops/19246cf3-3402-4e12-8fb8-9e1c0e715583/scratchpad/t076/smoke/backend",
    "ready_url": "http://127.0.0.1:8000/health"
  },
  "playwright": {
    "mcp_command": [
      "npx",
      "@playwright/mcp@latest",
      "--headless",
      "--executable-path",
      "/usr/bin/chromium"
    ]
  },
  "git": {
    "commit_per_milestone": false
  },
  "secrets": {
    "env": [],
    "literals": []
  },
  "boundary": {
    "allowed_extra": []
  }
}
```

## Outputs

- `outputs/milestone-<NN>-<slug>.md`: one per milestone, with its tasks and acceptance criteria.
- `outputs/plan-summary.md`: the chosen stack and the milestone list.
- `outputs/ui-url.txt`: the URL the frontend is served at, recorded when it is first validated.
- `outputs/open-questions.md`: anything you could not resolve from the requirements.
- `progress.md` and `outputs/final-report.md`: run status and outcome, rendered by the driver.

You do not write any of these files yourself (except through the `implement`/`fix` steps' own
target-directory changes, which the driver's own rendering never touches); the driver renders them
from state after every trial.
