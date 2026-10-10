---
title: Testing
description: >-
  How to run devloops' tests, how they stand in for Claude Code, and the rules they enforce.
sources:
  - CLAUDE.md
  - loops/shared/tests/helpers.py
  - loops/shared/tests/fake_claude.py
  - loops/shared/tests/stub_loop.py
  - loops/shared/tests/samples.py
  - loops/shared/tests/test_no_app_specifics.py
  - loops/shared/tests/test_schemas_sync.py
  - loops/shared/tests/test_app_js.py
  - loops/shared/tests/test_packaging.py
  - loops/shared/tests/test_dashboard_perf.py
  - loops/shared/tests/test_docs.py
  - loops/shared/devloops/assets/app/tests/load.js
---

# Testing

devloops' tests run offline and cost nothing: a [stand-in](../glossary.md#stand-in) answers in
place of Claude Code. They use only Python's `unittest`, so there is nothing to install.

## Running the tests

Run them from the repository's root folder:

```sh
VISUAL=true EDITOR=true python3 -m unittest discover -s loops/shared/tests
```

The full suite takes about ten minutes, so run it in the background while you work.
`VISUAL=true EDITOR=true` matters: some tests reach the prompt that reviews a plan, and its "edit
answers" choice opens `$VISUAL` or `$EDITOR`; `true` makes that a command that does nothing,
instead of your real editor.

One module, or one test:

```sh
VISUAL=true EDITOR=true python3 -m unittest discover -s loops/shared/tests -p 'test_serve.py'

cd loops/shared/tests
VISUAL=true EDITOR=true python3 -m unittest test_serve.ServeTest.test_read_only
```

The second form runs from the tests folder, where the shared `helpers` module can be imported.

### Optional parts

| Setting | Effect |
|---|---|
| `DEVLOOPS_TEST_PACKAGING=1` | Runs `test_packaging.py`, which builds the wheel with `uv` and installs it into a temporary virtual environment. Needs `uv` on `PATH`; skipped otherwise |
| `DEVLOOPS_SKIP_PERF=1` | Skips `test_dashboard_perf.py`, which times the dashboard's answers and can fail on a slow or busy machine |

Two other parts run only when their tool is there:

- The dashboard's browser code has its own tests in `loops/shared/devloops/assets/app/tests/`,
  run with `node --test loops/shared/devloops/assets/app/tests/`. `test_app_js.py` runs them too,
  and skips them when `node` is not installed. Node is a test tool only; devloops never needs it
  to run.
- The site's strict build (`test_docs.py`) runs when Zensical is installed, on `PATH` or in
  `.venv-docs/`. See [documentation](documentation.md).

There is no linter or formatter.

## How the tests work

Most tests run the real `bin/devloops` command, in a throwaway folder, against a stand-in for
Claude Code.

### A throwaway folder: `TempEnv`

`helpers.TempEnv` (in `loops/shared/tests/helpers.py`) makes a temporary folder for one test:

- `repo/`: a copy of the real `loops/` and `bin/` (or links to them, with `symlink=True`), set up
  as a devloops project whose workspaces are in `repo/workspaces/` and whose plans pause for
  review (`questions: ask`);
- `target/` and `frontend-target/`: the folders the loops write code to;
- `fake/`: the stand-in's answers and its log of calls;
- `claude-config/` and `runtime/`: where the stand-in writes conversations and where a dashboard
  server records itself, so no test touches your own.

Copying `loops/` and `bin/` is the default, so a test that makes Claude write outside its target
cannot change the real checkout. `TempEnv.env` is the environment to run commands with, already
pointed at the stand-in; `TempEnv.run_cli` runs `bin/devloops` with it and returns the exit code,
standard output and standard error. No test opens a browser: `helpers` sets
`DEVLOOPS_NO_BROWSER=1` for every command.

### The stand-in Claude Code: `fake_claude.py`

`loops/shared/tests/fake_claude.py` accepts the options devloops passes to `claude -p`. devloops
calls it instead of Claude Code when `DEVLOOPS_CLAUDE_BIN` points at it. It finds the step from
the first line of the prompt, and answers from a scenario: a JSON file named by
`DEVLOOPS_FAKE_SCENARIO`, written with `TempEnv.write_scenario`:

```python
t.write_scenario({"steps": {
    "plan": {"structured_output": samples.plan()},      # the same answer on every call
    "implement": [                                      # one answer per call; the last repeats
        {"exit_code": 1, "api_error_status": 429},      # a rate limit
        {"structured_output": {...},
         "writes": [{"path": "app.py", "content": "...", "tool": "Write"}]},
    ],
}})
```

An answer can return a structured output, write files (through the write guard, or directly as
a shell command would, which only the write audit in `boundary.py` sees), report tool uses, fail with an API
error, sleep (to test timeouts and interruption), leave a process running, or report its own
token counts and cost. The docstring at the top of `fake_claude.py` lists every field. The
stand-in also writes a conversation file like Claude Code's, and appends each call, with its
prompt, to the log named by `DEVLOOPS_FAKE_LOG`, so a test can check what devloops sent.

`loops/shared/tests/samples.py` returns a valid example of each document (a plan, checks, a
validation result and so on) for scenarios to start from. `loops/shared/tests/fixtures/` holds
a small HTTP application (`http_app.py`) for the curl validator's tests, spec-kit features,
stories, and the expected rendered outputs (`golden/`).

### A loop without a real application: `stub_loop.py`

Tests of the engine's limits, recovery and stops do not need a real application.
`stub_loop.StubLoopMixin` sets up a `backend-dev` loop whose validator is a stub: every
criterion passes, unless `DEVLOOPS_STUB=fail`.

## Rules the tests enforce

| Test | Rule |
|---|---|
| `test_no_app_specifics.py` | No file that steers the loops (loop definitions, prompts, defaults, the driver, `bin/devloops`) names an application or assumes a stack, such as `npm install` or `fastapi`. The site and the tests are not scanned, so they may show examples |
| `test_schemas_sync.py` | Each schema in `loops/shared/schemas/` is byte-identical to its copy in the `contracts/` folder of the spec that owns it. Change both together |
| `test_app_js.py` | Every script of the dashboard app is listed in `scripts.txt`; no script uses `innerHTML`, `outerHTML`, `insertAdjacentHTML` or `document.write`, so text Claude wrote is only ever shown as text; nothing loads from outside the page. The copied-in Prism files in `vendor/` are exempt from the markup rule, and the app may use Prism only to split code into tokens |
| `test_docs.py` | The reference pages and example outputs are current; every hand-written page has its front matter and its sources exist; pages name only commands, options, settings and workspace files devloops has; each status is in its diagram; the site builds strictly |

The browser code has two more rules that its design depends on: each script is a function that
runs at once over `window.DL` and touches no page element when it loads, so its pure parts can
run under `node --test` (`assets/app/tests/load.js`), and no script uses a `style=` attribute or
an inline script, because the page's content security policy allows only its own files.

When `test_docs.py` fails, its message names the page, the line and the item.
[Documentation](documentation.md) explains each check and how to fix it.
