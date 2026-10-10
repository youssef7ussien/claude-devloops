---
title: Install
description: >-
  What devloops needs, how to install it, and how to check that it works.
sources:
  - pyproject.toml
  - bin/devloops
  - spec 002 FR-002
  - loops/shared/devloops/checkcmd.py
  - loops/shared/devloops/preflight.py
  - spec 002 FR-001
---

# Install

devloops is one Python package, with nothing else to install from Python. You install it once,
then use it in any number of projects.

## What you need

| Tool | Needed for | How to get it |
|---|---|---|
| Python 3.10 or later | everything | [python.org](https://www.python.org/downloads/), or your system's package manager |
| [Claude Code](https://code.claude.com/docs) 2.1.283 or later | everything | Install it, then run `claude` once to log in. `claude update` updates it |
| curl | [the backend loop](../glossary.md#backend-dev) | Usually installed already; otherwise your system's package manager |
| Node.js (with `npx`) | [the frontend loop](../glossary.md#frontend-dev) | [nodejs.org](https://nodejs.org/). devloops starts the Playwright MCP server with `npx` |
| A Chrome browser | the frontend loop | `npx playwright install chrome`, or point [`playwright.executable_path`](../reference/configuration.md#playwright.executable_path) at a Chrome you have |
| git | only to commit each milestone ([`git.commit_per_milestone`](../reference/configuration.md#git.commit_per_milestone)) | Your system's package manager |
| uv or pip | installing devloops | [uv](https://docs.astral.sh/uv/) is recommended; pip comes with Python |

You need the frontend tools only if your project has a frontend. devloops builds the frontend
in a real browser through the Playwright MCP server, a program that lets Claude Code control a
browser.

devloops runs Claude Code as your logged-in user, so every call uses your Claude account and
counts toward its usage.

## Install devloops

With uv, from the repository:

```sh
uv tool install git+https://github.com/youssef7ussien/claude-devloops
```

This puts the `devloops` command on your `PATH`. With pip, use
`pip install git+https://github.com/youssef7ussien/claude-devloops` instead.

From a copy of the repository (a checkout), you can also install it, or run it without
installing:

```sh
git clone https://github.com/youssef7ussien/claude-devloops
cd claude-devloops
uv tool install .        # install this checkout
uv tool install -e .     # or: install it so your edits to the checkout take effect at once
bin/devloops --version   # or: run it from the checkout, without installing
```

`bin/devloops` behaves exactly like the installed command. Use its full path from your project
folder, for example `~/claude-devloops/bin/devloops run`.

## Check the install

```sh
devloops --version
```

This prints the version of devloops you installed. Then, to see whether this machine has every
tool a run needs, run [`devloops check`](../reference/commands.md#check). In a
[project](../glossary.md#project), it marks as `unused` each tool that only a loop the project
does not use needs; outside a project, it checks the tools of both loops. Each line says whether a
tool is `ready`, `missing` or `unused`, or gives a `warning`, and a problem comes with how to fix
it:

```text
--8<-- "examples/check.txt"
```

`devloops check` exits with [code 0](../reference/exit-codes.md#exit-0) when nothing needed is
missing, and [code 30](../reference/exit-codes.md#exit-30) otherwise. It checks that Claude Code
is installed and recent enough, but not that you are logged in: if you are not, the first call of
a run stops with [`auth-failed`](../reference/statuses.md#stop-auth-failed).

## Next

[Your first run](first-run.md): set up a project and build it.
