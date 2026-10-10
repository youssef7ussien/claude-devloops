---
title: Reference
description: >-
  What each reference page holds, and how the pages stay true to devloops.
sources:
  - tools/docs/gen_reference.py
  - tools/docs/descriptions.json
  - loops/shared/devloops/cli.py
  - loops/shared/schemas
  - spec 006 FR-012
  - spec 006 FR-013
---

# Reference

These pages answer "what exactly…": every command, setting, exit code, step, status and file,
each with its own address you can link to. To learn how to do something, start from the
[guides](../guides/backend-loop.md) instead; to understand why devloops works the way it does,
see [how it works](../how-it-works/index.md).

| Page | What it holds |
|---|---|
| [Commands](commands.md) | Every command and option, with its default, the options that cannot be used together, and options that were removed |
| [Configuration keys](configuration.md) | Every setting: which file it goes in, its type, its default and what it does, and which file wins when several set it |
| [Exit codes](exit-codes.md) | What each exit code means and what to do next |
| [Steps](steps.md) | Each kind of call to Claude Code: whether it changes files, its tools, the form of its answer, and its model setting |
| [Statuses](statuses.md) | Every status of the run, a loop, a milestone, a task, a trial and the plan's approval, and every reason a loop stops |
| [State files](state-files.md) | Every file a run writes in its [workspace](../glossary.md#workspace), and the fields of the main ones |

## How these pages stay right

The pages above are generated from devloops itself: the commands and options from its
command-line definitions, the settings and file fields from its JSON schemas, the exit codes,
steps and statuses from its code. The plain-language meanings that the code does not hold are
in one file next to the generator, `tools/docs/descriptions.json`.

devloops' tests fail when a page no longer matches the code, or when the code has a value that
file does not describe, so a change to devloops cannot leave these pages behind. The site's
build also fails when a link points at an entry that no longer exists.

To change a page, change its source (the option's help text, the schema's description, or
`descriptions.json`), then run `python3 tools/docs/gen_reference.py`. See
[documentation](../contributing/documentation.md).
