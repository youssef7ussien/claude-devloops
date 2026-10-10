# devloops

devloops turns written requirements into a working, tested application. It runs Claude Code
without its interactive screen (`claude -p`), one small part of the application at a time, and
tests each part itself before it moves on.

**Documentation: <https://youssef7ussien.github.io/claude-devloops/>**

## The core idea

Ask an AI model to build an application and it will tell you the work is done, whether it is or
not. devloops never takes its word for it.

The work is split into **milestones**, built one at a time, in order. A milestone passes only
when devloops' own **validation** passes:

- **`backend-dev`** builds the HTTP API. Before any of a milestone's code exists, it writes the
  requests to send and the answers they must get. Then it sends them to the running application.
  When the backend is done, it publishes an OpenAPI document listing only the operations its
  validation actually called.
- **`frontend-dev`** builds the user interface from the same requirements and that OpenAPI
  document. Each milestone is validated in a real browser, and every request a page sends must
  be an operation the document lists.

When validation fails, the next attempt fixes the code. Each milestone gets a limited number of
attempts (three by default). A run keeps everything in files, so it resumes where it stopped, and
the dashboard shows each milestone, every call to Claude Code with its cost, and the files.

## What you need

- Python 3.10 or later (devloops has no other Python dependencies).
- [Claude Code](https://code.claude.com/docs) 2.1.283 or later, installed and logged in.
- curl, for the backend loop.
- Node and a Chrome browser, for the frontend loop.

## Quick start

```sh
uv tool install git+https://github.com/youssef7ussien/claude-devloops
cd /path/to/your/app          # a folder with your requirements, e.g. requirements.md
devloops init                 # once: asks for the code folders and the requirements
devloops check                # reports any missing tool, and how to get it
devloops run                  # plans, then builds and validates each milestone
```

`devloops check` shows what this machine has:

```text
  ready    python          3.12.3
  ready    claude          2.1.0
  ready    curl            8.5.0
  unused   playwright-mcp  not used by this project (frontend-dev)
  unused   browser         not used by this project (frontend-dev)
  ready    git             /usr/bin/git
```

`devloops run` prints a line for each step, and ends with what it built:

```text
00:00:00 backend-dev M02 #1  validating
00:00:00 backend-dev M02 #1  ✓ trial 1 passed
00:00:00 backend-dev M02  ✓ milestone achieved: M02 Create items
00:00:00 backend-dev  ■ all 2 milestone(s) achieved
backend-dev completed; see run/progress.md
run: completed
backend-dev: completed
  OpenAPI artifact: outputs/openapi.json
```

When a run stops, it prints the one command to run next. `devloops status` shows where a run is,
and `devloops dashboard` opens the dashboard in your browser.

`pip install git+https://github.com/youssef7ussien/claude-devloops` works too. From a checkout,
`bin/devloops` runs devloops without installing it.

## Learn more

- [Getting started](https://youssef7ussien.github.io/claude-devloops/getting-started/install/):
  install devloops and make your first run.
- [How it works](https://youssef7ussien.github.io/claude-devloops/how-it-works/): the plan, the
  steps, validation, trials, and the files a run writes.
- [Guides](https://youssef7ussien.github.io/claude-devloops/guides/backend-loop/): each loop, the
  dashboard, approval, configuration, spec-kit, security, and upgrades.
- [Reference](https://youssef7ussien.github.io/claude-devloops/reference/): every command, option,
  setting, exit code and file.
- [Contributing](https://youssef7ussien.github.io/claude-devloops/contributing/): how devloops is
  built and tested, and how its features are specified.
