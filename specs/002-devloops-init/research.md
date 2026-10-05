# Research: Devloops Project Setup

**Feature**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md) · **Date**: 2026-10-05

Each entry gives the decision, the reasons for it, and the alternatives considered. Entries are
numbered **P-n** so they don't clash with 001's R-n, which still apply.

Facts verified on this machine:
- Python 3.14.7, uv 0.12.19, setuptools 84.0.0, Claude Code 2.1.283;
- the packaging prototype in P-1 was built and installed from a wheel and editable;
- 001's T076 session transcripts were found as described in P-9.

Claude Code facts come from the official docs (permissions, sessions, skills), as noted inline.

---

## P-1 Packaging: one distribution, the code and the kit as two packages, no source move

**Decision**: Add a `pyproject.toml` at the repository root, with the setuptools build backend.
- **Packages**: two import packages, mapped onto the existing directories with no file moves:
  - `devloops`, from `loops/shared/devloops`, with `devloops.validators`;
  - `devloops_kit`, from `loops/`, as package data only:
    - `backend-dev/*`, `frontend-dev/*`, `orchestrator/*`;
    - `shared/{prompts,schemas,hooks,config}/**`;
    - the new `shared/skills/**`.

  Tests and fixtures are not shipped.
- **Command**: the console script `devloops = devloops.cli:entry`.
- **Installation**:
  - `uv tool install git+<repo-url>` (or `uv tool install .` from a checkout);
  - for development, `uv tool install -e .`;
  - `bin/devloops` keeps working from a checkout with nothing installed (FR-002).

**Rationale**:
- The prototype (`uv build --wheel`, then install into a fresh venv) produced a 50-file wheel. From
  the installed copy, `devloops_kit/shared/prompts/common.md` and the other files were found.
- An editable install resolved `devloops_kit` back to the checkout's `loops/`, so prompt edits
  apply without reinstalling.
- Keeping `loops/` where it is preserves 001's documented layout (001 FR-001 and FR-037,
  `contracts/workspace-layout.md`), so no 001 doc becomes wrong.
- The runtime stays standard-library only. setuptools is used only when building (Principle VII).

**Alternatives**:
- *Move everything under `src/devloops/`*: the cleanest packaging, but it rewrites every path in
  001's docs and tests for no user-visible gain.
- *hatchling*: equally fine, but setuptools' `package-dir` mapping covered the non-standard layout
  with no plugin.
- *A zipapp*: one file, but no console script on PATH and no standard upgrade path.
- *Publishing to PyPI*: out of scope (A-4).

## P-2 Kit root resolution

**Decision**: A new module `devloops/kit.py` exposes `Kit` with:
- `root`: the directory with `backend-dev/`, `frontend-dev/`, and `shared/`;
- `mode`: `"source"` or `"installed"`;
- `reserved`: the paths a target must not overlap;
- `command`: how skills invoke devloops (P-7).

Resolution:
- **Source**: if `<devloops package>/../../backend-dev/loop.json` exists, the root is
  `loops/` of the checkout, and `reserved` is that checkout's `loops/` and `bin/`.
- **Installed**: otherwise, the root is `devloops_kit.__path__[0]`, and `reserved` is both
  installed packages.

Every `os.path.join(repo_root, "loops", ...)` in `engine`, `claude`, `render`, `config`, and
`boundary` goes through `Kit`. `repo_root` is renamed and split into `kit` and `project` (P-3).

**Rationale**:
- One resolver serves both modes (FR-002) and gives the target guard its reserved list (FR-014).
- `devloops_kit` has no `__init__.py`, so `importlib.resources.files()` returns a
  `MultiplexedPath`. `__path__[0]` is the plain directory.

**Alternatives**: `importlib.resources.as_file()` for every read. It is correct for zipped
installs, but devloops also runs `hooks/guard_writes.py` by path, so a real directory is needed
anyway, and wheels install unzipped.

## P-3 Project root discovery

**Decision**: `project.find(start=cwd)` walks up from the current directory to the first directory
containing `.devloops/devloops.json`. The nearest project wins. `init` and `check` do not require a
project; every other command stops with exit 2 and "no devloops project found from <cwd>; run
`devloops init`" (FR-008).

