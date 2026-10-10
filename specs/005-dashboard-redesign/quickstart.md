# Quickstart: validating the dashboard redesign

## Prerequisites

- A checkout of this repository; `bin/devloops` on the PATH (or `python3 -m devloops.cli`).
- For the browser checks: a desktop browser. For the JS unit tests: `node` (optional; the tests
  are skipped without it).
- A project with workspaces to look at: the test fixtures, or a real project such as quickflow
  (delete `"dashboards_dir"` from its `.devloops/devloops.json` first: the key is removed,
  contracts/cli.md).

## 1. Automated tests

```sh
cd /data/space/workspace/claude-loops
VISUAL=true EDITOR=true timeout 900 python3 -m unittest discover -s loops/shared/tests
```

Expected: all pass. The dashboard modules are covered by `test_dashboard_data`, `test_serve`,
`test_dashboard_export`, `test_live_call`, `test_dashboard_cli`, and `test_app_js` (runs `node --test` on
`assets/app/tests/`; skipped without node).

## 2. Serve, follow, stop

```sh
devloops dashboard --daemon            # prints serving: http://127.0.0.1:8765/w/<ws>/ and log: …
devloops dashboard --daemon            # prints the same address; no second server
devloops dashboard --stop              # stopped
devloops dashboard --stop              # not running (exit 0)
devloops dashboard                     # foreground; Ctrl+C stops it
```

In the browser (SC-001–SC-003), with the developer tools' network panel open:
1. Refresh on `#/`: only `summary`, `now`, and `version` (and the two assets) are requested; the
   overview is usable within 1 s.
2. Open a loop, a trial, the calls, a conversation, the files: each requests only its
   own data and shows within 1 s.
3. Start a run (`devloops run` in another terminal): the now panel shows the call and its tools as
   they happen; when a trial ends, the open view updates in place, keeping scroll and open
   sections. Views not on screen make no requests.
4. Stop the server: the page shows **Offline** and keeps its data.

## 3. Views

On a workspace with a failed backend trial and a failed frontend trial (e.g. quickflow M08):
- **Tokens** (SC-004): the loop card and loop view show tokens; the loop view shows input,
  output, cache write, cache read, cache-hit rate, and cost per milestone achieved; a milestone's
  trials add up to the milestone, and its steps to the trial.
- **Trial** (SC-005): from the timeline, open each failed trial: every failing check, criterion,
  contract problem, unit-test result, and boundary violation in its `validation.json` is listed
  with its evidence; screenshots show as images.
- **Plan** (in the loop view since 2026-10-10): every milestone, criterion (passed, failed, not
  checked), task, and dependency; ids show their text on hover; the questions line opens Questions filtered to the loop;
  the Steps card has a row per planning attempt (opening its call); each milestone shows its tasks,
  then its acceptance criteria as a table.
- **Conversation**: tool calls folded; the error count in the summary line and "Errors only (N)";
  "System records" shows each record in its place;
  "Files changed" jumps to the tool call.
- **Markdown** (FR-025): open a Markdown file with a list item that continues on the next line —
  the whole item shows.
- **Search** (SC-006): Ctrl+K, type a string from one conversation and one file: both appear
  within 1 s and open at the match.

## 4. Export

```sh
devloops dashboard --export                          # <workspace>/exports/<time>.html
devloops dashboard --export /tmp/run.html            # the given path
```

Copy the file alone to another folder, turn off the network, open it (SC-007): every view,
file, and conversation within 5 MB opens; search works; nothing polls; the top bar says it is a
snapshot. `grep` the file for a configured secret value: no match (SC-008).

## 5. No dashboard files from commands

Run `devloops run` to its end: no `dashboard.html` in the workspace and nothing in `exports/`
(SC-009); the output ends with `dashboard: …`.
