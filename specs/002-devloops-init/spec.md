# Feature Specification: Devloops Project Setup

**Feature Branch**: `main` (no branch hook configured)

**Created**: 2026-10-05

**Status**: Draft

**Input**: User description: "002-devloops-init with the design above". The design proposed
making devloops work like spec-kit:
- install it once as a tool;
- run `devloops init` to write a small `.devloops/` folder and Claude Code skills into any project;
- discover the project from the current directory;
- read project defaults from `.devloops/devloops.json`;
- let the project override prompts;
- add `devloops check` and `init --upgrade`, using an install manifest;
- bridge from spec-kit feature folders;
- switch to a visible browser with one config setting.

## Scope and Source Classification

**In scope**:
- turning devloops from a tool that runs only inside its own repository into one that is installed
  once and set up in any project;
- project initialization, project discovery, and project-level defaults;
- per-project prompt overrides;
- the readiness check, Claude Code skills, and safe upgrades;
- using spec-kit feature folders as loop input.

**Out of scope**: changing how the loops plan, implement, validate, retry, or orchestrate. Feature
001 (`specs/001-reusable-dev-loops`) defines that, and its requirements still hold unless this spec
says otherwise.

Every requirement below is tagged with its source:

| Tag | Meaning |
|-----|---------|
| **[E]** | **Explicit**: part of the design the developer accepted for this feature |
| **[I]** | **Implied**: needed to satisfy an explicit requirement or a constitution MUST; the reason is given inline |
| **[C]** | **Constitution**: required by a MUST in `.specify/memory/constitution.md` (principle cited) |
| **[K]** | **Kept from 001**: a 001 guarantee that this feature must not weaken (001 item cited) |

## Clarifications

### Session 2026-10-05

- Q: In initialized projects, should run workspaces be committed, and how is evidence shared? →
  A: Workspaces stay out of version control. A `devloops dashboard` command generates a complete,
  self-contained dashboard that embeds every file and piece of evidence the developer needs
  (screenshots, check results, prompts, logs, outputs), so the dashboard alone can be opened,
  committed, or shared.
- Q: Should a project have a per-developer, git-ignored configuration file next to the shared
  `devloops.json`? → A: Yes. `.devloops/devloops.local.json`, git-ignored, is applied after
  `devloops.json` and before `--config`. It is for machine-specific settings such as the browser
  executable, the visible browser, or a personal budget.
- Q: When a spec-kit feature already has `tasks.md` (and `plan.md`), how should devloops use them?
  → A: The devloops planner follows them. spec-kit's phases become milestones, and task IDs (e.g.
  `T012`) are kept. Devloops still writes the acceptance criteria and checks, and still pauses for
  approval.
- Q: Should `init` add a Claude Code permission rule, so that the skills can run `devloops` without
  approval prompts? → A: Not by default. `init` prints the rule and how to add it. `init
  --allow-skills` adds it to the project's Claude Code settings on request.
- Q: How should `init` learn the loop targets and the requirements file? → A: From flags
  (`--backend-target`, `--frontend-target`, `--requirements`). When it runs in a terminal and a
  value is not given, it asks for that value, offering a default: `backend/`, `frontend/`, or the
  active spec-kit feature if there is one. `--no-prompt` skips the questions, for scripts.
- Q: Should the full dashboard be generated automatically when a run finishes, or only on demand?
  → A: Automatically when a loop or the orchestrator ends (completed, or stopped on failure or on an
  error), and on demand with `devloops dashboard` at any time. It is not generated at intermediate
  pauses such as awaiting approval.
- Q: Should the full dashboard embed each Claude Code call's conversation? → A: Yes. Every call's
  full conversation is embedded, untruncated: every message, tool call, and file edit.
- Q: Where should the full dashboard be saved, and should git track it by default? → A: A new
  timestamped file each time, at `.devloops/dashboards/<workspace>/<time>.html`. Git ignores it by
  default.

### Session 2026-10-07

- Q: The lightweight page linked raw files and could not show conversations; how should a developer
  see files and conversations? → A: `devloops dashboard --serve`: a local, read-only server with the
  full dashboard's views, loading each file and conversation when opened (no size limit), following
  a run as it goes, and switching between the project's workspaces. `devloops dashboard --export`
  writes the self-contained file; `dashboard.html` becomes a summary written when a command pauses,
  stops, or ends.
- Q: Should a run start the server itself? → A: No. Commands print the command, or the running
  server's URL; nothing outlives the command that started it.
- Q: Can the server be reached from a private network? → A: Yes, with `--host`: beyond this machine
  it requires a token by default (`--token` to set it, `--no-token` to drop it) and warns that it
  serves plain HTTP.

## User Scenarios & Testing *(mandatory)*

Every story has the same actor: a **developer** who wants to use the devloops loops in their own
project, not inside the devloops repository.

### User Story 1 - Install once and initialize a project (Priority: P1)

The developer installs devloops once on their machine. In the root of an existing (or empty)
project, they run `devloops init`. It creates a `.devloops/` folder (project configuration, install
manifest, workspaces location) and the devloops Claude Code skills. It also keeps run records out of
version control by default, and prints what it created and the next command to run.

**Why this priority**: Nothing else in this feature works until a project can be set up without
copying or pointing back to the devloops repository.