Relative paths in project files resolve against the project root, which is the parent of
`.devloops/`.

**Rationale**:
- The search mirrors how git finds its repository, and is what the spec asks for (FR-008).
- Requiring `devloops.json`, not just `.devloops/`, avoids treating a half-deleted folder as a
  project.

**Alternatives**:
- *A `DEVLOOPS_PROJECT` environment variable*: kept as an override for tests and scripts, not as
  the main mechanism.
- *Stopping at the git top level*: wrong for projects that aren't under git.

## P-4 Project configuration shape and precedence

**Decision**: `.devloops/devloops.json` has project-level keys plus one `config` block. The
`config` block has exactly the shape of 001's run configuration (`config.schema.json`).
`.devloops/devloops.local.json` has the same shape and is deep-merged over it. The schema is in
[contracts/project-config.schema.json](./contracts/project-config.schema.json).

```json
{
  "schema_version": 1,
  "workspace": "main",
  "workspaces_dir": ".devloops/workspaces",
  "dashboards_dir": ".devloops/dashboards",
  "targets": { "backend-dev": "backend", "frontend-dev": "frontend" },
  "requirements": { "speckit_feature": "active" },
  "config": { "max_invocations_per_run": 60, "playwright": { "headless": true } }
}
```

The run configuration is resolved in this order, each level overriding the one before (FR-010):
1. packaged `shared/config/defaults.json`;
2. `devloops.json` `config`;
3. `devloops.local.json` `config`;
4. the workspace's `config.json` or `--config` (001);
5. command-line flags.

The result is frozen into `run.json` at the first run, as before (001 FR-062).

Project-level values (workspace, targets, requirements) follow the same order: local file over
shared file, and command-line flags over both.

`requirements` takes exactly one form:
- `{"path": "<file>"}`, with an optional `"story_file": true`;
- `{"speckit_feature": "<dir>"}`;
- `{"speckit_feature": "active"}`.

A story ID is per run, so it is not stored in the project configuration. FR-011's "story selection
mode" is the `story_file` flag.

**Rationale**:
- Nesting the run configuration under `config` reuses 001's schema and validator unchanged, and
  keeps the project-level keys from colliding with run keys.
- Validation is strict: unknown keys are rejected, with the file and the key named (FR-016),
  matching 001's `additionalProperties: false`.

**Alternatives**:
- *A flat file mixing both kinds of keys*: ambiguous (a top-level `backend` key already means the
  backend runtime in 001).
- *TOML*: friendlier to read, but the reader (`tomllib`) is only in Python 3.11+, and everything
  else in devloops is JSON.

## P-5 Configuration drift reporting

**Decision**: When the configuration is frozen, `run.json` also records `config_sources`, a sha256
for each of `devloops.json`, `devloops.local.json`, and the workspace config. It also records
`prompt_sources` (P-8).

`status` recomputes the effective configuration from the current files. It reports
`config_drift: [<dotted keys whose value would now differ>]` and `prompt_drift: [...]`. Nothing is
applied (FR-015).

**Rationale**: Reporting the keys, not just "a file changed", tells the developer whether the
change matters. A whitespace edit reports nothing.

**Alternatives**: Applying project changes on the next start. Rejected because 001 FR-062 freezes
the configuration for reproducibility.

## P-6 Targets, requirements, and workspace paths stored relative to the project

**Decision**:
- **Storage**: `workspace.json` stores a target, the requirements path, and the spec-kit paths
  relative to the project root when they are inside it, and absolute otherwise (FR-013).
- **Reading**: relative values are resolved against the current project root.
- **Old workspaces**: existing workspaces store absolute paths, which are still read as they are.
- **Workspace lookup**: a bare workspace name maps to `<workspaces_dir>/<name>`.

**Target guard** (FR-014): a target is rejected when it overlaps any of:
- `Kit.reserved`;
- `<project>/.devloops`;
- the workspace;
- the other loop's target.

Since `.devloops/` is inside the project root, **a target cannot be the project root itself**. The
README says to give each loop a subfolder, which orchestration needs anyway (two targets that don't
overlap).

**Rationale**: Paths stored relative to the project let a moved or cloned project resume (US2
scenario 6).

