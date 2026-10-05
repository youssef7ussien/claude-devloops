---

description: "Task list for devloops project setup (install once, init per project)"
---

# Tasks: Devloops Project Setup

**Input**: Design documents from `specs/002-devloops-init/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Included, as in 001. The constitution (VIII) requires the infrastructure to be testable
without an application, and [quickstart.md §1](./quickstart.md) lists the offline scenarios. Tests
use stdlib `unittest`, the fake `claude`, and fake transcripts, so they need no model and no
network.

**Organization**: Tasks are grouped by user story (US1–US7 in spec.md). The full dashboard belongs
to US2 (acceptance scenario 7). It has its own phase because it is large.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: The user story this task belongs to (US1–US7)
- Paths are relative to the repository root

## Conventions that apply to every task

- **Python** ≥ 3.10, **standard library only at runtime**. setuptools is build-time only
  (research P-1).
- **Package**: `loops/shared/devloops/`. Tests are in `loops/shared/tests/test_*.py`. Run them
  with `python3 -m unittest discover -s loops/shared/tests`.
- **Test imports**: tests `import helpers` before `from devloops import …`.
- **Writes**: state and project files are written with `state.write_json_atomic`, or a temp file
  plus `os.replace`.
- **Redaction**: every text written to `state/`, and everything embedded in a dashboard, passes
  through `redact.Redactor` (001 FR-070, 002 FR-041).
- **Schemas**:
  - 001's six schemas in `loops/shared/schemas/` are byte-identical copies of
    `specs/001-reusable-dev-loops/contracts/*.schema.json` (`test_schemas_sync`). **Every change
    goes to both copies**, and to `specs/001-reusable-dev-loops/data-model.md` if it adds a field.
  - The two new schemas are copies of `specs/002-devloops-init/contracts/*.schema.json`.
  - Changes are **additive only**, so old workspaces stay valid (FR-033).
- **No file moves under `loops/`** (research P-1). The kit is mapped by packaging.
- **Kit and project, not `repo_root`**: after Phase 2, code uses `kit.Kit` for packaged files, and
  `project.Project` for project files and workspaces.
- **Commits**: Conventional Commits, no Co-Authored-By trailer, directly on `main` (user
  preference).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Packaging, version, schema copies, and test harness additions.

- [ ] T001 Create `pyproject.toml` at the repository root, per research P-1:
  - **Build system**: `[build-system] requires = ["setuptools>=68"]`,
    `build-backend = "setuptools.build_meta"`.
  - **Project**: `[project] name = "devloops"`, `dynamic = ["version"]`,
    `requires-python = ">=3.10"`, `dependencies = []`, with a short `description`.
  - **Command**: `[project.scripts] devloops = "devloops.cli:entry"`.
  - **Packages**: `[tool.setuptools] packages = ["devloops", "devloops.validators",
    "devloops_kit"]`, `include-package-data = false`.
  - **Package directories**: `[tool.setuptools.package-dir] devloops = "loops/shared/devloops"`,
    `devloops_kit = "loops"`.
  - **Package data**: `[tool.setuptools.package-data] devloops_kit = ["backend-dev/*",
    "frontend-dev/*", "orchestrator/*", "shared/prompts/*.md", "shared/prompts/steps/*.md",
    "shared/schemas/*.json", "shared/hooks/*.py", "shared/config/*.json",
    "shared/skills/*/SKILL.md", "shared/project/**/*"]`.
  - **Version**: `[tool.setuptools.dynamic] version = {attr = "devloops.__version__"}`.
- [ ] T002 Add `entry()` to `loops/shared/devloops/cli.py`. It performs the same Python ≥ 3.10
  check as `bin/devloops`, then calls `sys.exit(main(sys.argv[1:]))`, as the console-script
  target.
- [ ] T003 [P] Set `__version__ = "0.2.0"` in `loops/shared/devloops/__init__.py` (research P-18).
- [ ] T004 [P] Copy the two new schemas into `loops/shared/schemas/`:
  `specs/002-devloops-init/contracts/project-config.schema.json` and `manifest.schema.json`.
  Then extend `loops/shared/tests/test_schemas_sync.py`:
  - `SCHEMA_NAMES` becomes a mapping from schema name to contracts directory: 001 for `config`,
    `plan`, `checks`, `validation-result`, `invocation-record`, and `run-state`; 002 for
    `project-config` and `manifest`;
  - the byte-identity check uses that mapping;
  - the missing/extra check covers the union of both directories' schemas.
- [ ] T005 [P] Make `loops/shared/tests/fake_claude.py` write a transcript after each call:
  - **Where**: `$CLAUDE_CONFIG_DIR/projects/<encoded cwd>/<session-id>.jsonl`. `<encoded cwd>` is
    the call's working directory with every non-alphanumeric character replaced by `-`.
  - **Records**:
    - a `user` record with the prompt as `text` content;
    - an `assistant` record with a `tool_use` block (`Read` of a file);
    - a `user` record with a `tool_result` block;
    - an `assistant` record with a `text` block;
    - one record of an unknown type, `{"type": "fake-internal", "x": 1}`.
  - **Skipping**: no transcript when `CLAUDE_CONFIG_DIR` is unset, or when the scenario sets
    `"transcript": false`.
  - **Long paths**: when the scenario sets `"transcript_dir": "<name>"`, use that directory name
    instead of `<encoded cwd>`, to simulate Claude Code's truncated long paths.
- [ ] T006 Extend `loops/shared/tests/helpers.py`:
  - `TempEnv.__enter__` writes `<root>/.devloops/devloops.json` = `{"schema_version": 1,
    "workspaces_dir": "workspaces"}`. With it, every existing test runs inside a project whose
    workspaces stay at `<root>/workspaces/` (research P-17).
  - It sets `CLAUDE_CONFIG_DIR=<base>/claude-config` in `self.env`.
  - Add `TempEnv.make_project(path, config=None)`, which writes a `.devloops/devloops.json` in any
    directory, and `TempEnv.read_json(path)`.
  - `run_cli` passes `cwd` through, so tests can run from a subfolder.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Split 001's single `repo_root` into **kit** (packaged files) and **project**
(`.devloops/` + workspaces), and add the project and local configuration layers. Every story
depends on this.

**⚠️ CRITICAL**: The whole 001 suite (312 tests) must be green at the end of this phase (SC-008).

- [ ] T007 [P] Write `loops/shared/tests/test_kit.py`:
  - `Kit.resolve()` from this checkout gives `mode == "source"`, `root == <repo>/loops`, and
    `reserved == [<repo>/loops, <repo>/bin]`.
  - `Kit.path("shared", "prompts", "common.md")` exists.
  - `Kit.command_for(project_root)` returns `bin/devloops` when the checkout is the project root,
    `<rel>/bin/devloops` when the checkout is inside the project, and an absolute path otherwise.
  - The installed mode, simulated by `Kit(root=<tmp copy of loops/>, mode="installed",
    reserved=[...])`, returns `devloops` as the command.
