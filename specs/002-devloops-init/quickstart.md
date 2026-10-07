# Quickstart: Validating Devloops Project Setup

This guide shows how to prove that devloops installs, sets up a project, and runs there. Command
formats are in [contracts/cli.md](./contracts/cli.md), and file layouts are in
[contracts/project-layout.md](./contracts/project-layout.md). 001's
[quickstart](../001-reusable-dev-loops/quickstart.md) still applies inside a workspace.

## Prerequisites

The same as 001, plus `uv`, for installing the tool. Set:
- `REPO` to this checkout's path;
- `SCRATCH` to an empty temporary directory.

## 1. Offline tests (no model, no network)

```bash
python3 -m unittest discover -s loops/shared/tests
```

**Expected**: all tests pass, the 312 from 001 and the new ones.

| Scenario | Expected result | Spec |
|----------|-----------------|------|
| `init --no-prompt` in an empty directory | It creates `devloops.json`, `manifest.json`, `prompts/README.md`, 7 skills, and the `.gitignore` block, and nothing else; then `init` again changes nothing | US1, FR-003–007, SC-003 |
| `init` with an existing different `.claude/skills/devloops-run/SKILL.md` | Exit 30 `init-conflict`, listing the path; no files written | FR-005 |
| `init` with answers given on a pseudo-terminal | The answers are written to `devloops.json`; an invalid target is asked again | FR-007a, FR-007b |
| `run`/`orchestrate` from a subfolder with configured targets and requirements, using the fake Claude | The workspace is under `.devloops/workspaces/main`; no path flags are needed | US2, SC-002 |
| A command outside any project | Exit 2, suggesting `devloops init` | FR-008 |
| A config value in the shared file, the local file, and on the command line | The command line wins over the local file, which wins over the shared file; `run.json` records the result | FR-010 |
| Editing `devloops.json` after the first run | `status --json` lists `config_drift`; the run uses the frozen value | FR-015 |
| A target that overlaps `.devloops/`, the kit, or the other target | Exit 30 `target-unwritable` | FR-014 |
| Moving the project directory, then `run` | It resumes; the targets resolve under the new root | FR-013 |
| `playwright.headless: false` and `executable_path` | The derived MCP command has no `--headless` and does have `--executable-path`; an explicit `mcp_command` wins | FR-017 |
| `check` with each tool hidden from `PATH` in turn | Each run names the item and its fix, and exits 30 | FR-018, FR-019, SC-005 |
| Skill files | Each names one command, `$ARGUMENTS`, `--json`, and `allowed-tools`; this repository's skills equal what `init` renders | FR-021, FR-022 |
| `init --allow-skills` with existing settings | The rule is added once; other keys are kept; invalid JSON is left untouched (exit 30) | FR-022b |
| A spec-kit fixture with `tasks.md`, and `--story-id US2` | The planning context has the parsed phases; a plan that skips an in-scope task without a reason is invalid; the plan summary lists planned and omitted tasks | FR-023a–d, FR-025 |
| `tasks.md` edited after planning | Exit 30 `input-changed` (input `tasks`) | FR-023c |
| `--upgrade` after changing one skill and deleting another | The unchanged files are replaced; the changed one is kept and a `.devloops-new` written; the deleted one is reported; the manifest version is bumped | FR-027, SC-004 |
| `--upgrade` with a newer manifest | Exit 30 `downgrade-refused`, no changes | FR-028 |
| A prompt override for `steps/plan.md` | The prompt contains the override; the invocation record has its `prompt_sources` entry | FR-030, FR-031 |
| A fake transcript in a temporary `CLAUDE_CONFIG_DIR` | It is copied, redacted, to `state/conversations/`; a missing one is marked `unavailable` | FR-040–042 |
| Reaching `completed` / `stopped-on-failure` | A new timestamped full dashboard each time; none at `awaiting-approval` | FR-036, FR-039 |
| Opening the full dashboard | No `src`/`href` to the network; all evidence embedded; the secret appears 0 times | SC-009, SC-010 |
| `status` and `dashboard --light` on the committed T076 workspaces | Both succeed | FR-033, SC-008 |

## 2. Install the tool and set up a fresh project

```bash
uv tool install "$REPO"          # or: uv tool install git+<repo-url>
devloops --version               # 0.2.0
mkdir -p "$SCRATCH/app" && cd "$SCRATCH/app" && git init -q
devloops init                    # accept the defaults: backend, frontend, (no requirements)
devloops check
```

**Expected**:
- `init` lists its files and the permission rule.
- `check` exits 0, or names each missing prerequisite with its fix.
- `git status` shows only `.devloops/devloops.json`, `.devloops/manifest.json`,
  `.devloops/prompts/README.md`, `.claude/skills/devloops-*`, and `.gitignore`.

## 3. Real end-to-end run from a spec-kit feature (SC-007)

1. In `$SCRATCH/app`, create a small spec-kit feature, `specs/001-health/` with `spec.md`,
   `plan.md`, and `tasks.md`. You can copy and adapt 001's smoke fixture: a `GET /health` backend
   and a page that shows its status.
2. Make it active with `.specify/feature.json` = `{"feature_directory": "specs/001-health"}`.
3. Put machine-specific browser settings in `.devloops/devloops.local.json`, e.g.
   `{"config": {"playwright": {"executable_path": "/usr/bin/chromium"}}}`.
4. Run:

   ```bash
   devloops orchestrate --speckit-feature --review-plan   # pauses at the backend plan (exit 10)
   # review .devloops/workspaces/main/backend-dev/outputs/plan-summary.md
   # (spec-kit tasks planned and omitted)
   devloops approve backend-dev    # builds the backend, then pauses at the frontend plan
   devloops approve frontend-dev   # builds the frontend; exit 0
   ```

**Expected**:
- `orchestrate` ends `completed`, and the milestones follow the spec-kit phases with task IDs.
- A full dashboard path is printed when it ends.
- Copy that one file to another directory (or machine) and open it offline. Every screenshot,
  check, prompt, and conversation is readable.

Record the results, costs, and any defects in `validation-results.md`, as 001 did for T076.

## 4. Upgrade

1. Build a second version locally: bump `__version__` in a scratch copy, then
   `uv tool install --force`.
2. Edit one installed skill.
3. Run `devloops init --upgrade`.

**Expected**:
- The edited skill is kept, with a `SKILL.md.devloops-new` written next to it.
- The other installed files are updated.
- `manifest.json` shows the new version.
- Running an older version against this project warns about the version mismatch.

## 5. Visible browser

Set `{"config": {"playwright": {"headless": false}}}` in `devloops.local.json`, in a new workspace.
Then run frontend-dev.

**Expected**: a browser window appears during `validate-ui`. `devloops check` shows a `display`
warning on a machine without a display.