**Alternatives**: Allowing the project root as a target by excluding `.devloops/` from the audit.
Rejected for now: it breaks 001's "workspace not inside the target" rule, which the write guard
depends on. This is a known limitation, recorded in plan.md.

## P-7 Skills: rendered from kit templates, with `allowed-tools`

**Decision**:
- **Templates**: the kit ships seven skill templates under `loops/shared/skills/` (see
  [contracts/skills.md](./contracts/skills.md)): `devloops-run`, `devloops-approve`,
  `devloops-replan`, `devloops-retry`, `devloops-status`, `devloops-orchestrate`, and
  `devloops-dashboard`.
- **Rendering**: `init` writes each one to `.claude/skills/<name>/SKILL.md`, replacing
  `{{DEVLOOPS}}` with the command for this project:
  - `devloops` when installed;
  - when running from a source checkout, the path of `bin/devloops`: relative to the project
    root if the checkout is inside it, otherwise absolute.
- **Frontmatter**: each skill has `allowed-tools: Bash({{DEVLOOPS}} *)`. Claude Code docs: skill
  `allowed-tools` pre-approves those tools for the skill's turn.
- **This repository's own skills**: `.claude/skills/devloops-*` are produced by running `init` on
  this repository, which renders `bin/devloops` as the command. A test checks that they are
  identical to what `init` would render (FR-022). The old `loops-*` skills are removed (A-3).

**Rationale**:
- `allowed-tools` removes the approval prompt **inside** skill runs without touching settings,
  which is what clarification Q4 wanted by default.
- `--allow-skills` (P-12) remains for running devloops from Claude Code outside a skill.
- Skill names (lowercase letters and hyphens) fit Claude Code's naming rules.

**Alternatives**:
- *One skill per loop (`devloops-backend-dev`)*: seven skills already cover every command, and
  the loop is an argument.
- *Not rendering the command*: then the skills fail when devloops is not on PATH (source
  checkouts).

## P-8 Prompt overrides

**Decision**: When it builds a prompt, devloops looks up each part in
`<project>/.devloops/prompts/<relative path>` before the kit. The overridable parts are:
- `shared/prompts/common.md`, as `common.md`;
- `shared/prompts/steps/<step>.md`, as `steps/<step>.md`;
- `<loop>/Loop-instructions.md`, as `<loop>/Loop-instructions.md`.

Each invocation record gains:
- `prompt_sources: [{part, source: "packaged"|"override", path, sha256}]` (FR-031).

`run.json` records the `prompt_sources` that were in effect when the configuration was frozen.

Overrides are **not** frozen. A change applies from the next start. That start records a
`prompt-sources-changed` event naming the changed parts, and `status` reports `prompt_drift` until
the run ends (FR-032: "not silently").

**Rationale**:
- Freezing would mean copying every prompt into the workspace, and a developer who edits an
  override usually wants the next call to use it.
- Recording the change as an event and a fingerprint keeps traceability (Principle VIII).
- Milestones that are already done are never re-run, so their prompts never change.

**Alternatives**:
- *Freezing overrides like the configuration*: reproducible, but surprising for prompt tuning.
- *Merging or appending to the packaged prompts*: no clear semantics.

## P-9 Copying Claude Code conversations into the workspace

**Decision**:
- **Source**: after each call, devloops copies the call's transcript from
  `<claude config dir>/projects/<encoded cwd>/<session_id>.jsonl`, where:
  - the config dir is `CLAUDE_CONFIG_DIR`, or else `~/.claude`;
  - `<encoded cwd>` replaces every non-alphanumeric character of the call's working directory
    (the target) with `-`.
- **Fallback**: Claude Code truncates long paths and adds a hash, so if the file is not there,
  devloops searches `projects/*/<session_id>.jsonl`.
- **Destination**: `<loop>/state/conversations/<seq>-<step>.jsonl`, next to `state/prompts/`,
  with each line redacted (001 `Redactor`).
- **Record**: the invocation record gains `conversation_path`, or `conversation: "unavailable"`
  when the transcript can't be found. That happens for an interrupted call or a cleaned-up history.

**Rationale**:
- Docs: transcripts are stored per working directory, `CLAUDE_CONFIG_DIR` moves the base, and
  **transcripts are deleted after `cleanupPeriodDays`, 30 by default**. So copying when the call
  ends is the only way to keep the full dashboard complete later (FR-042).
