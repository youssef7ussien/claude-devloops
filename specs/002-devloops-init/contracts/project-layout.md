# Contract: project layout

## What `init` creates in a project

```text
<project>/
├── .devloops/
│   ├── devloops.json            # shared project configuration (committed; owned by the developer)
│   ├── devloops.local.json      # optional, per developer, git-ignored; never created by init
│   ├── manifest.json            # devloops version + fingerprints of installed files (committed)
│   ├── prompts/
│   │   └── README.md            # how to override prompts (installed file)
│   ├── workspaces/              # default workspaces_dir (git-ignored by default)
│   │   └── <ws>/                # unchanged 001 workspace layout, plus state/conversations/
│   └── dashboards/              # default dashboards_dir (git-ignored by default)
│       └── <ws>/<YYYYMMDDTHHMMSSZ>[-n].html
├── .claude/
│   ├── settings.json            # only touched by `init --allow-skills`
│   └── skills/devloops-{run,approve,replan,retry,status,orchestrate,dashboard}/SKILL.md
└── .gitignore                   # one block appended under a marker
```

`workspaces/` and `dashboards/` are created when they are first used, not by `init`.

**Ownership**:

| Path | Written by | On `--upgrade` |
|------|-----------|----------------|
| `devloops.json` | `init` once, then the developer | never touched (FR-028) |
| `devloops.local.json` | the developer | never touched |
| `manifest.json` | `init` / `--upgrade` | rewritten |
| `prompts/README.md`, `.claude/skills/devloops-*/SKILL.md` | `init` (listed in the manifest) | replaced if unchanged, otherwise kept, with a `.devloops-new` file written next to it |
| `prompts/<override>` | the developer | never touched |
| `.gitignore` block | `init` | not re-added if the marker exists |
| `.claude/settings.json` | `init --allow-skills` only | never touched |

## `.gitignore` block

```gitignore
# >>> devloops (added by "devloops init")
.devloops/workspaces/
.devloops/dashboards/
.devloops/devloops.local.json
# <<< devloops
```

`--track-workspaces` and `--track-dashboards` leave out their lines. The lines use the configured
directories, relative to the project root.

## Prompt override paths

| Override file in `.devloops/prompts/` | Replaces the kit file |
|---------------------------------------|-----------------------|
| `common.md` | `shared/prompts/common.md` |
| `steps/<step>.md` (`plan`, `replan`, `implement`, `fix`, `author-checks`, `validate-ui`) | `shared/prompts/steps/<step>.md` |
| `backend-dev/Loop-instructions.md`, `frontend-dev/Loop-instructions.md` | `<loop>/Loop-instructions.md` |

Any other file in `prompts/` is ignored. `status` lists ignored files under `warnings`, so a typo
is visible.

## Workspace additions (inside 001's layout)

```text
<ws>/<loop>/state/
├── prompts/<seq>-<step>.md              # 001
└── conversations/<seq>-<step>.jsonl     # new: the redacted copy of the call's Claude Code transcript (FR-042)
```

- `workspace.json`: `targets.*` and `requirements.path` are relative to the project root when they
  are inside it.
- `requirements.speckit`: new, `{feature_dir, plan: {path, sha256}|null, tasks: {path, sha256}|null}`.

## The kit (installed devloops files)

From a source checkout, the kit is `loops/`. When installed, it is
`site-packages/devloops_kit/`. Both have the same tree:
- 001's `backend-dev/`, `frontend-dev/`, `orchestrator/`, and `shared/{prompts,schemas,hooks,config}`;
- the new `shared/skills/<name>/SKILL.md` templates.

Runs never write to the kit. The target guard rejects any target that overlaps it (FR-009,
FR-014).