- [ ] T008 [P] Write `loops/shared/tests/test_project.py`:
  - `project.find(start)` finds the nearest `.devloops/devloops.json` from a nested subfolder, and
    the nearest of two nested projects wins.
  - `DEVLOOPS_PROJECT` overrides the search. With no project, it raises `state.UsageError` whose
    message contains `devloops init`.
  - Invalid `devloops.json` cases each raise an error naming the file and the key:
    - invalid JSON;
    - an unknown key;
    - a wrong type;
    - `requirements` with both `path` and `speckit_feature`, or with neither;
    - `story_file` without `path`.
  - The local file is deep-merged over the shared one, and an invalid local file is reported with
    its own path (FR-016).
  - `Project.resolve(rel)` and `Project.relative_or_absolute(path)` round-trip for paths inside
    the project and keep outside paths absolute.
  - `Project.workspaces_dir` and `dashboards_dir` default to `.devloops/workspaces` and
    `.devloops/dashboards`.
- [ ] T009 Implement `loops/shared/devloops/kit.py` (research P-2):
  - **Class**: `Kit(root, mode, reserved)` with `path(*parts)`, `version`, and
    `command_for(project_root)`.
  - **`resolve()`**:
    - If `<dirname(devloops.__file__)>/../../backend-dev/loop.json` exists, it returns source mode
      with the root `<checkout>/loops` and `reserved = [<checkout>/loops, <checkout>/bin]`.
    - Otherwise it imports `devloops_kit` and uses `devloops_kit.__path__[0]`, with
      `reserved = [<site>/devloops_kit, <site>/devloops]`.
- [ ] T010 Implement `loops/shared/devloops/project.py` (research P-3, P-4, P-6, data-model
  "Project"):
  - `find(start, env)`.
  - `Project(root)`, with:
    - `shared_config` / `local_config`: each read and validated against
      `project-config.schema.json`, plus the requirements one-of check;
    - `merged`: local deep-merged over shared;
    - `workspaces_dir`, `dashboards_dir`, `default_workspace` (default `"main"`), `targets`,
      `requirements`, and `run_config_layers()`, which returns `[shared.config, local.config]`;
    - `manifest()`, which returns the parsed `manifest.json` or `None`;
    - `resolve()` and `relative_or_absolute()`.
  - Paths are not required to exist here.
- [ ] T011 Change `loops/shared/devloops/config.py`:
  - `load_effective(defaults_path, workspace_config_path, cli_overrides, project_layers=())`
    merges in this order: `defaults < project_layers[0] < project_layers[1] < workspace
    config.json/--config < cli` (research P-4).
  - `DEFAULTS_PATH` comes from the kit: `kit.Kit.resolve().path("shared", "config",
    "defaults.json")`.
  - `resolve_for_run` passes `project_layers` through.
  - Add `file_sha256(path)`, which returns a hex digest or `None` when the file is missing.
- [ ] T012 Change `loops/shared/devloops/workspace.py`:
  - `resolve_path(name_or_path, project)`: a bare name goes to `<project.workspaces_dir>/<name>`.
  - `open_workspace(name_or_path, project, kit, create)`: its reserved check uses
    `kit.reserved + [<project>/.devloops]`, but allows `<project>/.devloops/workspaces/…`.
  - `Workspace(path, project, kit, data)` keeps `repo_root` as a read-only alias of
    `project.root` until Phase 2 ends, for callers not yet converted.
  - Add `check_target(path, project, kit, workspace_path, other_targets)`, which returns the real
    path or raises `input_error("target-unwritable", …)`. It rejects overlap with `kit.reserved`,
    `<project>/.devloops`, the workspace, and the other targets (FR-014). `set_target` calls it.
- [ ] T013 Replace `repo_root` path building with `Kit`:
  - `loops/shared/devloops/engine.py`: `load_loop_def(kit, loop)`; `Engine(loop, workspace,
    options, kit=None, project=None, env=None)`, where `kit` defaults to `Kit.resolve()` and
    `project` defaults to `workspace.project`; and `_workspace_config_path`.
  - `loops/shared/devloops/claude.py`: `ClaudeRunner(kit, loop, …)`, `compose_prompt`, and
    `settings()` (the hook path is `kit.path("shared", "hooks", "guard_writes.py")`).
  - `loops/shared/devloops/render.py`: `render_all(…, kit, …)`, with the `task.md` template from
    the kit.
  - `loops/shared/devloops/boundary.py`: the snapshot manifest roots are `kit.reserved`.
  - `loops/shared/devloops/orchestrator.py`: `Orchestrator(ws, options, kit=None, env=None)`.
  - `loops/shared/devloops/dashboard.py`: only if it reads kit files.

  Pass the project's `run_config_layers()` into `config.load_effective` / `resolve_for_run` in
  `engine.py`.
- [ ] T014 Change `loops/shared/devloops/cli.py`:
  - `main(argv=None, kit=None, project=None, env=None)` resolves `kit` (`Kit.resolve()`) and,
    for every command except `init` and `check`, `project.find(os.getcwd(), env)`. An error exits
    2 with the FR-008 message.
  - `--workspace` is no longer `required`. It defaults to `project.default_workspace`.
  - Add `_version_warnings(project, kit)`. When the manifest exists and its `devloops_version`
    differs from `kit.version`, it returns the warning text from contracts/cli.md. The text goes to
    stderr in text mode and into a `warnings` array in `--json` output (FR-029).
  - Remove `_repo_root()`. `bin/devloops` keeps calling `cli.main(sys.argv[1:])`.
- [ ] T015 Update every test that passes `repo_root=` to `Engine`, `Orchestrator`,
  `open_workspace`, `ClaudeRunner`, `render_all`, or `cli.main` (find them with `grep -rn
  "repo_root" loops/shared/tests`), so they pass a `Kit` and a `Project` built from the `TempEnv`
  root instead. Keep `loops/shared/tests/stub_loop.py` working.
- [ ] T016 Run `python3 -m unittest discover -s loops/shared/tests` and fix failures until all 001
  tests, plus `test_kit` and `test_project`, pass. **Checkpoint**: there is no behavior change for
  existing workspaces.

---

## Phase 3: User Story 1 - Install once and initialize a project (Priority: P1) 🎯 MVP

**Goal**: `devloops init` sets up any directory as a devloops project. It writes the
configuration, manifest, prompt README, seven skills, and the ignore block, never overwrites
anything, and can ask for the targets and requirements.

**Independent Test**: In an empty temporary directory, `bin/devloops init --no-prompt`:
- creates exactly the files in contracts/project-layout.md, and nothing else;
- a second run changes nothing;
- a conflicting file means nothing is written (quickstart §1, rows 1–3).

### Tests for User Story 1 ⚠️