- Verified on this machine: T076's session `88ee6fa2…` is at
  `~/.claude/projects/-tmp-claude-1000--data-space-…-t076-smoke-backend/88ee6fa2-….jsonl`, about
  140 KB.
- Each loop's transcripts total roughly 0.4 to 0.9 MB, which is acceptable in an ignored workspace.

**Risk**: The transcript format is internal and undocumented. The copy is byte-for-byte (after
redaction), and the renderer (P-11) is defensive: it knows the `user` and `assistant` messages and
their content blocks (`text`, `thinking`, `tool_use`, `tool_result`). It shows any other record
type as collapsed raw JSON instead of failing. A format change can make the dashboard less pretty,
but never wrong or broken.

**Alternatives**:
- *`--output-format stream-json` for every step*: this captures the conversation as it happens. But
  it changes how results are parsed for every step (only `validate-ui` streams today), and it
  still lacks some records.
- *`/export`*: interactive only.

## P-10 Full dashboard: format, embedding, naming

**Decision**: A new module `devloops/fulldash.py` reuses `dashboard.collect()` and its page
styles. It adds an **Artifacts** section per loop and a **Conversations** section per call. The
embedding and naming rules are in [contracts/full-dashboard.md](./contracts/full-dashboard.md):
- Images are embedded as base64 `data:` URIs, and other binary files as `data:` download links.
- Text and JSON files are inlined, HTML-escaped, inside collapsed `<details>` elements.
- Every embedded string goes through the `Redactor` built from that loop's frozen configuration
  (FR-041).
- The file is written to `<dashboards_dir>/<workspace>/<YYYYMMDDTHHMMSSZ>.html`, with `-2`, `-3` …
  appended on a collision. It is opened with `O_EXCL`, so it never overwrites (FR-036).
- The page header shows "Contains full Claude Code conversations — review before sharing" (FR-041).
- Missing files are shown with their path, marked missing (FR-037). The command prints the path,
  the size, and the five largest embedded files.

**Rationale**:
- The page needs no JavaScript beyond 001's theme toggle. `<details>` keeps a large page usable,
  and data URIs keep it one file (SC-009).
- Data URIs roughly add a third to binary sizes. T076-sized workspaces stay well under 10 MB.

**Alternatives**:
- *A zip or MHTML bundle*: browsers can't open a zip directly, and MHTML support is inconsistent.
- *JSON blobs rendered by JavaScript*: more code, and 001's no-network, one-inline-script property
  is harder to test.

## P-11 When the full dashboard is generated

**Decision**: The command layer adds `_write_full_dashboard(ws)`, called by `run`, `approve`,
`replan`, `retry`, and `orchestrate` when the command's final status is `completed`,
`stopped-on-failure`, `stopped-on-input-error`, or `stopped-on-service-error`.
- `orchestrate` generates it once, at the end, covering both loops.
- It is not generated at `awaiting-approval` or on a refused lock (exit 40).
- A failure prints a warning and never changes the exit code (FR-039).
- `devloops dashboard` always generates a full one. `devloops dashboard --light` only refreshes the
  per-command page.
- The per-command page lists the full dashboards, newest first (FR-036a).

**Rationale**: This follows clarification Q6 directly. Hooking in at the command layer matches how
001's lightweight dashboard is written.

## P-12 `init`, `--upgrade`, and the manifest

**Decision**:
- **Installed files**: `init` installs `.devloops/devloops.json`,
  `.devloops/prompts/README.md`, and the seven skills.
- **Manifest**: `.devloops/manifest.json` records:
  - `devloops_version`;
  - `kit_mode`;
  - `command`;
  - the date of the first install and of the last upgrade;
  - `files: {<project-relative path>: sha256}`.

  `devloops.json` is **not** in `files`: it belongs to the developer from the moment it is written
  (FR-028).
- **Ignore rules**: one block is appended to the project `.gitignore`, under a marker comment, with
  the workspaces directory, the dashboards directory, and `devloops.local.json`. `--track-workspaces`
  and `--track-dashboards` leave the first two out. If the marker is already there, the block is not
  added again.
