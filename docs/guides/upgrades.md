---
title: Upgrades
description: >-
  Upgrading devloops, then the files it installed in each project, without losing your own
  changes to them.
sources:
  - loops/shared/devloops/initcmd.py
  - loops/shared/devloops/cli.py
  - loops/shared/config/defaults.json
  - spec 002 FR-027
  - spec 002 FR-028
  - spec 002 FR-029
---

# Upgrades

Upgrading takes two steps: install the new devloops once, then update the files it installed in
each [project](../glossary.md#project).

## 1. Install the new devloops

Upgrade it the way you installed it:

```sh
uv tool upgrade devloops                                                       # installed with uv
pip install --upgrade git+https://github.com/youssef7ussien/claude-devloops    # installed with pip
git pull                                                                       # a checkout
```

Then `devloops --version` prints the new version.

## 2. Upgrade each project

`devloops init` copied a few files into your project: the two [skills](skills.md) in
`.claude/skills/`, and `.devloops/prompts/README.md`. A new devloops may ship new versions of
them. Until you update them, devloops commands in the project (such as `run` and `status`) warn
that the project was set up with another version, and say to run:

```sh
devloops init --upgrade
```

[`--upgrade`](../reference/commands.md#init--upgrade) compares each installed file with the
fingerprint devloops recorded when it wrote the file, in `.devloops/manifest.json`, so it knows
whether you changed it:

| The file | What `--upgrade` does |
|---|---|
| You did not change it | Replaces it with the new version |
| You changed it | Keeps your version, and, when this version brings a new one, writes it next to yours as `<file>.devloops-new` for you to compare and merge |
| You deleted it | Reports it, and leaves it deleted; add [`--restore`](../reference/commands.md#init--restore) to write it again |
| It is new in this version | Adds it |
| devloops no longer ships it | Removes it, unless you changed it: then it is kept |

Then it records the new version in the manifest, and the warning stops. devloops checks every
file before it writes the first one, so a problem leaves the project as it was.

`--upgrade` never touches:

- your configuration, `.devloops/devloops.json` and `.devloops/devloops.local.json`;
- your [prompt overrides](prompts.md);
- the `.gitignore` rules;
- the [workspaces](../glossary.md#workspace) and everything in them.

A setting that is new in this version takes its default value until you set it; see
[configuration](configuration.md).

## When it refuses

[`devloops init --upgrade`](../reference/commands.md#init--upgrade) exits with
[code 30](../reference/exit-codes.md#exit-30), and changes nothing, when:

- the project was set up with a newer devloops than the one running (`downgrade-refused`):
  install that version or a later one;
- a file new in this version already exists in the project with other content
  (`init-conflict`): move it away and run the command again;
- `.devloops/manifest.json` cannot be read: move it away and run
  [`devloops init`](../reference/commands.md#init) again.

On a project that was never set up, it stops with a usage error
([code 2](../reference/exit-codes.md#exit-2)) and says to run `devloops init` first.

## Runs in progress

A [run](../how-it-works/run-lifecycle.md) keeps the configuration it started with, so upgrading devloops in the middle of a run does
not change the settings that run uses. devloops is still in development, though, and does not
promise that a new version can resume a workspace an older one started. Finish a run before you
upgrade, or start a new workspace after.