- [ ] T017 [P] [US1] Write `loops/shared/tests/test_init.py`, covering:
  - **Fresh `init --no-prompt --json`**: the set of all files under the directory afterwards is
    exactly:
    - `.devloops/devloops.json`;
    - `.devloops/manifest.json`;
    - `.devloops/prompts/README.md`;
    - `.claude/skills/devloops-{run,approve,replan,retry,status,orchestrate,dashboard}/SKILL.md`;
    - `.gitignore`.

    Also: `devloops.json` has `targets` `backend`/`frontend` and `workspace: "main"`; the manifest
    lists every installed file, but not `devloops.json`, with correct sha256s; and the JSON output
    matches contracts/cli.md (SC-003).
  - **Second `init`**: exit 0, the "already initialized" message, and no file modification times
    changed (FR-006).
  - **Conflicts**: an existing, different `.claude/skills/devloops-run/SKILL.md` gives exit 30
    with `init-conflict` listing it, and no file is created. An existing, identical file is adopted
    into the manifest (FR-005).
  - **`.gitignore`**:
    - the block has the marker comments and the three lines;
    - `--track-workspaces` and `--track-dashboards` drop their lines;
    - an existing `.gitignore` is appended, not rewritten;
    - the block is not added twice.
  - **Bad target**: `--backend-target .devloops/x` and `--frontend-target` equal to the backend
    target both give exit 30 `target-unwritable`, with nothing written (FR-007b).
  - **Interactive**, using `pty.fork()` to run `bin/devloops init` with a terminal:
    - accepting the defaults writes `backend`/`frontend`;
    - an invalid backend answer is re-asked;
    - with `.specify/feature.json` naming an existing folder, the requirements default is
      `{"speckit_feature": "active"}`.
  - **`--no-prompt` with no requirements**: the output says how to set them, and
    `devloops.json` has `requirements: null`.
  - **Next steps**: the output names `devloops check` and the permission rule `Bash(<command> *)`.
- [ ] T018 [P] [US1] Write `loops/shared/tests/test_repo_skills.py`:
  - this repository's `.claude/skills/devloops-*/SKILL.md` are byte-identical to what
    `initcmd.render_skills(kit, project_root=<repo>)` produces (FR-022);
  - no `.claude/skills/loops-*` directory remains;
  - `.devloops/manifest.json` lists them.

### Implementation for User Story 1

- [ ] T019 [P] [US1] Create the seven skill templates
  `loops/shared/skills/devloops-{run,approve,replan,retry,status,orchestrate,dashboard}/SKILL.md`,
  exactly per contracts/skills.md:
  - **Frontmatter**: `name`, `description`, `argument-hint`, `user-invocable: true`,
    `allowed-tools: Bash({{DEVLOOPS}} *)`.
  - **Body**: one command, `{{DEVLOOPS}} <cmd> $ARGUMENTS --json`, followed by the summary
    instructions and the exit-code explanations (10/20/30/40/50, as in `loops/README.md`).
  - **Rules**: no loop logic, and no second command.
- [ ] T020 [P] [US1] Create `loops/shared/project/prompts/README.md`, the file `init` installs as
  `.devloops/prompts/README.md`. It explains the override paths from contracts/project-layout.md
  ("Prompt override paths"), that overrides apply from the next start and are recorded, and that
  other files are ignored.
- [ ] T021 [US1] Implement `loops/shared/devloops/initcmd.py` (research P-12, data-model
  "Install manifest"):
  - `render_skills(kit, project_root)` returns `{rel_path: text}`, with `{{DEVLOOPS}}` replaced by
    `kit.command_for(project_root)`.
  - `installed_files(kit, project_root)` returns `{rel_path: bytes}` for the skills and
    `.devloops/prompts/README.md`.
  - `default_project_config(targets, requirements)` builds the `devloops.json` dict:
    `schema_version`, `workspace: "main"`, `workspaces_dir`, `dashboards_dir`, `targets` (stored
    relative), `requirements`, and `config: {}`.
  - `init(project_root, kit, opts) -> result dict`:
    1. **Already initialized**: if `.devloops/devloops.json` exists and no `--upgrade` or
       `--allow-skills` was given, return the "already initialized" result.
    2. **Targets**: validate them with `workspace.check_target` (the project not yet saved).
    3. **Conflicts**: compute them (an existing file with different content); any conflict raises
       `input_error("init-conflict", …)` with the paths, before any write.
    4. **Write**: the files, then `devloops.json`, then `manifest.json` (`schema_version`,
       `devloops_version`, `kit_mode`, `command`, `installed_at`, `upgraded_at: null`,
       `ignore_rules`, `files`).
    5. **`.gitignore`**: append the marked block (contracts/project-layout.md) unless the marker
       is already present.
    6. **Result**: `created`, `changed`, `permission_rule`, `next`, and `message`.
- [ ] T022 [US1] Add the interactive questions to `loops/shared/devloops/initcmd.py` (research
  P-13):
  - **When**: `ask_missing(opts, project_root, kit, stdin, stdout)` runs only when
    `stdin.isatty() and stdout.isatty() and not opts.no_prompt`.
  - **Questions**:
    - "Backend target [backend]: "
    - "Frontend target [frontend]: "
    - "Requirements (file, spec-kit feature dir, or 'active') [<default>]: "
  - **Requirements default**: `active` when `.specify/feature.json` names an existing directory,
    otherwise blank.
  - **Re-asking**: an answer that fails `check_target`, or a requirements path that doesn't exist,
    prints the reason and asks again.
  - **Mapping answers**: a directory containing `spec.md`, or `active`, maps to
    `{"speckit_feature": …}`; a file maps to `{"path": …}`.
- [ ] T023 [US1] Add the `init [DIR]` subcommand to `loops/shared/devloops/cli.py`:
  - **Options**: `--backend-target`, `--frontend-target`, `--requirements`,
    `--speckit-feature [DIR]` (`nargs="?"`, `const="active"`), `--no-prompt`,
    `--track-workspaces`, `--track-dashboards`, `--json`.
  - **No project needed**.
  - **Text output**: lists the created and changed files, the permission rule, and the next
    command.
  - **`--json`**: per contracts/cli.md.
  - **Exit codes**: 0 / 30 / 2.
- [ ] T024 [US1] Migrate this repository (research P-17):
  1. Run `bin/devloops init --no-prompt --track-workspaces` at the repository root.
  2. Edit `.devloops/devloops.json`: set `workspaces_dir` to `"workspaces"`, and `targets` to
     `null`.
  3. Delete `.claude/skills/loops-backend-dev/`, `loops-frontend-dev/`, and `loops-orchestrate/`.
  4. Keep the existing `.gitignore` rules.

  Check that `bin/devloops status --workspace smoke` still works.
- [ ] T025 [US1] Run the US1 tests and the full suite. Then run `bin/devloops init --no-prompt` in
  a scratch directory and inspect the files by hand.