- **Conflicts**: before writing, `init` checks every destination. A path that exists with
  different content and is not in the manifest is a conflict. Any conflict means nothing is written
  and every conflicting path is listed (exit 30, `init-conflict`). An existing file with identical
  content is adopted into the manifest.
- **Upgrade**: `init --upgrade` compares each kit file with the manifest:
  - **Unchanged on disk** (its fingerprint matches the manifest): replaced.
  - **Changed on disk**: kept, with the new version written as `<path>.devloops-new`, then
    reported.
  - **Missing on disk**: reported, and restored only with `--restore`.
  - **New in this version**: added, under the same conflict rule.
  - **Removed from the kit**: deleted if unchanged, otherwise kept and reported.

  A manifest version newer than the running devloops is refused with no changes (FR-028).
  Versions are compared as tuples of integers.
- **Version warning**: every other command compares `devloops.__version__` with the manifest. On a
  difference, it prints `devloops: warning: …` to stderr and adds a `warnings` entry in `--json`
  output (FR-029).
- **`--allow-skills`**: merges `{"permissions": {"allow": ["Bash(<command> *)"]}}` into
  `<project>/.claude/settings.json`:
  - it keeps every other key and the order of the existing entries;
  - it skips a rule that is already present;
  - it creates the file if absent;
  - it leaves a settings file that isn't valid JSON untouched, and prints the rule instead.

  Docs: `Bash(devloops *)` is the current form of the rule, equivalent to the legacy
  `Bash(devloops:*)`.

**Rationale**:
- This mirrors spec-kit's install-and-upgrade behavior.
- Fingerprints are the only way to tell "the developer changed it" from "an older version" without
  keeping every past release.

**Alternatives**: three-way merge on upgrade. Rejected as too complex (Principle X); a `.devloops-new`
file next to the changed one is enough.

## P-13 Interactive `init`

**Decision**:
- **When it asks**: only when stdin and stdout are both terminals and `--no-prompt` is not given.
- **Questions**: for the backend target, the frontend target, and the requirements, in that order,
  each with a default:
  - `backend`;
  - `frontend`;
  - `active spec-kit feature (<dir>)` if `.specify/feature.json` names an existing folder,
    otherwise blank.
- **Validation**: an answer is checked against the target guard and the existence of the
  requirements, and the question is asked again until it is valid (FR-007b).
- **Non-interactive** (`--no-prompt`, or stdin/stdout not a terminal): uses the flags or the
  defaults. The requirements are left unset when nothing applies, and the output says how to set
  them.

**Rationale**: This mirrors spec-kit's interactive `init`, and scripts and CI never hang.

## P-14 `devloops check`

**Decision**: `devloops check [--json]` builds a list of items with: `name`, `status`
(`ready`, `missing`, or `warning`), `detail`, `fix`, and `needed_for`. It reads the project's
effective configuration when run inside a project, and the packaged defaults otherwise.

| Item | Ready when | Fix printed |
|------|-----------|-------------|
| python | ≥ 3.10 | install Python 3.10+ |
| claude | `claude --version` ≥ 2.1.283 (A-5) | install or update Claude Code |
| curl | `curl --version` runs | install curl |
| playwright-mcp | first element of the effective MCP command is on PATH (`npx`) | install Node.js (npx) |
| browser | `executable_path` exists and is executable; or, with none set, a Chrome-channel binary is found | `npx playwright install chrome` or set `playwright.executable_path` |
| git | on PATH, when `git.commit_per_milestone` is on | install git |
| display | `headless: false` and Linux without `DISPLAY` / `WAYLAND_DISPLAY` → warning | set `headless: true`, or run under `xvfb-run` |
| shared-visible-browser | `headless: false` set in the shared `devloops.json` → warning | move it to `devloops.local.json` |

The exit code is 0 when no needed item is missing, otherwise 30 (input error, as in 001's
`missing-tool`). Warnings never fail the check. A run's own preflight (001 FR-013b) is unchanged.

**Rationale**:
- Each item matches a setup failure seen in T076, or a new setting this feature adds.
- 30 is the existing exit code for "fix your inputs or environment".

## P-15 Visible browser settings

**Decision**: `config.schema.json` `playwright` gains:
- `headless` (boolean, default `true`);
- `executable_path` (string or null, default `null`).

