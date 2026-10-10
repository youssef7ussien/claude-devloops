---
title: Known limitations
description: >-
  What devloops does not do yet, or does with a catch, and how to work around each.
sources:
  - loops/shared/devloops/orchestrator.py
  - loops/shared/devloops/artifacts.py
  - loops/shared/devloops/validators/playwright.py
  - loops/shared/devloops/redact.py
  - loops/shared/devloops/config.py
  - specs/006-docs-site/research.md
  - spec 002 FR-014
  - spec 003 FR-019
---

# Known limitations

## The frontend cannot run without the backend

A [run](../how-it-works/run-lifecycle.md) includes the backend [loop](../glossary.md#loop), or
both loops, but never the frontend loop alone: the frontend is built against the OpenAPI document the backend loop
publishes, and devloops has no way yet to give it a document and a backend from elsewhere. A
project whose configuration names only a frontend target stops before anything is written, with
the reason `frontend-needs-backend` and [exit code 30](../reference/exit-codes.md#exit-30).

## No target at the project root

Each loop writes its code into its own folder (`backend/`, `frontend/`, or any other name), never
the project root itself, because the project root holds `.devloops/`. A
[target](../glossary.md#target) that overlaps `.devloops/`, the [workspace](../glossary.md#workspace), another loop's target, or
devloops' own files is refused.

## Not under `~/.claude`

Claude Code treats the files in `~/.claude` as sensitive and blocks writes there. A target inside
it fails: Claude Code cannot write the code, and reports the problem as an [open question](../glossary.md#open-question). Keep projects
somewhere else.

## Conversations depend on Claude Code's own files

devloops copies each call's conversation from the session files Claude Code keeps on your
machine. Their format is Claude Code's own and is not documented, so it may change. A record
devloops does not recognize is shown as raw JSON in the [dashboard](dashboard.md), and a
conversation that cannot be found is marked unavailable. Neither ever fails a run.

## The first browser start may time out

By default, the frontend loop starts the Playwright MCP server (the tool that lets Claude Code
drive a browser) with `npx`. When `npx` must first download a
new release of the server, the server can miss Claude Code's start-up time limit. The [trial](../glossary.md#trial)
is then void, and the run stops with [exit code 50](../reference/exit-codes.md#exit-50) and the
message "the Playwright MCP server did not start". No trial is used up: run the command again. To
avoid it, run this once before the run, so the download is done:

```sh
npx @playwright/mcp@latest --help
```

## Only listed secrets are hidden

Before it writes anything, devloops replaces with `***` the secret values you list in its
configuration: the values of the environment variables named in
[`secrets.env`](../reference/configuration.md#secrets.env), and the strings in
[`secrets.literals`](../reference/configuration.md#secrets.literals). It does not look for
secrets by itself, so a value you did not list is written as it is. Review a
workspace or an exported dashboard before you share it, or before you serve the dashboard beyond
your own machine. See [security](security.md).

## An invalid run configuration exits 2, not 30

When the run configuration (the `config` settings in `.devloops/devloops.json`, or a file given
with `--config`) does not match its schema, devloops stops with a usage error,
[exit code 2](../reference/exit-codes.md#exit-2). Other problems with the inputs exit 30. Whether
this one should exit 30 too is not decided yet, so check for both codes in a script.