**Checkpoint**: US1 is independently usable. A project can be set up, and its skills call devloops.

---

## Phase 4: User Story 2 - Run the loops in a project with its own defaults (Priority: P1)

**Goal**: `run` and `orchestrate` need no path flags in an initialized project. The shared and
local configuration layer correctly. Paths survive moving the project. `status` reports drift.
One setting shows the browser.

**Independent Test**:
1. In a `TempEnv` project with `targets` and `requirements` configured, run `bin/devloops
   orchestrate --json` from a subfolder with the fake Claude.
2. Confirm the workspace is `.devloops/workspaces/main`.
3. Confirm the code is written only into the targets, and that no path flags were used (quickstart
   §1, rows 4–10).

### Tests for User Story 2 ⚠️

- [ ] T026 [P] [US2] Write `loops/shared/tests/test_project_runs.py`, covering:
  - **Defaults from the configuration**: `orchestrate` from `<project>/sub/dir` with no flags
    reaches exit 10. The workspace is `<project>/.devloops/workspaces/main`. `workspace.json`
    stores the targets as `backend`/`frontend` (relative) and the requirements path as relative
    (SC-002, FR-013).
  - **Precedence**: `max_trials` set to 5 in `devloops.json`, 4 in `devloops.local.json`, and 3
    via `--config` gives 3; with `--max-trials 2`, it gives 2. Without the `--config` and flag
    layers, the local value wins over the shared one. `run.json` `effective_config` records each
    winner (FR-010).
  - **Drift**: editing `devloops.json` after the first run makes `status --json` show
    `config_drift: ["max_trials"]`, and the next `run` still uses the frozen value (FR-015).
  - **Moved project**: copy the project with `shutil.copytree` to a new path, then `run`. The run
    resumes, and the targets resolve under the new root (FR-013).
  - **No project**: a command outside any project gives exit 2, with `devloops init` in stderr
    (FR-008).
  - **Bad targets**: a target `.devloops/x` or the kit's `loops/` gives exit 30
    `target-unwritable` (FR-014).
  - **Flags win**: `--workspace other` and `--target` flags override the configuration.
- [ ] T027 [P] [US2] Extend `loops/shared/tests/test_config.py` for research P-15:
  - `config.mcp_command(cfg)` gives `["npx", "@playwright/mcp@latest", "--headless"]` by default;
  - with `headless: false` it drops `--headless`;
  - with `executable_path: "/usr/bin/chromium"` it appends `--executable-path /usr/bin/chromium`;
  - an explicit `mcp_command` list is returned unchanged;
  - a frozen 001 configuration with an explicit list behaves as before.

### Implementation for User Story 2

- [ ] T028 [US2] In `loops/shared/devloops/cli.py` and `loops/shared/devloops/orchestrator.py`,
  default the `run`/`orchestrate` inputs from the project, with command-line flags winning:
  - `--target` from `project.targets[loop]`;
  - `--backend-target` / `--frontend-target` from `project.targets`;
  - `--requirements` / `--story-file` from `project.requirements` (the spec-kit form is wired in
    T050);
  - `--workspace` from `project.default_workspace`.

  Resolve every relative value with `project.resolve()`.
- [ ] T029 [US2] In `loops/shared/devloops/workspace.py`, `Workspace.set_target` and
  `attach_requirements` store paths with `project.relative_or_absolute()`. Readers
  (`Workspace.target(loop)`, `requirements_path()`, and the orchestrator's
  `_requirements_selection`) resolve relative values against the current `project.root`. Absolute
  values from old workspaces are used unchanged (FR-013, FR-033).
- [ ] T030 [US2] Implement drift reporting (research P-5):
  - **Recording**: when `engine.py` freezes the configuration, it also stores `config_sources:
    {"devloops.json": sha|null, "devloops.local.json": sha|null, "workspace": sha|null}` in
    `run.json`.
  - **Schema**: add the optional `config_sources` object to `run-state.schema.json`, in both
    copies.
  - **Comparing**: add `config.drift(frozen, project, workspace_config_path, defaults_path)`. It
    recomputes the effective configuration without command-line overrides and returns the changed
    dotted keys.
  - **Reporting**: `engine.status_object` adds `config_drift`, and the `status` text prints it
    when not empty.
- [ ] T031 [US2] Implement the visible-browser settings (research P-15, FR-017):
  - **Defaults**: in `loops/shared/config/defaults.json`, `playwright` becomes `{"headless":
    true, "executable_path": null, "mcp_command": null}`.
  - **Schema**: `config.schema.json` (both copies) gains `headless` (boolean),
    `executable_path` (string or null), and `mcp_command` (array or null).
  - **Derived command**: add `config.mcp_command(cfg)`, and use it wherever the MCP command is
    read: `preflight.check_tools`, and the MCP config written for `validate-ui` in
    `engine.py`/`validators/playwright.py`.
  - **Missing display**: when `headless` is false and the MCP server fails to start, the
    service-error message adds "no display available (playwright.headless is false)".
- [ ] T032 [US2] Run the US2 tests and the full suite.

**Checkpoint**: US1 and US2 together let a developer set up a project and run both loops with no
path flags.

---

## Phase 5: User Story 2 (continued) - Full dashboard with conversations (Priority: P1)

**Goal**: Every Claude call's conversation is copied, redacted, into the workspace. A
self-contained, timestamped full dashboard embedding every artifact and conversation is written
when a run ends, and by `devloops dashboard` (clarifications 1, 6, 7, 8; FR-035 to FR-042).

**Independent Test**:
1. Run the stub loop with the fake Claude, a fake `CLAUDE_CONFIG_DIR`, and a configured secret.
2. At `completed`, a new file appears under `.devloops/dashboards/<ws>/`.
3. Copied alone to another directory, it shows every evidence file and conversation, has no
   network references, and contains the secret 0 times (SC-009, SC-010).

### Tests for the full dashboard ⚠️

- [ ] T033 [P] [US2] Write `loops/shared/tests/test_conversations.py`:
  - **Copying**: after a stub run, each invocation record has `conversation: "copied"` and
    `conversation_path: "state/conversations/<seq>-<step>.jsonl"`. The file equals the fake
    transcript, with the configured secret replaced by `***`.
  - **Long paths**: a scenario with `transcript_dir` (simulating truncated long paths) is still
    found, by the `projects/*/<session>.jsonl` fallback.
  - **Missing transcript**: `"transcript": false` gives `conversation: "unavailable"` and
    `conversation_reason: "not-found"`, and the run is unaffected (FR-042).
