# Contract: CLI changes

Revises specs/001-reusable-dev-loops/contracts/cli.md and specs/002-devloops-init/contracts/cli.md
for the dashboard. Everything not listed is unchanged.

## `devloops dashboard`

```text
devloops dashboard [--workspace <ws>] [--host <addr>] [--port <n>] [--token <t> | --no-token]
                   [--no-open] [--daemon]
devloops dashboard --stop
devloops dashboard --export [<path>] [--workspace <ws>]
```

| Form | Behavior | Exit |
|------|----------|------|
| *(no mode)* | Serve the project's workspaces in the foreground until Ctrl+C; open the workspace in a browser unless `--no-open`. A server already running for the project: print its address, open it, return | 0; 1 when the port or address cannot be used |
| `--daemon` | Start the server in the background (R-11); print `serving: <url>` and `log: <path>` once it answers; open the browser unless `--no-open` | 0; 1 when it does not start within 10 s (the log's last lines are printed) |
| `--stop` | Stop the project's running server, however started; remove its record | 0 (`stopped` or `not running`) |
| `--export [<path>]` | Write the export (contracts/export.md); print path, size, five largest items, unavailable conversations, files not embedded | 0; 1 when it cannot be written |

- `--host`, `--port`, `--token`, `--no-token`, `--no-open` go with serving (with or without
  `--daemon`); with `--stop` or `--export` they are a usage error (exit 2).
- `DEVLOOPS_NO_BROWSER=1` in the environment: no browser is opened in any form (the address is
  still printed).
- `--serve`, `--open`, `--out`, and `--light` are removed (usage error if given).
- `--json`: serving prints one object `{"serving": url, "workspace", "token": bool, "pid",
  "daemon": bool, "log"?}`; `--stop` prints `{"stopped": bool}`; `--export` prints `{"workspace",
  "export": {"path", "bytes", "largest", "unavailable", "not_embedded"}}`.

## Run and decision commands (`run`, `approve`, `replan`, `retry`, `status`)

- They never write `<workspace>/dashboard.html` and never write an export (FR-008, FR-010).
- Text output ends with `dashboard: <url>` when a server is running for the project, otherwise
  `dashboard: devloops dashboard --daemon[ --workspace <ws>]` (FR-009). They never start a server.
- `--json` objects: `dashboard` and `full_dashboard` are removed; `dashboard_url` is present only
  when a server is running.

## `devloops init`

- `--track-dashboards` is removed. `dashboards_dir` is no longer written to `devloops.json` nor
  ignored in `.gitignore`.

## Configuration

- Removed keys: `dashboard.light`, `dashboard.full_on_stop` (and the `dashboard` object),
  `dashboards_dir`. A file that still sets them is a configuration error like any unknown key
  (devloops is in development; no migration). The error names the key and says it was removed by
  this feature and can be deleted (e.g. `devloops.json: "dashboards_dir" was removed (the
  dashboard is served or exported now); delete it`).