**Independent Test**:
1. Install devloops.
2. Run `devloops init` in an empty temporary directory.
3. Check the created files.
4. Check that nothing was written anywhere else on disk.
5. Check that a second `init` changes nothing.

**Acceptance Scenarios**:

1. **Given** a directory with no devloops files, **When** the developer runs `devloops init`,
   **Then** `.devloops/devloops.json`, `.devloops/manifest.json`, and the devloops skills are
   created. The ignore rule for workspaces is added, and the output lists every created file and
   the next command.
2. **Given** an initialized project, **When** the developer runs `devloops init` again, **Then**
   nothing changes, and the output says the project is already initialized and how to upgrade.
3. **Given** a project that already has a file at a path `init` would write, which devloops did not
   install, **When** the developer runs `devloops init`, **Then** no file is written at all, and
   each conflicting path is listed.
4. **Given** `init` runs in a terminal without target flags, **When** the developer accepts the
   offered defaults, **Then** `devloops.json` records `backend/` and `frontend/` as the targets and
   the active spec-kit feature (if any) as the requirements, and `devloops run` then runs with no
   path flags. *(Revised by specs/003-single-run-command.)*
5. **Given** `init --no-prompt` runs in a script, **When** no values are given, **Then** it
   completes without waiting for input, writes the default targets, and says the requirements still
   need to be set.
6. **Given** the developer wants to try devloops without installing it, **When** they run the
   repository's `bin/devloops init` from a source checkout, **Then** the result is the same as with
   the installed tool.

---

### User Story 2 - Run the loops in a project with its own defaults (Priority: P1)

In an initialized project, the developer runs `devloops run` (formerly a loop or the orchestrator;
revised by specs/003-single-run-command) from the project root or any folder below it. Devloops
finds the project the way version control finds its repository. It reads the targets, the
requirements file, limits, and browser settings from the project configuration, and keeps workspaces
inside the project. Targets may be folders of the project itself (for example `api/` and `web/`).
The developer can show the browser during UI validation by changing one setting.

**Why this priority**: This is the outcome the developer asked for. The loops run in the developer's
project, with project-wide defaults, and without repeating paths and options on every command.

**Independent Test**:
1. Initialize a temporary project, and set targets and requirements in its configuration.
2. Run `devloops run` from a subfolder, using the offline test double for Claude Code. *(Revised by
   specs/003-single-run-command.)*
3. Confirm the workspace is created inside the project.
4. Confirm the code is written only into the configured targets.
5. Confirm no command-line flag beyond the story selection was needed.

**Acceptance Scenarios**:

1. **Given** an initialized project whose configuration names the requirements and both targets,
   **When** the developer runs `devloops run --story-id US1` from a subfolder, **Then** the
   run uses those values, and the workspace and its dashboard are created in the project's workspaces
   location. *(Revised by specs/003-single-run-command.)*
2. **Given** a configuration value and a different value passed on the command line, **When** a run
   starts, **Then** the command-line value wins, and the frozen run configuration records the value
   used. In the same way, a value in the local configuration wins over the shared project
   configuration.
3. **Given** a run that has already started, **When** the developer edits the project
   configuration, **Then** the started run keeps its frozen configuration (001 FR-062), and `status`
   says the project configuration has changed since the run started.
4. **Given** the setting that shows the browser during UI validation, **When** `frontend-dev`
   validates, **Then** the browser runs in a visible window. Without the setting, it runs headless
   as before.
5. **Given** a directory outside any initialized project, **When** the developer runs any command
   other than `init` or `check`, **Then** it stops with a usage error that says no project was found
   and suggests `devloops init`.
6. **Given** a project that has been moved or cloned to another path, **When** a workspace is
   resumed there, **Then** targets inside the project resolve against the new location, and the run
   continues.

7. **Given** a run that ends (completed, or stopped), **When** the command returns, **Then** a full
   dashboard with every artifact embedded is written as a new timestamped file under
   `.devloops/dashboards/<workspace>/`, and its path is printed. At the approval pause, only the lightweight dashboard is refreshed.

---

### User Story 3 - Check that the environment is ready (Priority: P2)

Before a first run, the developer runs `devloops check`. It reports each prerequisite as ready,
missing, or a warning, with a one-line fix for anything missing. The prerequisites are:
- the language runtime version;
- Claude Code and its version;
- the HTTP client used for backend validation;
- the browser-automation server and a usable browser;
- version control, when commits per milestone are on;
- a display, when the visible browser is on.

**Why this priority**: The T076 real runs lost time and money to setup problems: a missing browser
channel, and a Claude Code version that rejected the schemas. A check catches these before any
Claude Code call is paid for.

**Independent Test**: Run `devloops check` with `PATH` set to hide one prerequisite at a time. Each
run must name the missing item, give its fix, and exit with a non-zero code.

**Acceptance Scenarios**:

1. **Given** a machine with every prerequisite, **When** the developer runs `devloops check`,
   **Then** every item is reported ready, and the exit code is 0.
2. **Given** a missing prerequisite that a configured loop needs, **When** the developer runs
   `devloops check`, **Then** the report names it, gives a fix, and exits non-zero.