- [ ] T034 [P] [US2] Write `loops/shared/tests/test_full_dashboard.py`:
  - **When it is written**: none at `awaiting-approval` (exit 10). Exactly one new file at
    `completed`. Another new file after `stopped-on-failure` (FR-039).
  - **Naming**: two generations in the same second give `<ts>.html` and `<ts>-2.html`, and
    neither replaces the other (FR-036).
  - **Embedded content**:
    - a PNG evidence file appears as `data:image/png;base64,`;
    - `validation.json`, `checks.json`, `plan.json`, `progress.md`, `outputs/*`, and every
      `state/prompts/*.md` appear, escaped;
    - each conversation shows its `tool_use` name and its `tool_result`;
    - the unknown record type is shown as raw JSON (FR-035, FR-040).
  - **Missing files**: a deleted evidence file shows `missing: <path>` (FR-037).
  - **Self-contained**: no `src=`/`href=` to `http(s):` or `//`, exactly one `<script`, model text
    escaped, the header notice present, and the configured secret appears 0 times (FR-041,
    SC-010).
  - **The `dashboard` command**: `dashboard --json` returns `full_dashboard.path`, `bytes`, and
    `largest` (up to five items). `dashboard --light` writes no full dashboard.
  - **Failures**: a directory in place of the dashboards directory gives a warning, with the exit
    code unchanged.
  - **Links and status**: the lightweight `dashboard.html` links each full dashboard, newest
    first (FR-036a), and `status --json` has `full_dashboards.count`.

### Implementation for the full dashboard

- [ ] T035 [US2] Copy the conversations in `loops/shared/devloops/claude.py` (research P-9):
  - **When**: after each call (including failed ones, but not on a kill of the driver),
    `_copy_conversation(seq, step, session_id, cwd)`.
  - **Finding the transcript**:
    - it looks in `<CLAUDE_CONFIG_DIR or ~/.claude>/projects/<re.sub('[^A-Za-z0-9]', '-',
      cwd)>/<session_id>.jsonl`;
    - otherwise it globs `projects/*/<session_id>.jsonl`.
  - **Writing**: it redacts each line, writes `state/conversations/<seq:04d>-<step>.jsonl`
    atomically, and sets `conversation` / `conversation_path` / `conversation_reason` on the
    record.
  - **Schema**: add those three optional fields to `invocation-record.schema.json`, in both
    copies.
- [ ] T036 [US2] Implement `loops/shared/devloops/fulldash.py`, per
  contracts/full-dashboard.md:
  - **Collecting**:
    - reuse `dashboard.collect(ws)` and `dashboard`'s CSS, theme script, and helpers (factor
      shared pieces out of `dashboard.py` where needed, without changing its output);
    - add `collect_artifacts(ws, loop)`, which lists every file in the content table with its
      milestone, trial, and step;
    - add `read_conversation(ws, loop, record)`, which reads the copy, or, for records made before
      this feature, the Claude Code history.
  - **Rendering**:
    - `embed(path)` returns a data URI for images and binary files, and escaped text otherwise;
    - `render_conversation(records)` follows the rendering table, collapsing tool results longer
      than 40 lines;
    - `render_full(data, ws)` builds the page.
  - **Writing**: `write(ws, project, trigger)` creates
    `<dashboards_dir>/<ws>/<YYYYMMDDTHHMMSSZ>[-n].html` with `O_CREAT|O_EXCL`, and returns `{path,
    bytes, largest, unavailable}`.
  - **Safety**: every embedded string passes through the loop's `Redactor`, built from its frozen
    `effective_config`.
- [ ] T037 [US2] Wire the full dashboard in `loops/shared/devloops/cli.py` and
  `loops/shared/devloops/dashboard.py`:
  - **After a final status**: add `_write_full_dashboard(ws, project, announce)`, called in the
    `finally` of `run`/`approve`/`replan`/`retry` when the loop's status is final (`completed`,
    `stopped-on-failure`, `stopped-on-input-error`, `stopped-on-service-error`), and once at the
    end of `orchestrate`. A failure warns: "could not write the full dashboard".
  - **Output**: print `full dashboard: <path> (<size>)`. `--json` adds `full_dashboard`.
  - **The `dashboard` command**: generates a full dashboard by default, and `--light` gives the
    001 behavior.
  - **Lightweight page**: `dashboard.py` lists the full dashboards in a "Full dashboards" section,
    newest first, with relative links.
  - **Status**: `status_object` adds `full_dashboards: {count, bytes, latest}`.
- [ ] T038 [US2] Run the full-dashboard tests and the full suite. Open one generated full
  dashboard in a browser from a copy in another directory, and check it visually: the
  conversation layout, image thumbnails, and dark mode.

**Checkpoint**: Every run end leaves a shareable full dashboard.

---

## Phase 6: User Story 3 - Check that the environment is ready (Priority: P2)

**Goal**: `devloops check` reports every prerequisite with a fix, and exits non-zero when one that
is needed is missing.

**Independent Test**: With each tool hidden from `PATH` in turn (and a fake `claude` reporting an
old version), `check` names the item and its fix, and exits 30 (SC-005).

- [ ] T039 [P] [US3] Write `loops/shared/tests/test_check.py`. It builds a `PATH` of stub
  executables in a temporary directory: `claude` printing `2.1.283 (Claude Code)`, `curl`, `npx`,
  `git`, and `google-chrome`. Cases:
  - **All present**: exit 0, every item `ready`.
  - **Each missing in turn** (`claude`, `curl`, `npx`, browser): exit 30, with that item
    `missing` and a non-empty `fix`.
  - **Old Claude Code**: `claude` printing `2.1.100` is `missing`, with "update" in the fix.
  - **git**: missing git is `ready`-irrelevant when `commit_per_milestone` is false, and `missing`
    when it is true.
  - **Display**: `headless: false` in `devloops.local.json` with no `DISPLAY`/`WAYLAND_DISPLAY`
    on Linux gives a `display` warning, with exit still 0.
  - **Shared visible browser**: `headless: false` in the shared `devloops.json` gives the
    `shared-visible-browser` warning.
  - **Outside a project**: `check` works and reports `project: null`.
  - **Output shape**: the `--json` shape matches contracts/cli.md.
- [ ] T040 [US3] Implement `loops/shared/devloops/checkcmd.py` (research P-14):
  - `run_checks(project_or_none, kit, env)` returns `{ready, project, items}`, with the items in
    the order of the research table.
  - The browser check:
    - with `executable_path` set, that path must exist and be executable;
    - otherwise it looks for `google-chrome`, `google-chrome-stable`, or `chrome` on `PATH`,
      `/opt/google/chrome/chrome`, and
      `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`.
  - Add `MIN_CLAUDE_VERSION = (2, 1, 283)` and `parse_version(text)` to
    `loops/shared/devloops/preflight.py`.
- [ ] T041 [US3] Add the `check [--json]` subcommand to `loops/shared/devloops/cli.py`:
  - it uses the project when one is found, and does not require one;
  - the text output follows contracts/cli.md;
  - it exits 0 or 30.

**Checkpoint**: `check` catches T076's setup failures before any paid call.

---

## Phase 7: User Story 4 - Drive the loops from Claude Code (Priority: P2)

**Goal**: The skills are verified thin, and `init --allow-skills` adds the permission rule on
request (clarification Q4).

