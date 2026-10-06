# Contract: Repository and Workspace Layout

> **Changed by 002** ([specs/002-devloops-init/contracts/](../../002-devloops-init/contracts/)):
> - Workspaces live under the project's `workspaces_dir` (default `.devloops/workspaces/`; this
>   repository sets `workspaces/`), and the kit (`loops/`) can also be installed as the
>   `devloops_kit` package ([project-layout.md](../../002-devloops-init/contracts/project-layout.md)).
> - Each loop's `state/` gains `conversations/<seq>-<step>.jsonl`: the redacted copy of each call's
>   Claude Code transcript.
> - Full dashboards are written outside the workspace, to `<dashboards_dir>/<ws>/`
>   ([full-dashboard.md](../../002-devloops-init/contracts/full-dashboard.md)).
> - `workspace.json` stores targets and the requirements path relative to the project root when
>   they are inside it.

## Reusable infrastructure (unchanged across applications: FR-037, FR-050)

```text
bin/devloops                      # CLI entry point (Python, stdlib only)
loops/
├── README.md                         # Usage, config, recovery, Mermaid sequence diagrams (FR-047/048)
├── shared/
│   ├── devloops/                 # Shared driver package (FR-038)
│   │   ├── cli.py                    # Argument parsing, exit codes
│   │   ├── config.py                 # Defaults < workspace < CLI merge, schema checks
│   │   ├── workspace.py              # Workspace create/attach, identity, lock
│   │   ├── inputs.py                 # Input checks, fingerprints, story-ID lookup (FR-013, D-6, D-8)
│   │   ├── state.py                  # Atomic JSON read/write, run/milestone/trial transitions
│   │   ├── plan.py                   # Plan schema + semantic checks (DAG, refs, story scope)
│   │   ├── selector.py               # Next unit of work (FR-026)
│   │   ├── engine.py                 # Iteration model (plan → pause → trials → stop)
│   │   ├── claude.py                 # Headless invocation, prompt composition, session records
│   │   ├── runtime.py                # Start/ready/stop the app under test
│   │   ├── boundary.py               # Pre/post snapshots, violation detection (R-11)
│   │   ├── render.py                 # Milestone files, progress.md, task.md, open-questions.md, final report
│   │   ├── dashboard.py              # workspaces/<ws>/dashboard.html: one offline overview page
│   │   ├── openapi.py                # OpenAPI 3 JSON parse check (FR-013a), path/operation matching
│   │   ├── redact.py                 # Secret redaction before any write (FR-070)
│   │   ├── preflight.py              # Required-tool checks (FR-013b)
│   │   ├── validators/
│   │   │   ├── curl.py               # backend-dev adapter (R-8)
│   │   │   └── playwright.py         # frontend-dev adapter (R-10)
│   │   └── orchestrator.py           # Optional orchestration (R-15)
│   ├── hooks/guard_writes.py         # PreToolUse write guard (R-11)
│   ├── prompts/
│   │   ├── common.md                 # Rules shared by all steps (scope, no unrelated changes, ambiguity)
│   │   └── steps/{plan,replan,implement,fix,author-checks,validate-ui}.md
│   ├── schemas/                      # Copies of specs/001-reusable-dev-loops/contracts/*.schema.json
│   ├── config/defaults.json
│   └── tests/                        # unittest suite, fake `claude` binary, fixtures (constitution VIII)
├── backend-dev/
│   ├── Loop-instructions.md          # Authoritative backend loop instructions (FR-046)
│   ├── task.md                       # Standing assignment template (R-14)
│   └── loop.json                     # {name, required_inputs, validator: "curl", artifacts: ["openapi"]}
├── frontend-dev/
│   ├── Loop-instructions.md
│   ├── task.md
│   └── loop.json                     # {name, required_inputs: [requirements, api_spec], validator: "playwright"}
└── orchestrator/
    └── README.md                     # Orchestration behavior (logic lives in shared/devloops/orchestrator.py)
```

## Per-run workspace (D-3, FR-049)

```text
workspaces/<name>/
├── workspace.json                    # Identity: requirements fingerprint, mode, story ID, targets
├── config.json                       # Optional workspace config
├── dashboard.html                    # Rendered overview page (devloops/dashboard.py), rewritten after every command
├── backend-dev/
│   ├── task.md                       # Rendered run assignment
│   ├── progress.md                   # Rendered: action items + per-milestone start/end/tokens/cost/sessions
│   ├── outputs/
│   │   ├── milestone-01-<slug>.md    # One per milestone, task checkboxes rendered from state (FR-002/003)
│   │   ├── plan-summary.md           # Stack + source + conflicts, runtime, milestone list (FR-058)
│   │   ├── open-questions.md         # Questions + developer answers (D-4)
│   │   ├── openapi.json              # Contract artifact for frontend-dev (FR-016, FR-019)
│   │   └── final-report.md           # Outcome, assumptions for review (FR-055), validation summary
│   └── state/
│       ├── run.json  plan.json  events.jsonl  invocations.jsonl  lock
│       ├── prompts/<seq>-<step>.md
│       └── milestones/<id>/{checks.json, trials/<n>/{trial.json, validation.json, stream.jsonl, evidence/}}
├── frontend-dev/                     # Same shape; outputs/ has ui-url.txt instead of openapi.json
└── orchestrator/{state.json, progress.md}
```

## Write permissions (D-7, FR-035b)

| Actor | May write |
|-------|-----------|
| Driver | The workspace only (and it starts or stops application processes) |
| Claude: implement / fix steps | The loop's `target_dir` only |
| Claude: plan / replan / author-checks / validate-ui | Nothing, except Playwright screenshots, which the MCP server writes to the trial's `evidence/` directory |
| Anyone during a run | Never `loops/`, `bin/`, another loop's target, or another workspace |
| Tools (package managers, browsers) | Their own caches under the home directory and system temporary directories (FR-035b). Paths inside an audited repository only if listed in `boundary.allowed_extra` (research R-23) |