The default `mcp_command` becomes `null`, meaning "derived":
`["npx", "@playwright/mcp@latest"]`, plus `--headless` when `headless` is true, plus
`--executable-path <p>` when one is set.

An explicit `mcp_command` list is used exactly as written (FR-017). Configurations already frozen
in existing workspaces contain an explicit list, so they behave as before.

A visible browser that cannot start (no display) appears as the MCP server failing to start. 001
already classifies that as a service error, which does not use up a trial (spec edge case). The
message adds "no display available".

## P-16 Spec-kit bridge

**Decision**:
- **Options**: `--speckit-feature [DIR]` on `run` and `orchestrate`. With no value, it takes the
  active feature. It cannot be combined with `--requirements`. The configuration can set
  `requirements.speckit_feature` instead.
- **Active feature**: the `feature_directory` in `<project>/.specify/feature.json`. It is resolved
  on the first run and recorded in `workspace.json`, so later starts don't depend on what is active
  later.
- **Inputs**:
  - `spec.md` is the requirements input (001 FR-051a identity).
  - `plan.md` and `tasks.md`, when present, are recorded with their sha256 and checked on every
    start (FR-023c).
  - A missing `spec.md` stops the run with `missing-input`.
- **Parsing `tasks.md`**: devloops parses it itself, so the check below is reliable:
  - phases are `## Phase <n>: <title>`;
  - tasks are `- [ ]`/`- [x]` lines with `T\d{3,}`, optional `[P]`, and `[US<n>]` labels.

  The planning context gets `speckit: {feature_dir, spec, plan_md, phases: [{n, title, tasks:
  [{id, story, done, text}]}]}`. The step prompt `plan.md` gets a "spec-kit feature" section that
  tells the planner to follow the phases, keep the task IDs, and list what it leaves out.
- **Plan schema** (additive and optional):
  - each milestone gains `speckit_phase`;
  - each task gains `speckit_tasks: ["T012", …]`;
  - the plan gains `speckit_omitted: [{id, reason}]`.

  `plan.py` checks (FR-023a, FR-023b):
  - every in-scope task ID is either referenced by a task or listed in `speckit_omitted` with a
    non-empty reason;
  - every referenced ID exists;
  - milestones follow the phase order.

  A violation is an invalid plan, which uses up a planning trial, like 001's story-scope check.
  The plan summary renders the three lists: planned, omitted, and devloops tasks with no spec-kit
  task.
- **Story selection**: `--story-id US<n>` is matched against a `User Story <n>` heading in
  `spec.md` (FR-025), not by the literal-ID search of 001.
  - **In scope**: the tasks labelled `[US<n>]`, plus unlabelled setup or foundational tasks that
    the plan marks as needed. Each of those must be listed with that reason (FR-023d).
  - **Out of scope**: tasks labelled with other stories. They are neither referenced nor required
    to be listed.
- **Tasks already checked**: a task marked `[x]` is still in scope (spec edge case). Its `done` flag
  is passed to the planner, and the plan summary notes it.

**Rationale**:
- A deterministic parse plus a schema check makes "the plan follows `tasks.md`" verifiable, rather
  than just hoped for (Principle III).
- The format matches `.specify/templates/tasks-template.md` and 001's own `tasks.md`.

**Alternatives**: Converting `tasks.md` to a plan with no model call. Rejected in clarification
Q3, because spec-kit tasks have no acceptance criteria or checks.

## P-17 Making this repository an initialized project (A-3)

**Decision**: Run `bin/devloops init --no-prompt --track-workspaces` on this repository. Then:
- set `workspaces_dir: "workspaces"` in its `devloops.json`, so the committed T076 workspaces stay
  where they are;
- remove `.claude/skills/loops-*`;
- commit the rendered `.claude/skills/devloops-*`.

The tests' `TempEnv` writes the same small `devloops.json` in each temporary root, so the 312
existing tests keep their `workspaces/` paths (SC-008).

**Rationale**: This is the smallest migration, and it keeps 001 A-4 (workspaces committed here).

## P-18 Version and minimum Claude Code version

**Decision**: `devloops.__version__` becomes `0.2.0` for this feature. The minimum supported Claude
Code version for `check` is a constant, `MIN_CLAUDE_VERSION = (2, 1, 283)`, in `preflight.py`
(A-5).