**Independent Test**: Every installed skill has exactly one command, the unchanged arguments, and
`allowed-tools`. `init --allow-skills` adds one rule and keeps the existing settings (quickstart
§1, the skills rows).

- [ ] T042 [P] [US4] Write `loops/shared/tests/test_skills.py`:
  - **Each template** in `loops/shared/skills/`:
    - contains exactly one line matching `{{DEVLOOPS}} <cmd> $ARGUMENTS --json`;
    - has `allowed-tools: Bash({{DEVLOOPS}} *)`;
    - has `user-invocable: true`;
    - names the command in the table of contracts/skills.md;
    - contains no other `{{DEVLOOPS}}` command (FR-021).
  - **`--allow-skills`**:
    - on a fresh `init`, it creates `.claude/settings.json` with `permissions.allow:
      ["Bash(bin/devloops *)"]`;
    - on existing settings with other keys and allow rules, it keeps them, in order, and adds the
      rule once;
    - a second run adds nothing;
    - invalid JSON in the settings file gives exit 30 `settings-unreadable`, with the file
      unchanged and the rule printed;
    - it works on an already-initialized project (FR-022a, FR-022b).
- [ ] T043 [US4] Add `allow_skills(project_root, command)` to
  `loops/shared/devloops/initcmd.py`:
  - **Rule**: `Bash(<command> *)`.
  - **Merging**: read `.claude/settings.json` (or `{}` if absent), append the rule to
    `permissions.allow` if missing, and write atomically with `indent=2`. Report `changed`.
  - **Invalid settings**: raise `input_error("settings-unreadable", …)` without writing.

  `init` always includes `permission_rule` in its result, and its text output prints "To let
  Claude Code run devloops outside the skills without asking, run: devloops init --allow-skills".
- [ ] T044 [US4] Add `--allow-skills` to the `init` subcommand in
  `loops/shared/devloops/cli.py`. On an already-initialized project, it runs only
  `allow_skills()`, and nothing else is reinstalled.

**Checkpoint**: The skills run without approval prompts, and the settings change only on request.

---

## Phase 8: User Story 5 - Use a spec-kit feature as the requirements (Priority: P2)

**Goal**: A spec-kit feature folder (or the active one) is the input. `tasks.md` guides planning,
with checked coverage. `US<n>` selects a story.

**Independent Test**: With the spec-kit fixture and `--story-id US2`, under the fake Claude:
- the planning context carries the parsed phases;
- a plan that skips an in-scope task without a reason is invalid;
- the plan summary lists the planned and omitted tasks (quickstart §1, the spec-kit rows).

### Tests for User Story 5 ⚠️

- [ ] T045 [P] [US5] Create the fixture `loops/shared/tests/fixtures/speckit/`:
  - `specs/001-sample/spec.md`: `### User Story 1 - List notes (Priority: P1)` and `### User
    Story 2 - Add a note (Priority: P2)`, each with acceptance scenarios.
  - `specs/001-sample/plan.md`: names a stack.
  - `specs/001-sample/tasks.md`: `## Phase 1: Setup` with `T001`, `## Phase 2: Foundational` with
    `T002`, `## Phase 3: User Story 1 …` with `T003 [US1]` and `T004 [P] [US1]`, and
    `## Phase 4: User Story 2 …` with `T005 [US2]`, `- [x] T006 [US2]`, and a frontend task
    `T007 [US2] … in web/…`.
  - `.specify/feature.json`: `{"feature_directory": "specs/001-sample"}`.
- [ ] T046 [P] [US5] Write `loops/shared/tests/test_speckit.py`:
  - **Parser**: `speckit.parse_tasks()` returns the 4 phases with the IDs, story labels,
    `parallel`, and `done` (T006) flags. `speckit.stories()` finds US1 and US2.
  - **Resolving the feature**: `--speckit-feature` with no value resolves through
    `.specify/feature.json` and is recorded in `workspace.json` as `requirements.speckit` with the
    sha256 of `plan.md`/`tasks.md`.
  - **Missing input**: a folder without `spec.md` gives exit 30 `missing-input`. `--story-id US9`
    gives exit 30 `story-not-found` (FR-026).
  - **Planning context**: it contains `speckit.phases`, and the composed prompt contains the
    spec-kit section.
  - **Coverage check** (`plan.validate` with the speckit context):
    - leaving out an in-scope task without listing it is invalid;
    - listing it in `speckit_omitted` with a reason is valid;
    - an unknown ID in `speckit_tasks` is invalid;
    - milestones out of phase order are invalid;
    - in story mode `US2`, T003 and T004 are not required, and T001/T002 are allowed only when
      listed as needed (FR-023a, FR-023d).
  - **Changed inputs**: editing `tasks.md` after planning gives exit 30 `input-changed`, input
    `tasks` (FR-023c). Using a different active feature on resume gives `workspace-mismatch`.
  - **Plan summary**: `outputs/plan-summary.md` lists the planned spec-kit tasks, the omitted ones
    with their reasons, the devloops tasks with no spec-kit task, and T006 as "already marked done
    in tasks.md" (FR-023b).

### Implementation for User Story 5

- [ ] T047 [P] [US5] Implement `loops/shared/devloops/speckit.py` (research P-16, data-model
  "Spec-kit feature"):
  - `resolve_feature(arg, project)` handles `"active"` through `.specify/feature.json`
    `feature_directory`, or a directory. It returns `{feature_dir (relative), spec, plan_md|None,
    tasks_md|None}`, or raises `missing-input`.
  - `parse_tasks(text)`:
    - a phase is `^## Phase (\d+): (.+)$`;
    - a task is `^- \[( |x|X)\] (T\d{3,})\b(.*)$`;
    - `[P]` sets `parallel`, and `\[US(\d+)\]` sets `story`.
  - `stories(spec_text)` returns `{"US<n>": heading}` from
    `^#{2,4} User Story (\d+)\b`.
  - `context(feature, story_id)` returns the planning-context block.
- [ ] T048 [US5] Wire the spec-kit inputs in `loops/shared/devloops/inputs.py` and
  `loops/shared/devloops/engine.py`:
  - **Inputs**: `inputs.speckit_requirements(feature, story_id)` returns the 001 requirements dict
    (path = `spec.md`, mode `prd` or `prd-story`), plus a `speckit` block with the sha256s.
    `US<n>` is checked against `speckit.stories()`.
  - **Recording**: `Workspace.attach_requirements` records and compares `speckit.feature_dir`
    (`workspace-mismatch`), and the `plan`/`tasks` sha256s (`input-changed`, input
    `plan`/`tasks`).
  - **Planning context**: the engine adds `speckit: speckit.context(...)` to the plan and replan
    contexts.