3. **Given** the visible browser is configured but no display is available, **When** the developer
   runs `devloops check`, **Then** it reports a warning that names the missing display. Running
   headless is one of the suggested fixes.
4. **Given** the installed devloops version differs from the version recorded in the project
   manifest, **When** any command runs, **Then** it warns and suggests `devloops init --upgrade`.

---

### User Story 4 - Drive the loops from Claude Code (Priority: P2)

Inside Claude Code, the developer types a devloops skill: run, approve, replan, retry, status, or
dashboard (the orchestrate skill was removed by specs/003-single-run-command). Each skill runs
exactly one devloops command in the project and summarizes the result, including what the exit code
asks the developer to do next.

**Why this priority**: spec-kit is used through slash commands, and the developer wants the same
experience. The skills hold no loop logic, so they are thin and low-risk.

**Independent Test**: In an initialized project, check that every installed skill:
- names exactly one devloops command;
- passes the user's arguments unchanged;
- holds no loop logic.

**Acceptance Scenarios**:

1. **Given** an initialized project, **When** the developer invokes the run skill, **Then** the
   skill runs the project's loops and summarizes the status, the exit code, and the next action.
   *(Revised by specs/003-single-run-command.)*
2. **Given** a skill invocation that is missing a required argument, **When** the command stops
   with a usage error, **Then** the skill reports the error and does not retry or guess.
3. **Given** an initialized project, **When** the developer runs `devloops init --allow-skills`,
   **Then** one permission rule for `devloops` commands is added to the project's Claude Code
   settings, with every existing setting kept. The skills then run without an approval prompt.

---

### User Story 5 - Use a spec-kit feature as the requirements (Priority: P2)

The developer has written a feature with spec-kit (`specs/<feature>/spec.md`, maybe also
`plan.md`). They pass that feature folder to `devloops run` (revised by
specs/003-single-run-command), or use the spec-kit
feature that is currently active. The feature's spec becomes the requirements. When the feature
has `plan.md` and `tasks.md`, the planner follows them: spec-kit's phases become devloops
milestones, and its task IDs are kept. Devloops adds the acceptance criteria and checks, and pauses
for approval as usual. A story can be selected by its spec-kit user story number.

**Why this priority**: It links the two tools: spec-kit decides *what* to build, and devloops builds
and validates it. The loops already accept any Markdown requirements, so this is a convenience, not
a prerequisite.

**Independent Test**: Use a spec-kit spec fixture with two user stories. Select story 2 by number,
with the offline Claude Code test double. The plan must cover only story 2, and the recorded
requirements must be the feature's spec file.

**Acceptance Scenarios**:

1. **Given** a spec-kit feature folder, **When** the developer passes it as the loop input,
   **Then** its `spec.md` is the requirements input, and its `plan.md`, if present, is supplied as
   stack context.
2. **Given** a spec-kit feature with `tasks.md`, **When** the loop plans, **Then** each devloops
   milestone corresponds to a spec-kit phase that has tasks for that loop's target. Each planned
   task carries the spec-kit task ID it implements. Any planned work with no spec-kit task, and any
   spec-kit task left out, is listed in the plan summary for the approval pause.
3. **Given** no folder is named, **When** the developer asks for the active spec-kit feature,
   **Then** the feature recorded as active by spec-kit is used, and the output names it.
4. **Given** a spec-kit spec with "User Story 2" headings, **When** the developer selects story
   `US2`, **Then** only that story is planned (001 FR-010, FR-010a).
5. **Given** a feature folder without `spec.md`, or a story number with no matching heading,
   **When** the run starts, **Then** it stops with an input error that names the missing file or
   story.

---

### User Story 6 - Upgrade devloops without losing local changes (Priority: P3)

After installing a newer devloops, the developer runs `devloops init --upgrade` in the project.
Devloops-installed files the developer has not changed are updated. Files the developer changed are
kept, and the output lists them with the path of the new version, so the developer can merge by
hand. The project manifest records the new version.

**Why this priority**: It is needed once devloops changes after projects are set up. The first
setup works without it.

**Independent Test**:
1. Initialize with one version.
2. Change one installed skill, and delete another.
3. Upgrade with a newer version.
4. Check that the unchanged files were updated, the changed file was kept and reported, the
   deleted file was reported and not restored, and the manifest version changed.

**Acceptance Scenarios**:

1. **Given** installed files with no local changes, **When** the developer upgrades, **Then**
   they are replaced with the new versions, and the manifest records the new version and file
   fingerprints.
2. **Given** an installed file the developer changed, **When** the developer upgrades, **Then**
   the file is not overwritten, and the new version is written beside it for review.
3. **Given** the installed devloops is older than the version in the project manifest, **When** the
   developer upgrades, **Then** nothing changes, and the command explains that downgrades are not
   applied.

---

### User Story 7 - Customize the loop prompts for one project (Priority: P3)

The developer wants project conventions in the prompts, for example "use the existing logger". They
place a copy of a prompt file in the project's prompt-override folder and edit it. Runs in that
project use the override, and every Claude Code call records which prompt source it used.

**Why this priority**: It is useful for adoption but optional. The packaged prompts work as they
are.

**Independent Test**: Add an override for one step's prompt, and run the offline suite's stub loop.
The rendered prompt must contain the override text, and the invocation record must name the
override file and its fingerprint.

