---
title: Contributing
description: >-
  How to contribute to devloops: where things are in the repository, how a change is made,
  tested and committed, and the rules every change follows.
sources:
  - CLAUDE.md
  - pyproject.toml
  - .specify/memory/constitution.md
  - loops/shared/tests/helpers.py
  - loops/shared/tests/test_docs.py
---

# Contributing

These pages are for people who change devloops itself. Unlike the rest of this site, they name
files, functions and tests, because that is what you need to find your way in the code.

## Where things are

| Path | What it holds |
|---|---|
| `loops/shared/devloops/` | The driver: the Python package `devloops`, which runs every command |
| `loops/backend-dev/`, `loops/frontend-dev/` | Each loop's definition and instructions |
| `loops/shared/prompts/` | The prompt text every call shares, and that of each [step](../glossary.md#step) |
| `loops/shared/schemas/` | The JSON schemas of the plan, checks, validation results, call records, run state, configuration and the project's install manifest |
| `loops/shared/hooks/` | The Claude Code hooks that keep writes inside the [target](../glossary.md#target) |
| `loops/shared/skills/`, `loops/shared/project/` | The templates `devloops init` installs into a project |
| `loops/shared/config/defaults.json` | The packaged default configuration |
| `loops/shared/devloops/assets/app/` | The dashboard's browser app (plain JavaScript, no build) |
| `loops/shared/tests/` | The test suite, with the [stand-in](../glossary.md#stand-in) Claude Code (`fake_claude.py`) |
| `bin/devloops` | Runs devloops from the checkout, without installing it |
| `docs/`, `docs-include/`, `tools/docs/` | This site, the files it includes, and the tools that generate and check it |
| `specs/` | One folder per feature: its specification, plan, tasks and contracts |

Everything under `loops/` is the *kit*, shipped as the `devloops_kit` package beside the driver
(see `pyproject.toml`). [Architecture](architecture.md) explains how the parts fit together.

devloops runs on Python 3.10 or later and uses only the standard library: a change must not add
a runtime dependency. Node is used only to test the dashboard's browser code, and Zensical only
to build this site.

This repository is not itself a devloops [project](../glossary.md#project). To try a change, run the checkout's
`bin/devloops` in another folder:

```sh
cd /path/to/some/app
/path/to/claude-devloops/bin/devloops run
```

## Making a change

1. **Specify it.** A new feature or a change in behavior starts as a spec in `specs/`, written
   with spec-kit. See [specs and process](specs-process.md).
2. **Write the code and its tests.** The tests run the real command line against throwaway
   folders, with a stand-in for Claude Code. See [testing](testing.md).
3. **Update the pages.** A change in behavior updates the site's pages in the same commit, and
   regenerates the reference pages and example outputs it affects. See
   [documentation](documentation.md).
4. **Run the full suite**, and build the site if you changed a page.
5. **Commit.**

## Commit messages

Commits follow [Conventional Commits](https://www.conventionalcommits.org/):

```text
<type>[(scope)][!]: <description>
```

- **type**: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore` or
  `revert`.
- **scope**, optional: the part changed, such as `feat(devloops): …` or `feat(docs): …`.
- **description**: imperative mood, lower case, no full stop, ideally 72 characters or fewer.
- A breaking change has `!` before the colon and a `BREAKING CHANGE: <what breaks>` footer.
- An optional body, after a blank line, says why and what changed.

devloops is still in development, so a breaking change needs no migration path: no shims, no
deprecation period. It does need its `!` and its footer.

## Rules the tests enforce

Some rules are checked by the suite, so a change that breaks one fails its tests:

- **No application specifics.** Nothing in the loops, prompts, defaults or driver names an
  application or assumes a stack: requirements, targets and configuration are inputs
  (`test_no_app_specifics.py`).
- **Schemas match their contracts.** Each schema in `loops/shared/schemas/` is byte-identical to
  its copy in a spec's `contracts/` folder; change both together (`test_schemas_sync.py`).
- **Safe browser code.** The dashboard app builds no HTML from text, loads nothing from outside
  the page, and lists every script in `scripts.txt` (`test_app_js.py`).
- **True documentation.** The reference pages and example outputs are current, and the pages
  name only commands, options, settings and files devloops has (`test_docs.py`).

[Testing](testing.md) describes each of these.