- [ ] T049 [US5] Extend the plan:
  - **Schema**: `plan.schema.json`, in both copies, plus 001's `data-model.md`. Add the optional
    milestone `speckit_phase` (integer or null), task `speckit_tasks` (array of strings), and plan
    `speckit_omitted` (array of `{id, reason}` with `minLength` 1).
  - **Checks**: `loops/shared/devloops/plan.py` gets `validate_speckit(plan, speckit_ctx,
    story_id)`:
    - the in-scope IDs are every task (no story mode), or the story's tasks plus any unlabelled
      task the plan references;
    - each in-scope ID must be referenced by a task or listed as omitted with a reason;
    - each referenced ID must exist;
    - an unlabelled task referenced in story mode must appear in `speckit_omitted`-style
      reporting as "needed by <story>";
    - `speckit_phase` must be non-decreasing across milestones.

    It returns errors in the same form as the story-scope check, which makes the planning trial
    fail.
- [ ] T050 [US5] Update the prompts, the plan summary, and the options:
  - **Prompt**: add a "spec-kit feature" section to `loops/shared/prompts/steps/plan.md` (and
    `replan.md`). It says to follow the phases as milestones in order, put the spec-kit task IDs
    in `speckit_tasks`, list every in-scope task left out in `speckit_omitted` with a reason (for
    example "frontend task" for backend-dev), and not trust `done` marks.
  - **Plan summary**: `loops/shared/devloops/render.py` renders the plan summary's
    "spec-kit tasks" section: planned, omitted (with reasons), devloops tasks with no spec-kit
    task, and tasks already marked done.
  - **Options**: add `--speckit-feature [DIR]` (`nargs="?"`, `const="active"`) to `run` and
    `orchestrate` in `loops/shared/devloops/cli.py`, mutually exclusive with `--requirements` and
    `--story-file`. Default it from `project.requirements.speckit_feature`, and pass it through
    `loops/shared/devloops/orchestrator.py`.
- [ ] T051 [US5] Run the US5 tests and the full suite. Check that `test_no_app_specifics` still
  passes (the fixture lives under `tests/fixtures`).

**Checkpoint**: spec-kit decides what to build, and devloops builds and validates it, with any
differences visible at approval.

---

## Phase 9: User Story 6 - Upgrade devloops without losing local changes (Priority: P3)

**Goal**: `init --upgrade` updates the installed files that weren't changed, keeps the ones that
were, refuses downgrades, and every command warns on a version mismatch.

**Independent Test**:
1. `init`.
2. Change one skill and delete another.
3. Simulate a newer kit version.
4. Run `--upgrade`, then check each outcome and the manifest (SC-004).

- [ ] T052 [P] [US6] Write `loops/shared/tests/test_upgrade.py`. It uses a `Kit` over a temporary
  copy of `loops/` with a patched version string, and edits template files to simulate a new
  release. Cases:
  - an unchanged installed file is replaced with the new template;
  - a changed one is kept, a `<path>.devloops-new` holds the new version, and the result is
    `kept`;
  - a deleted one is reported as `deleted` and not re-created, and `--restore` re-creates it;
  - a template added to the kit is created;
  - a template removed from the kit is removed if unchanged, and kept and reported otherwise;
  - `devloops.json` is byte-identical before and after;
  - the manifest has the new `devloops_version`, `upgraded_at`, and fingerprints;
  - a manifest version `9.0.0` gives exit 30 `downgrade-refused` with nothing changed;
  - after an upgrade, the `.gitignore` block is not duplicated;
  - a `status --json` with a mismatched manifest version has the warning in `warnings` (FR-029).
- [ ] T053 [US6] Implement `upgrade(project_root, kit, restore)` in
  `loops/shared/devloops/initcmd.py`:
  - follow the state diagram in data-model "Install manifest";
  - compare versions with `tuple(int(p) for p in v.split("."))`;
  - re-render the skills with the current `kit.command_for(project_root)`;
  - write each `.devloops-new` file atomically;
  - return `{updated, kept, deleted, added, removed}`.
- [ ] T054 [US6] Add `--upgrade` and `--restore` to the `init` subcommand in
  `loops/shared/devloops/cli.py`, with the text and JSON output of contracts/cli.md.

**Checkpoint**: Projects can follow devloops releases safely.

---

## Phase 10: User Story 7 - Customize the loop prompts for one project (Priority: P3)

**Goal**: A file in `.devloops/prompts/` overrides the matching packaged prompt part. Each call
records its prompt sources. A change is recorded as an event and reported by `status`.

**Independent Test**:
1. Add `.devloops/prompts/steps/plan.md`.
2. Run the stub loop.
3. Check that the recorded prompt contains the override text, and that the invocation record names
   the override and its sha256.