**Acceptance Scenarios**:

1. **Given** an override for a step's prompt, **When** that step runs, **Then** the override is
   used instead of the packaged prompt, and the call's record names the override and its
   fingerprint.
2. **Given** no override, **When** a step runs, **Then** the packaged prompt is used, as today.

### Edge Cases

- **Nested projects**: A folder inside one initialized project is itself initialized. The nearest
  project root wins.
- **Machine-specific settings in the shared file**: The visible browser or a browser path placed in
  the shared configuration affects every teammate. The README recommends the local configuration
  for them, and `check` warns when the visible browser is set in the shared file.
- **Invalid project configuration**: Unreadable JSON (in the shared or the local file), an unknown key, or a value of the wrong type
  stops the command with an input error. The error names the file, the key, and the problem,
  before any workspace is written.
- **Target overlapping devloops files**: A configured target overlaps `.devloops/`, a workspace,
  the installed devloops files, or the other loop's target. The run stops with an input error
  (keeps 001 FR-035a–d).
- **Target outside the project**: This is still allowed, as in 001. It is recorded as an absolute
  path because it cannot be relative to the project.
- **The devloops source repository itself**: The repository that develops devloops must keep
  working, including its existing committed workspaces under `workspaces/`, via the
  workspaces-location setting (FR-012).
- **Removed prerequisite after `check`**: A run still performs its own tool checks before planning
  (001 FR-013b). `check` is advice, not a gate.
- **Visible browser without a display**: UI validation cannot start a browser. This is reported as a
  service error that names the missing display, and it does not use up a trial (001 FR-067).
- **Init in a project that is not under version control**: `init` still works. The ignore rule is
  written to an ignore file anyway, and the output mentions that no repository was found.
- **Unreadable Claude Code settings**: With `--allow-skills`, the existing settings file is not
  valid JSON. Devloops leaves it untouched, reports the problem, and prints the rule to add by hand.
- **Deleted installed file**: An upgrade does not restore a file the developer deleted. It reports
  the file as deleted, unless the developer asks to restore it.
- **spec-kit tasks already marked done**: `tasks.md` marks some tasks `[X]`. Devloops still plans
  them; it does not trust the check mark as validation (Principle III). Instead, it notes them in the
  plan summary, so the developer can drop them at approval.
- **spec-kit phase mixing backend and frontend tasks**: Each loop takes only the tasks for its own
  target. A phase with no tasks for a loop is not a milestone of that loop.
- **Accumulating full dashboards**: Every run end adds a file, and devloops never deletes them.
  Removing old ones is the developer's choice. `status` reports how many there are and their total
  size.
- **Very large full dashboard**: The embedded evidence makes the page large. It is still generated
  in full. The command reports the page size and the largest embedded files (like 001's
  `large_evidence`).
- **Conversation history not on this machine**: The workspace was run elsewhere, or Claude Code's
  history was cleared. Calls whose conversation was copied into the workspace are unaffected. Any
  others are listed with their session IDs and marked unavailable (FR-042).
- **Evidence file missing from disk**: A file the state refers to has been deleted. The full
  dashboard is still generated and marks that item as missing, instead of failing.
- **Workspace name reused across projects**: Workspaces of different projects never collide,
  because each project keeps its own.

## Requirements *(mandatory)*

### Functional Requirements

#### Installation and initialization

- **FR-001** [E]: Devloops MUST be installable once per machine as a command-line tool. Installation
  MUST need no third-party dependencies beyond the language runtime (keeps the stdlib-only design;
  Principle X).
- **FR-002** [E]: Devloops MUST keep working from a source checkout without installation, with
  identical behavior.
- **FR-003** [E]: `devloops init` MUST set up the current directory as a devloops project, or a
  given directory if one is named. It MUST create:
  - the project configuration file `.devloops/devloops.json`, with every supported key present
    and set to the packaged default, or omitted as a documented optional key;
  - the install manifest `.devloops/manifest.json`, which records the devloops version and a
    fingerprint of every file `init` installed;
  - the prompt-override folder `.devloops/prompts/`, empty except for a short README;
  - the devloops Claude Code skills (FR-020).
- **FR-004** [E, confirmed in Clarifications]: By default, `init` MUST keep three things out of
  version control: the workspaces location, the full-dashboards location (FR-036), and the local
  configuration file (FR-010). It does this by adding ignore rules to the project's ignore file,
  creating the file if needed. Documented options MUST skip the workspace rule and the dashboards
  rule. The local configuration rule is always added.
- **FR-005** [I, from FR-003 + Principle IV]: `init` MUST NOT overwrite or modify any existing file
  except by appending the ignore rule. If any file it would create already exists and devloops did
  not install it, `init` MUST write nothing and MUST list the conflicting paths.
- **FR-006** [I, from Principle IV]: Running `init` on an initialized project MUST change nothing,
  and MUST report that the project is initialized and how to upgrade.
- **FR-007** [E]: `init` MUST print every file it created or changed and the next command to run
  (`devloops check`, then `devloops run`). *(Revised by specs/003-single-run-command: the next
  command no longer names `orchestrate` or `run <loop>`. A target prompt also accepts `none`, and
  `--no-backend` / `--no-frontend` write a `null` target; a project needs at least one loop.)*