- [ ] T055 [P] [US7] Write `loops/shared/tests/test_prompt_overrides.py`:
  - **Overrides apply**: an override of `steps/plan.md` appears in `state/prompts/0001-plan.md`,
    and the record's `prompt_sources` has `{part: "steps/plan.md", source: "override", path:
    ".devloops/prompts/steps/plan.md", sha256}`. The other parts are `packaged`.
  - **Every overridable part**: an override of `backend-dev/Loop-instructions.md` and one of
    `common.md` also apply.
  - **Unknown files**: `.devloops/prompts/steps/typo.md` is ignored, and listed in `status --json`
    `warnings`.
  - **Freezing**: `run.json` has `prompt_sources` after the first start.
  - **Changes**: editing the override, then `run`, records a `prompt-sources-changed` event naming
    `steps/plan.md`, and `status --json` shows `prompt_drift: ["steps/plan.md"]` (FR-030 to
    FR-032).
- [ ] T056 [US7] Implement the overrides:
  - **Composing**: in `loops/shared/devloops/claude.py`, `compose_prompt(step, context)` looks up
    each part in `<project>/.devloops/prompts/<part>` before the kit. It returns the prompt and
    `prompt_sources`, which `_record` stores.
  - **Freezing**: in `loops/shared/devloops/engine.py`, store `prompt_sources` (for every part
    the loop can use) in `run.json` when the configuration is frozen. On a later start, compare
    and record a `prompt-sources-changed` event.
  - **Event**: add `"prompt-sources-changed"` to `state.EVENT_TYPES`, and document it in
    `specs/001-reusable-dev-loops/data-model.md`.
  - **Schemas**: add the optional `prompt_sources` array to `invocation-record.schema.json` and
    `run-state.schema.json`, in both copies.
  - **Status**: `status_object` adds `prompt_drift` and the warning for ignored files.

**Checkpoint**: Every user story is implemented.

---

## Phase 11: Polish & Cross-Cutting Concerns

- [ ] T057 [P] Update `loops/README.md` (FR-034), describing only implemented behavior:
  - **Install**: `uv tool install git+<repo>` / `uv tool install .` / `-e .`, plus
    `bin/devloops` from a checkout.
  - **Quick start**: `devloops init` (its questions and flags) → `devloops check` → `devloops
    orchestrate`.
  - **Project**: the layout (contracts/project-layout.md), the configuration precedence
    (5 layers), and `devloops.local.json` for machine settings.
  - **Visible browser**: `headless` and `executable_path`.
  - **Overrides and spec-kit**: prompt overrides, and the spec-kit bridge (`--speckit-feature`,
    `US<n>`, what the plan summary shows).
  - **Full dashboards**: when they are written, what they contain, the review-before-sharing note,
    and that they accumulate.
  - **Skills and upgrades**: skills and `--allow-skills`, `init --upgrade`.
  - **Limits and migration**: the known limitations (no target at the project root; transcript
    format), and the note on migrating this repository.

  Update the command reference and the exit codes.
- [ ] T058 [P] Write `loops/shared/tests/test_packaging.py`, skipped unless `uv` is on `PATH` and
  `DEVLOOPS_TEST_PACKAGING=1`:
  1. Run `uv build --wheel` into a temporary directory. Check that the wheel lists the
     `devloops_kit/` assets (`shared/skills/devloops-run/SKILL.md`, `shared/prompts/common.md`,
     `shared/hooks/guard_writes.py`) and no `tests/`.
  2. Install it into a temporary venv. `devloops --version` prints 0.2.0.
  3. `devloops init --no-prompt` in a temporary directory renders `devloops` (not a path) in the
     skills, and its manifest has `kit_mode: "installed"`.
- [ ] T059 [P] Update `specs/001-reusable-dev-loops/contracts/workspace-layout.md` and
  `specs/001-reusable-dev-loops/contracts/cli.md`. Each gets a short "Changed by 002" note: the
  `state/conversations/` directory, the optional `--workspace`, the `dashboard` full/`--light`
  modes, and a link to `specs/002-devloops-init/contracts/`.
- [ ] T060 Run the full offline suite (quickstart §1) and fix it until it is green. Confirm that
  `git status loops/ bin/` is clean after the suite. Then run `/code-review` on the change set and
  apply the confirmed findings.
- [ ] T061 Run quickstart §2–5 with real Claude Code (SC-007), following only `loops/README.md`:
  install with `uv tool install .`, then `init` a fresh scratch project, `check`, a spec-kit
  feature through `orchestrate`, opening the copied full dashboard offline, the upgrade, and the
  visible browser. Record the outcomes, costs, defects, and README gaps in
  `specs/002-devloops-init/validation-results.md`, and fix the code or docs where they differ.

---

## Dependencies & Execution Order

### Phase dependencies

| Phase | Depends on |
|-------|------------|
| Setup (1) | nothing |
| Foundational (2) | Setup. It blocks every story |
| US1 (3) | Foundational |
| US2 (4) | Foundational. Uses `init` only in tests (it can write `devloops.json` directly), so it is independent of US1 |
| US2 full dashboard (5) | Phase 4's project paths (`dashboards_dir`) |
| US3 (6) | Foundational (it reads the project configuration) |
| US4 (7) | US1 (templates and `initcmd`) |
| US5 (8) | Phase 4 (project requirements defaults) |
| US6 (9) | US1 (manifest) |
| US7 (10) | Foundational |
| Polish (11) | Every story. T061 needs a logged-in Claude Code |

### Within phases

- **Setup**: T001 → T002. T004, T005, and T006 are independent. T006 must land before Phase 2's
  test runs.
- **Foundational**: T009 → T010 → T011/T012 → T013 → T014 → T015 → T016. T007 and T008 can be
  written first.
- **Within stories**: the tests are written first and must fail. Templates and fixtures come
  before the modules, the modules before the CLI wiring, and the CLI wiring before the story's
  suite run.

## Parallel Opportunities

| Where | Tasks that can run together |
|-------|-----------------------------|
| Setup | T003, T004, T005 |
| Foundational | T007, T008 (tests) while T009 is written |
| After Phase 2 | US1 (T017–T025), US2 (T026–T032), US3 (T039–T041), and US7 (T055–T056) touch mostly different modules; `cli.py` edits are separate functions, applied in sequence |
| US1 | T017, T018, T019, T020 |
| US2 | T026, T027; then T033, T034 |
| US5 | T045, T046, T047 |
| Polish | T057, T058, T059 |

## Parallel Example: User Story 1

```text
# After Phase 2, in parallel:
T017  loops/shared/tests/test_init.py
T018  loops/shared/tests/test_repo_skills.py
T019  loops/shared/skills/devloops-*/SKILL.md (7 templates)
T020  loops/shared/project/prompts/README.md
# Then in sequence:
T021 → T022 → T023 → T024 → T025
```

## Implementation Strategy

### MVP first

1. Phase 1 + Phase 2: the split into kit and project, with 001 fully green.
2. Phase 3 (US1): `devloops init`. **Stop and validate**: initialize a scratch project and inspect
   it.
3. Phase 4 (US2): run with project defaults. This is the outcome the developer asked for.

### Incremental delivery

| Step | Adds |
|------|------|
| MVP | Setup + Foundational + US1 + US2 (project defaults) |
| + full dashboard | Shareable record of every run with conversations (Phase 5) |
| + US3 | `check` before paid runs |
| + US4 | Approval-free skills, `--allow-skills` |
| + US5 | The spec-kit bridge |
| + US6 | Safe upgrades |
| + US7 | Prompt overrides |
| + Polish | README, packaging test, real-run validation (SC-007) |

### Traceability

| Requirement | Tasks |
|-------------|-------|
| FR-001, FR-002 | T001, T002, T009, T058 |
| FR-003–FR-007b | T017, T019–T024 |
| FR-008, FR-009 | T008, T009, T010, T014, T026 |
| FR-010, FR-011, FR-012 | T010, T011, T026, T028 |
| FR-013, FR-014 | T012, T026, T029 |
| FR-015, FR-016 | T008, T026, T030 |
| FR-017 | T027, T031 |
| FR-018, FR-019 | T039–T041 |
| FR-020–FR-022b | T018, T019, T024, T042–T044 |
| FR-023–FR-026 | T045–T051 |
| FR-027–FR-029 | T014, T052–T054 |
| FR-030–FR-032 | T020, T055, T056 |
| FR-033 | T006, T015, T016, T029, T060 |
| FR-034 | T057, T059 |
| FR-035–FR-042 | T005, T033–T038 |
| SC-001–SC-003 | T017, T026, T061 |
| SC-004 | T052 |
| SC-005 | T039 |
| SC-006 | T008, T026 |
| SC-007 | T061 |
| SC-008 | T016, T060 |
| SC-009, SC-010 | T034, T038, T061 |

## Notes

- A `[P]` task touches different files and does not depend on an incomplete task.
- The `[USn]` labels map to spec.md user stories 1–7. Phase 5's tasks are `[US2]` (acceptance
  scenario 7).
- Commit after each phase or logical group, using Conventional Commits.
- Never put application-specific content in `loops/`. `test_no_app_specifics` enforces this.