- **FR-007a** [Clarifications]: `init` MUST accept the backend target, the frontend target, and the
  requirements input as options, and write them to the project configuration (relative to the
  project root, per FR-013).
  - **Interactive**: When `init` runs in an interactive terminal, without `--no-prompt`, it MUST ask
    for each value not given on the command line. Each question shows a default the developer can
    accept with Enter:
    - `backend/` for the backend target;
    - `frontend/` for the frontend target;
    - the active spec-kit feature, if one is recorded, otherwise empty, for the requirements.
  - **Non-interactive**: Otherwise, or with `--no-prompt`, `init` MUST NOT wait for input. It writes
    the given values, and the defaults for the targets. The requirements stay unset when no value or
    active spec-kit feature exists, and the output says how to set them.
- **FR-007b** [I, from FR-007a + FR-014]: A target value that would be rejected by the target guard
  MUST be rejected by `init` before any file is written. Asked interactively, the question is
  repeated. Given non-interactively, `init` stops with an input error.
- **FR-007c** [cost; 001 FR-033a]: A new `devloops.json` MUST carry the recommended model split in
  its `config` (`model: sonnet`; `models`: `opus` for `plan`, `replan`, `author-checks`, and
  `fix_last_trial`), written into the project rather than shipped as a packaged default, so it is
  visible and editable and never overrides the model of a setup without those names. On a terminal
  `init` asks first (default yes); `--no-models` leaves `config` empty, so Claude Code picks the
  model. An existing `devloops.json` is never changed: `init --upgrade` only notes the block to add
  when neither configuration file sets `model` or `models`.

#### Project discovery and configuration

- **FR-008** [E]: Every command except `init` and `check` MUST find its project root by searching
  from the current directory upward for the nearest `.devloops/` folder. Outside any project, it
  MUST stop with a usage error that suggests `init`.
- **FR-009** [E]: The installed devloops files (loop definitions, prompts, schemas, hooks) and the
  project MUST be separate locations. Nothing in the project MUST be required to locate the
  installed files, and no run MUST write to the installed files.
- **FR-010** [E]: Configuration MUST be resolved in this order, each level overriding the one
  before:
  1. packaged defaults;
  2. the project configuration (`.devloops/devloops.json`, shared and committed);
  3. the local configuration (`.devloops/devloops.local.json`, per developer and git-ignored;
     optional, and `init` does not create it);
  4. a `--config` file;
  5. command-line flags.

  The resolved configuration is frozen at a workspace's first run, as in 001 FR-062.
- **FR-011** [E]: The project configuration MUST be able to set:
  - the target of each loop;
  - the requirements input and story selection mode;
  - the default workspace name;
  - every key that 001's run configuration supports.

  Relative paths in it MUST resolve against the project root.
- **FR-012** [I, from the source-repository edge case]: The workspaces location MUST default to
  `.devloops/workspaces/` and MUST be configurable in the project configuration.
- **FR-013** [I, from US2 scenario 6]: A target inside the project root MUST be recorded relative to
  the project root, so that a moved or cloned project resumes correctly. A target outside it MUST
  be recorded as an absolute path.
- **FR-014** [E; changes 001 FR-035a only in what counts as reserved]: The target guard MUST reject
  targets that overlap:
  - the installed devloops files;
  - the project's `.devloops/` folder;
  - the workspace;
  - the other loop's target.

  It MUST allow targets anywhere else inside the project.
- **FR-015** [I, from US2 scenario 3]: `status` MUST report when the project or local configuration has
  changed since the workspace's configuration was frozen. Such a change MUST NOT affect the
  started run.
- **FR-016** [I, from Principle IV]: An invalid project or local configuration MUST stop every command that
  reads it with an input error, before any workspace is written. The error names the file, the key,
  and the problem.

#### Visible browser

- **FR-017** [E]: The configuration MUST offer a setting that runs UI validation in a visible
  browser window, defaulting to headless. It MUST also offer a setting for the browser executable.
  An explicitly configured browser-automation server command MUST still take precedence over both.

#### Readiness check

- **FR-018** [E]: `devloops check` MUST report each prerequisite as ready, missing, warning, or
  unused (not used by the project's loops), with a one-line fix for each one that is missing or a
  warning. *(Revised by specs/003-single-run-command: `unused` added; an unused item never fails
  the check.)* The prerequisites are:
  - the language runtime version;
  - Claude Code, at or above the minimum supported version;
  - the HTTP client for backend validation;
  - the browser-automation server and a usable browser;
  - version control, when per-milestone commits are configured;
  - a display, when the visible browser is configured.
- **FR-019** [I, from FR-018]: `check` MUST exit 0 when every prerequisite needed by the project's
  configuration is ready, and non-zero otherwise. It MUST offer machine-readable output like the
  other commands (001 `--json`). It MUST work outside a project, checking against the packaged
  defaults. *(Revised by specs/003-single-run-command: inside a project, only the loops the project
  includes are checked, and a project that includes no loop gets a missing `loops` item.)*

#### Claude Code skills

- **FR-020** [E]: `init` MUST install one skill for each of: run, approve, replan, retry,
  status, and dashboard. *(Revised by specs/003-single-run-command: the run skill runs the
  project's loops, and the orchestrate skill is removed.)*
- **FR-021** [K, 001 skills design]: Each skill MUST run exactly one devloops command, pass the
  user's arguments unchanged, summarize the result and what the exit code asks of the developer,
  and contain no loop logic.
- **FR-022** [I, from FR-020]: The skills in the devloops repository itself MUST be the same
  skills `init` installs, so they cannot drift apart.
- **FR-022a** [Clarifications]: By default, `init` MUST NOT edit Claude Code settings. Its output
  MUST show the permission rule that lets the skills run `devloops` commands without an approval
  prompt, and how to add it.
- **FR-022b** [Clarifications]: `init --allow-skills` MUST add that one rule to the project's shared
  Claude Code settings, creating the file if it is absent. It MUST preserve every existing setting,
  MUST NOT add a rule that is already present, and MUST report the change. It is the only case where
  devloops edits a file it did not install (an exception to FR-005). It MUST also work on an
  already-initialized project.

#### Spec-kit bridge

- **FR-023** [E]: `devloops run` MUST accept a spec-kit feature folder as input
  *(revised by specs/003-single-run-command; formerly "loops and the orchestrator")*. Its
  `spec.md` is the requirements input, with the same content identity checks as 001 FR-051a. Its
  `plan.md`, when present, is supplied to planning as stack context, at the "named in the
  requirements" level of 001's stack priority (001 FR-057–060).
- **FR-023a** [Clarifications]: When the feature has `tasks.md`, planning MUST follow it:
  - Milestones correspond to spec-kit phases, in spec-kit's order. Only phases with tasks for the
    loop's target (backend or frontend) are included.
  - Each planned task MUST reference the spec-kit task ID(s) it implements.

  Devloops still authors the acceptance criteria and validation checks, and the approval pause is
  unchanged (001 FR-053).
- **FR-023b** [I, from FR-023a + Principle I]: The plan summary MUST list every spec-kit task that
  is planned for this loop, every one left out (with the reason, for example "frontend task"), and
  any devloops task with no spec-kit counterpart. So the developer reviews the differences at
  approval, not afterwards.
- **FR-023c** [I, from FR-023a + 001 FR-051a]: `plan.md` and `tasks.md` MUST be recorded and
  compared like the requirements input. A change after planning stops the run as a changed input.
- **FR-023d** [I, from FR-023a + 001 FR-010a]: In single-story mode, only tasks labelled with that
  story are in scope. Setup or foundational tasks are included only when the story needs them, and
  each one MUST be listed as such in the plan summary.
- **FR-024** [E]: A documented option MUST select the spec-kit feature that spec-kit records as
  active, and the output MUST name the folder used.
- **FR-025** [I, from US5]: With a spec-kit input, story selection MUST accept a user story number
  (`US<n>`) and match the spec's "User Story <n>" heading. Single-story scoping is unchanged
  (001 FR-010, FR-010a, FR-010b).
- **FR-026** [I, from FR-013 of 001]: A missing `spec.md`, or a story number with no matching
  heading, MUST stop the run with an input error that names it.

#### Upgrade

- **FR-027** [E]: `devloops init --upgrade` MUST:
  - replace each installed file whose fingerprint still matches the manifest;
  - keep each file whose fingerprint differs, writing the new version beside it and listing it;
  - report deleted files without restoring them, unless asked to;
  - add files that are new in this version;
  - update the manifest.
- **FR-028** [I, from Principle IV]: An upgrade MUST NOT apply an older devloops version over a
  newer manifest version, and MUST NOT touch workspaces or the project configuration's values. New
  configuration keys come from the packaged defaults, under FR-010.
- **FR-029** [E]: Every command MUST warn when the running devloops version differs from the
  project manifest's version, and suggest `init --upgrade`.

#### Prompt overrides

- **FR-030** [E]: For each prompt the loops use, a file with the same relative path in the
  project's prompt-override folder MUST be used instead of the packaged one.
- **FR-031** [C, Principle VIII]: Each Claude Code call's invocation record MUST name the prompt
  source used (packaged or override), its path, and its fingerprint.
- **FR-032** [K, 001 FR-062 / Principle IV]: A run MUST record which overrides were in effect when
  its configuration was frozen. Adding, changing, or removing an override after that MUST be
  reported by `status`, and it MUST NOT silently change the prompts of milestones already done.

#### Full dashboard

- **FR-035** [Clarifications; revised 2026-10-07]: `devloops dashboard --export` MUST generate a full dashboard of a workspace
  as one self-contained file. Opened anywhere, with no other file and no network, it shows
  everything the per-command dashboard (001) shows. It also embeds every artifact the developer
  needs to review the run:
  - screenshots and other evidence files;
  - each trial's validation results and HTTP checks;
  - the frozen check lists;
  - the plan, milestone files, outputs, and `progress.md`;
  - the prompts sent;
  - the per-call stream logs;
  - the full Claude Code conversation of every call (FR-040).
- **FR-036** [Clarifications]: Each full dashboard MUST be written as a new file at
  `<dashboards location>/<workspace>/<UTC timestamp>.html`, and MUST NOT replace an earlier one. The
  dashboards location defaults to `.devloops/dashboards/` and is configurable. The file name sorts
  chronologically and is unique even for two dashboards generated within the same second. The
  command MUST print the path and size. `--export --out <file>` writes to that file instead,
  replacing it.
- **FR-036a** [I, from FR-036 + FR-038]: The summary page MUST link to the workspace's full
  dashboards, newest first, so the latest complete record is one click away.
- **FR-037** [I, from FR-035]: An artifact that cannot be read MUST appear in the full dashboard as
  missing, with its path. It MUST NOT stop the command. Model-written text MUST be escaped, as in
  the 001 dashboard.
- **FR-038** [K, 001 dashboard; revised 2026-10-07]: The workspace's `dashboard.html` is kept as a
  summary page: status, milestones, trials, failures, questions, calls, and cost. It MUST NOT link
  to files on disk or show conversations; where it would, it MUST say how to see them
  (`devloops dashboard --serve`). The run and decision commands (revised by
  specs/003-single-run-command) MUST write it when they pause,
  stop, or end (not after every event), and it MUST NOT reload itself. `devloops dashboard` writes
  it on demand. `dashboard.light` (default `true`; not frozen, like `dashboard.full_on_stop`) turns
  the automatic writes off.
- **FR-039** [Clarifications; revised: full dashboards accumulated unasked]: The full dashboard MUST
  be generated by `devloops dashboard --export`. It MAY also be generated automatically whenever a
  run or decision command (revised by specs/003-single-run-command) ends in a final status
  (completed, stopped-on-failure, stopped-on-input-error, or stopped-on-service-error), only when
  `dashboard.full_on_stop` is set (default `false`; not frozen: read from the configuration files as
  they are when the command ends, and not reported as drift). The command's summary MUST say where
  files and conversations are shown: the running server's URL (FR-042c), or `devloops dashboard
  --serve`. It MUST NOT be generated at awaiting-approval or when a lock is refused. As with the
  lightweight dashboard, a failure to generate it MUST only warn and MUST NOT change the command's
  outcome or exit code.
- **FR-039a** [a run printed nothing until it ended]: `run`, `approve`, `replan`, and `retry`
  (revised by specs/003-single-run-command: `orchestrate` removed) MUST report progress as they
  work, on stderr: one timestamped line per recorded event and per Claude call (its start, with the
  model, and its end, with duration, cost, and tool calls), and while a call runs, a status line in
  a terminal or a "still ..." line every minute otherwise. They MUST print, before running, where
  files and conversations are shown (as in FR-039) and where the progress log is. `--verbose` adds
  one line per tool Claude uses, `--quiet` prints only the final summary, and `--json` is quiet
  unless `--verbose`. The same lines (tools included, no colors) MUST be appended to the loop's
  `state/run.log`, with a "still ..." line every minute while a call runs; the write-boundary audit
  does not count the log as Claude's write. When a call ends, what it left running in its process
  group MUST be stopped.
- **FR-040** [Clarifications]: The full dashboard MUST embed, for every recorded Claude Code call,
  that call's complete conversation, untruncated:
  - every message;
  - every tool call with its input and result;
  - every file edit.

  It is read from Claude Code's session history for the call's recorded session ID. Each
  conversation MUST be shown with the milestone, trial, and step it belongs to.
- **FR-041** [K, 001 FR-070]: Secrets named in the configuration MUST be hidden in the embedded
  conversations, as everywhere else in the dashboard. The page header MUST state that it contains
  full Claude Code conversations and should be reviewed before sharing.
- **FR-042** [I, from FR-040 + FR-037]: When each call ends, its conversation MUST be copied into
  the workspace, with configured secrets hidden. The full dashboard then does not depend on Claude
  Code's history still holding it. A conversation that cannot be found (an interrupted call, or
  history cleared before the copy) MUST be shown as unavailable, with its session ID, and MUST NOT
  stop the command. Conversations of calls made before this feature are read from the history when
  still present.

#### Live dashboard

- **FR-042a** [Clarifications 2026-10-07]: `devloops dashboard --serve` MUST serve, until stopped,
  the full dashboard of each of the project's workspaces, with the same views, file viewer, and
  conversation viewer as FR-035 and FR-040. It MUST load a file or a conversation only when it is
  opened, with no size limit, and MUST let the reader switch between workspaces. While a run goes
  on, an open page MUST show changes within seconds, replacing only what changed and keeping the
  reader's place (the page shown, open folders, filters, the file open in the viewer). Search MUST
  cover the text of every file and conversation.
- **FR-042b** [Clarifications 2026-10-07]: The server MUST be read-only and MUST listen on
  127.0.0.1 unless `--host` names another address; on a loopback address it MUST answer only
  requests addressed to a loopback name. It MUST send only files its page lists, inside the
  workspace or recorded as inputs, never a path taken from the request, and every text it sends
  MUST have configured secrets hidden (FR-041). Listening beyond this machine, it MUST require a
  token by default (random, or `--token`; `--no-token` drops it), given in the URLs it prints and
  then kept in a cookie, and MUST warn that anyone with access sees code, prompts, and
  conversations over plain HTTP.
- **FR-042c** [I, from FR-039]: While it runs, the server MUST record its URL and process ID
  outside the project, so other commands print its URL instead of the command; a second `--serve`
  MUST print the running one's URL and exit 0. The record MUST be removed when it stops.
- **FR-042d** [Clarifications 2026-10-07]: No command MUST start the server itself.

#### Compatibility and documentation

- **FR-033** [K]: All 001 behavior (statuses, exit codes, state layout inside a workspace,
  dashboard, recovery) MUST be unchanged inside a workspace. Existing workspaces MUST remain
  readable by `status` and `dashboard`.
- **FR-034** [C, Principle IX]: The README MUST document:
  - installation, `init`, `check`, and `--upgrade`;
  - the project layout and the configuration precedence;
  - the visible-browser setting and prompt overrides;
  - the spec-kit bridge, and a migration note for using the devloops repository itself.

### Key Entities

- **Installed devloops**: the tool and its packaged files (loop definitions, prompts, schemas,
  hooks, default configuration, skills). It has one version and is never written by runs.
- **Project**: a directory containing `.devloops/`. It is found from the current directory, and its
  root anchors relative paths.
- **Project configuration**: `.devloops/devloops.json`. It holds project defaults between the
  packaged defaults and per-run options.
- **Local configuration**: `.devloops/devloops.local.json`, optional and git-ignored. It holds
  one developer's machine-specific settings and accepts the same keys as the project
  configuration.
- **Install manifest**: `.devloops/manifest.json`. It holds the devloops version and the
  fingerprint of each file `init` installed, and it drives upgrades and version warnings.
- **Prompt override**: a project file that replaces a packaged prompt with the same relative path.
- **Skill**: a Claude Code skill installed by `init` that runs one devloops command.
- **Spec-kit feature**: a `specs/<feature>/` folder with `spec.md` and optionally `plan.md` and
  `tasks.md` (phases of task IDs, optionally labelled with user stories). The active one is
  recorded by spec-kit.
- **Workspace**: unchanged from 001. Its default location moves under the project's `.devloops/`.
- **Full dashboard**: a self-contained, timestamped file that embeds all of a workspace's evidence,
  artifacts, and conversations as of when it was generated (`devloops dashboard --export`). It is
  the shareable record of a run when workspaces are not committed.
- **Live dashboard**: the full dashboard served by `devloops dashboard --serve`, loading files and
  conversations when opened and following runs as they go.
- **Summary page**: `<workspace>/dashboard.html`, written when a command pauses, stops, or ends.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A developer goes from a project with no devloops files to a first loop run with at
  most three commands (install, initialize, run), with no files edited by hand. The exception is
  the requirements, if they are not already configured.
- **SC-002**: After initialization and configuration, starting either loop or the orchestrator
  needs 0 path arguments on the command line.
- **SC-003**: Initializing a fresh project creates files only in `.devloops/`, the skills folder,
  and the ignore file: 0 other paths are created or changed.
- **SC-004**: An upgrade preserves 100% of the installed files the developer changed, and updates
  100% of those they did not.
- **SC-005**: With each prerequisite removed in turn, the readiness check names that prerequisite
  and its fix in 100% of cases.
- **SC-006**: Two initialized projects on one machine run loops without sharing any workspace,
  configuration, or prompt override.
- **SC-007**: One real end-to-end run reaches *completed* in a fresh project set up only with the
  README's commands, using a spec-kit feature as input. This repeats the T076 approach.
- **SC-008**: The existing offline test suite and the existing committed workspaces keep working:
  0 test regressions, and `status` and `dashboard` succeed on every committed workspace.
- **SC-009**: A full dashboard copied alone to another machine, with no network, shows 100% of
  the run's evidence and artifacts. Every screenshot and file opens from the page. 100% of the
  recorded calls whose conversation was available when it was generated can be read in full.
- **SC-010**: 0 configured secret values appear anywhere in a full dashboard, including the
  embedded conversations.

## Assumptions

- **A-1**: Claude Code is the only supported agent. spec-kit supports other agents, but devloops
  depends on Claude Code features (structured output, sessions, hooks), so other agents are out of
  scope.
- **A-2** (confirmed in Clarifications): Workspaces are excluded from version control in initialized
  projects by default. This is unlike 001 A-4, where the devloops repository commits its workspaces
  as deliverables. The full dashboard (FR-035) is the shareable record instead. Projects can opt out
  of the ignore rule (FR-004).
- **A-3**: The devloops repository keeps its committed workspaces in `workspaces/` by setting the
  workspaces location (FR-012) and becomes an initialized project itself. Its current `loops-*`
  skills are replaced by the installed skills (FR-022).
- **A-4**: Installation uses the language ecosystem's standard tool installer from the repository
  URL. Publishing to a public package index is out of scope.
- **A-5**: The minimum supported Claude Code version for `check` is the one used in T076 (2.1.283),
  until a newer one is proven.
- **A-6**: The spec-kit bridge reads spec-kit's files and its active-feature record only. It
  neither calls nor requires the spec-kit tool.

### Out of Scope

- Uninstalling devloops from a project (deleting `.devloops/` and the skills by hand is enough).
- Agents other than Claude Code; publishing to a public package index.
- Running Claude Code interactively inside a loop (calls stay non-interactive; see the visible
  browser for watching validation).
- Changes to loop planning, validation, or orchestration behavior.
