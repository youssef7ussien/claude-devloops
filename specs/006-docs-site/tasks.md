---
description: "Task list for the devloops documentation site"
---

# Tasks: Documentation Site

**Input**: Design documents from `specs/006-docs-site/` (plan.md, spec.md, research.md,
data-model.md, contracts/, quickstart.md)

**Tests**: requested by the spec (FR-002, FR-017, FR-018, FR-020): `loops/shared/tests/test_docs.py`
checks 1–7 ([contracts/docs-tests.md](./contracts/docs-tests.md)) are built with the parts they check.

**Organization**: by user story (spec.md). Every hand-written page follows
[contracts/page-front-matter.md](./contracts/page-front-matter.md) (`title`, `description`,
non-empty `sources`) and `docs/contributing/writing-style.md`: plain language for a reader new to
devloops; each devloops term explained where first used or linked to the glossary; every mention of
a command, option, configuration key, step, status or exit code links to its reference entry
(R-7). A page task is done when the page passes `test_docs` and `zensical build --strict`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: the user story (US1–US6) the task serves

---

## Phase 1: Setup

**Purpose**: the site builds and publishes, empty.

- [X] T001 Pin the site builder: `tools/docs/requirements.txt` with `zensical==0.0.69` (R-1); add `site/`, `.venv-docs/` and `.claude/worktrees/` to `.gitignore`
- [X] T002 Create `zensical.toml` at the repository root (R-1, R-3, R-12): `site_name = "devloops"`, `site_url = "https://youssef7ussien.github.io/claude-devloops/"`, `repo_url`, `docs_dir = "docs"`, `strict = true`; theme features `navigation.tabs`, `navigation.sections`, `navigation.indexes`, `navigation.top`, `search.highlight`, `content.code.copy`; light and dark palettes following the system setting with a toggle; `markdown_extensions` listing Zensical's default set (abbr, admonition, attr_list, def_list, details, footnotes, md_in_html, toc with permalink, pymdownx highlight, inlinehilite, keys, mark, tilde, tasklist, tabbed alternate_style, superfences with the `mermaid` custom fence) plus `pymdownx.snippets` with `base_path = ["docs-include"]`, `check_paths = true`, `auto_append = ["abbreviations.md"]`; `nav` with the tabs Home, Getting started, How it works, Guides, Reference, Glossary, Contributing and the pages of R-12
- [X] T003 Create the page skeleton: `docs/index.md` and one stub per page in `nav` (each with front matter `title`, `description`, `sources: [loops/README.md]` and one line "Being written."), `docs-include/abbreviations.md` (empty), `docs-include/examples/.gitkeep`, `docs/assets/screenshots/.gitkeep`; `zensical build --strict --clean` exits 0
- [X] T004 [P] Create `.github/workflows/docs.yml` (R-11): on `push` to `main` and on `pull_request`, with `paths` `docs/**`, `docs-include/**`, `tools/docs/**`, `zensical.toml`, `loops/**`, `.github/workflows/docs.yml`; job `build`: `actions/checkout@v7`, `actions/setup-python@v7` (`python-version: "3.12"`), `pip install -r tools/docs/requirements.txt`, `python -m unittest discover -s loops/shared/tests -p test_docs.py` (env `VISUAL=true EDITOR=true`), `zensical build --strict --clean`, and on `main` only `actions/configure-pages@v6`, `actions/upload-pages-artifact@v5` (`path: site`); job `deploy` (needs `build`, `main` only, `environment: github-pages`, permissions `pages: write`, `id-token: write`): `actions/deploy-pages@v5`; no caching
- [X] T005 Create `loops/shared/tests/test_docs.py` with check 7 (contracts/docs-tests.md): run `zensical build --strict --clean` from the repository root (it writes the git-ignored `site/`; Zensical has no output-folder option) and fail with its output when it exits non-zero; skip when `zensical` is not on PATH (as test_app_js skips without node); a helper `pages()` that yields every `docs/**/*.md` with its parsed front matter (a small stdlib YAML-subset reader for `key: value`, `key: >-` and lists)

**Checkpoint**: an empty site builds strictly and the workflow is ready to publish it.

---

## Phase 2: Foundational

**Purpose**: what every page depends on: the reference pages they link to, the examples they
include, the writing standard, the glossary, and the checks that keep them true.

**⚠️ No content page is finished before this phase is.**

### Code values the reference reads (R-5, R-6)

- [X] T006 Add `RUN_STATUSES`, `MILESTONE_STATUSES`, `TASK_STATUSES`, `TRIAL_STATUSES` tuples to `loops/shared/devloops/state.py` (values from research R-5's table, as the code writes them today) and use them instead of string literals where those statuses are set or compared in `engine.py`, `orchestrator.py` and `selector.py`; no value changes; add a test (in `test_docs`) that every milestone, task, trial and run status written by those modules is one of the constants (scan for `"status"` assignments with string literals); full suite passes
  - *Done differently:* the modules keep their string literals (a tuple lookup such as `MILESTONE_STATUSES[2]` reads worse, and named constants would collide: `failed` is a milestone, task and trial status); `test_docs` checks both ways instead: every status literal they write or compare is in the constants, and every constant is written
- [X] T007 [P] Add a `description` to every key without one in `loops/shared/schemas/config.schema.json` and `loops/shared/schemas/project-config.schema.json` (R-6; read the current keys, since spec 005 removed the `dashboard.*` settings), plain language per the writing style; copy both files byte-for-byte to their contract copies in `specs/001-reusable-dev-loops/contracts/` and `specs/002-devloops-init/contracts/`; `test_schemas_sync` passes
- [X] T008 [P] Create `tools/docs/descriptions.json` (contracts/descriptions.md): `exit_codes` (every code in `state.EXIT_CODES`, `EXIT_USAGE`, `EXIT_LOCK_HELD`, the error classes' codes, 1 and 130; each `name`, `meaning`, `next`; state that an invalid run configuration exits 2, as the code does), `steps` (every key of `claude.STEPS`), `statuses` (`run`, `loop`, `milestone`, `task`, `trial`, `approval`), `stop_reasons` (every `status_reason.code` in `run-state.schema.json`), `files` (state files without a schema); one or two plain sentences each, written from the code that sets each value

### Reference generator and its checks (US4's foundation)

- [X] T009 Create `tools/docs/gen_reference.py` (contracts/reference-pages.md): standard library only; puts `loops/shared` on `sys.path`; writes `docs/reference/commands.md` (walk `cli.build_parser()`: each command's help, usage, options with argument, default and help, mutually exclusive groups, global options; leave out `argparse.SUPPRESS` options; a "Removed options" table from `cli.REMOVED_DASHBOARD_FLAGS` if it still exists), `configuration.md` (merge order from `config.py`'s docstring; one entry per dotted key of both schemas: type, allowed values, default, description), `exit-codes.md`, `steps.md` (driver order, writes, tools, output schema name), `statuses.md`, `state-files.md` (from `docs-include/examples/workspace-files.txt`, the schemas and `descriptions.json`); every entry has the explicit anchor of data-model.md "Reference entry"; each page starts with front matter `generated: true` and the note "This page is generated from devloops' code; do not edit it."; deterministic output; `--check` writes nothing, prints each differing file and exits 1
- [X] T010 Add `test_docs` checks 1 and 2: `gen_reference.py --check` exits 0 (else fail with the files it names); `descriptions.json` keys equal the code's values per group (fail with "add a description for X" / "X no longer exists")

### Examples from a real run (R-9)

- [X] T011 Create `tools/docs/examples.py`: reuse `loops/shared/tests/helpers.py` (`TempEnv`, `write_scenario`, `run_cli`) and `samples.py` (`plan()`) with the backend loop's `fixtures/http_app.py` as a generic sample application; run `init`, `check`, `run` (pausing for approval), `approve`, `status`, `status --json` and `dashboard --export`; write each output to `docs-include/examples/<command>.txt` with temporary paths replaced by `<project>`, timestamps by `2026-01-01T00:00:00Z`, durations by `1s`, costs and token counts kept as the stand-in reports them; write `docs-include/examples/workspace-files.txt` (every file the run wrote, workspace-relative, sorted, numbers in milestone/trial/sequence folders kept); `--check` compares instead of writing and exits 1 naming differing files; no application specifics (constitution II)
- [X] T012 Generate the examples and the reference pages (`python3 tools/docs/examples.py`, then `python3 tools/docs/gen_reference.py`); commit-ready output in `docs-include/examples/` and `docs/reference/`
- [X] T013 Add `test_docs` checks 3, 4 and 6: front matter per contracts/page-front-matter.md (hand-written pages: non-empty `title`, `description`, `sources`; each source path exists; each `spec NNN ID` exists in that spec's `spec.md` or `research.md`); every `devloops …` command line in code blocks and inline code names a known command and known options (`cli.build_parser()`); every inline-code configuration key (a dotted name such as `unit_tests.command`, or a word that is the name of a top-level key in either schema) is a key of `config.schema.json` or `project-config.schema.json` (FR-018); every inline-code workspace path (`state/…`, `outputs/…`, `run/…`, `<loop>/…`) matches a line of `workspace-files.txt` with `<id>`, `<n>`, `<seq>`, `<loop>`, `<NN>`, `<slug>` as wildcards; `examples.py --check` exits 0; every failure names file, line and item

### Writing standard and glossary (FR-014–FR-016)

- [X] T014 [P] Write `docs/contributing/writing-style.md`: who the reader is (spec Assumptions: knows a terminal, web apps, APIs, tests; not devloops or Claude Code's headless mode); rules (plain words, short sentences, active voice, what and why before how, one idea per paragraph, no source code needed); explaining a term where first used or linking the glossary; linking every command, option, key, step, status and exit code to its reference anchor (with examples of each link form); diagrams for flows and statuses (Mermaid); examples only from `docs-include/examples/` via snippets; front matter and `sources`; three before/after examples of a sentence made plain
- [X] T015 [P] Write `docs/glossary.md` and `docs-include/abbreviations.md`: one entry per devloops term (at least: requirements, story, plan, milestone, task, acceptance criterion, check, trial, step, call, validation, evidence, target, workspace, project, loop, backend-dev, frontend-dev, handoff, approval, open question, assumption, suggested answer, retry granted, contract (OpenAPI), runtime, stand-in, dashboard, export, headless Claude Code); each glossary entry a heading with an explicit anchor, a plain definition and a link to where it is explained in depth (stub pages until written); each abbreviation line `*[term]: one-line definition`; add a `test_docs` assertion that every term in `abbreviations.md` has a glossary entry and the reverse

**Checkpoint**: reference pages, examples, writing standard and glossary exist and are checked;
content pages can be written in parallel.

---

## Phase 3: User Story 1 - Understand what devloops is in a few minutes (Priority: P1) 🎯 MVP

**Goal**: the landing page tells a newcomer what devloops is, why to trust it, and where to start.

**Independent Test**: someone new to devloops reads only `docs/index.md` and can say what devloops
does, why its results can be trusted, and what they would do first (SC-001).

- [X] T016 [US1] Write `docs/index.md` (FR-006): what devloops is (two sentences), the problem it solves, the core idea (a milestone passes only when devloops' own validation passes, never on the model's word), a Mermaid diagram of the cycle requirements → plan → approval → per milestone (implement → validate → pass, or fix and try again) → validated application, the two loops in one paragraph each, key features (validation by real HTTP requests and a real browser, bounded trials, recovery, the dashboard, spec-kit input), what is needed (Python ≥ 3.10, Claude Code, Node for the frontend loop), and cards linking to Getting started, How it works, Guides and Reference; front matter `sources` (spec 001, 003, 005 FR IDs used; `loops/shared/devloops/engine.py`, `orchestrator.py`, `validators/`)
- [X] T017 [P] [US1] Write the root `README.md` (FR-023, R-13), about 80–120 lines: what devloops is, the core idea, requirements, a five-command quick start taken from `docs-include/examples/`, links to the site's sections at `https://youssef7ussien.github.io/claude-devloops/`, license; no front matter (it is not a site page)

**Checkpoint**: the landing page and the front door are ready.

---

## Phase 4: User Story 2 - Learn how a run works, end to end (Priority: P1)

**Goal**: "How it works" explains the whole run so a reader needs no source code.

**Independent Test**: after reading `docs/how-it-works/`, a reader new to devloops says what happens
after a failed check, a milestone out of trials, an interruption, and an open question (SC-003).

- [ ] T018 [US2] Write `docs/how-it-works/index.md`: the big picture in one page: requirements in, plan, approval, milestones one at a time, each in trials, validation decides, outputs; a Mermaid flowchart of a whole run including both loops and the handoff; links to each page of the section
- [ ] T019 [P] [US2] Write `docs/how-it-works/run-lifecycle.md` (FR-007): planning (what the plan holds and how devloops checks it), approval (automatic with suggested answers, or reviewed), milestones in dependency order, completion and the final report; which loops a run includes and in what order (the manual's "Which loops a run includes"); the progress output while it runs (phases, `--quiet`/`--verbose`, `run.log`, the manual's "Progress"); a sequence diagram per loop and one for the whole run (from the manual's "How a run works", rewritten to the writing style); `sources`: `engine.py`, `orchestrator.py`, spec 001/003 IDs
- [ ] T020 [P] [US2] Write `docs/how-it-works/steps.md` (FR-007): each step (plan, replan, author checks, implement, fix, validate the UI) as a section: why it exists, what Claude is given (the prompt's parts), what it may do (tools, writing only in implement and fix), what it must return, how devloops checks the answer; a flowchart of one step (prompt parts → call → answer checked against its schema → recorded); link each step to `reference/steps.md#step-<name>`; `sources`: `claude.py`, `prompts.py`, `loops/shared/prompts/steps/`
- [ ] T021 [P] [US2] Write `docs/how-it-works/validation.md` (FR-007): what passes and fails a backend milestone (frozen checks, the runtime, curl, criteria, the OpenAPI contract, unit tests, the write audit) and a frontend milestone (the UI runtime, unit tests, the validate-ui call with the browser, evidence, the network log against the contract); why the model's word never counts; the failure reasons; a flowchart for each loop's validation; `sources`: `validators/curl.py`, `validators/playwright.py`, `validators/unit_tests.py`, `boundary.py`
- [ ] T022 [P] [US2] Write `docs/how-it-works/trials-and-recovery.md` (FR-007): what a trial is and what it sees, implement then fix, `max_trials`, running out of trials and retries granted (`continue`), questions raised during a trial, processes Claude starts, interruption and resuming from the state files, voided trials; the manual's "one milestone, three trials" example rewritten; `sources`: `engine.py`, `selector.py`, `state.py`
- [ ] T023 [US2] Write `docs/how-it-works/statuses.md` (FR-008): one Mermaid `stateDiagram-v2` per kind (run, loop, milestone, task, trial, plan approval) with every value of that kind and a sentence per transition saying what causes it; link each status to `reference/statuses.md#<kind>-<status>`; the stop reasons as a table linking the reference
- [ ] T024 [US2] Add `test_docs` check 5: each status value of each kind (the constants of T006 and the schema enums) appears in that kind's diagram on `docs/how-it-works/statuses.md`; fail naming the kind and the value
- [ ] T025 [P] [US2] Write `docs/how-it-works/state-and-files.md` (FR-007): the project, workspaces and the target; what devloops writes and when (plan, run state, call records, transcripts, events, trial folders with evidence, outputs), atomic writes, why a run can resume from them; a tree from `docs-include/examples/workspace-files.txt` (included, not typed); link to `reference/state-files.md`
- [ ] T026 [P] [US2] Write `docs/how-it-works/dashboard-data.md` (FR-007): the server reads only the workspace files and writes nothing; one JSON answer per view, redacted; how the browser follows a run (the workspace version, refreshing only the open view); the live "now" panel; search; the export (the same answers inside one file); a sequence diagram; `sources`: `serve.py`, `dashboard.py`, `artifacts.py`, `assets/app/api.js`, spec 005 IDs
- [ ] T027 [P] [US2] Write `docs/guides/backend-loop.md` and `docs/guides/frontend-loop.md`: each loop's purpose, inputs, what it builds and publishes (OpenAPI document; UI address), how it is validated (linking `how-it-works/validation.md`), the handoff, backend-only projects; `sources` per loop

**Checkpoint**: "How it works" is complete and checked; US1 + US2 explain devloops fully.

---

## Phase 5: User Story 3 - Get a first run working (Priority: P1)

**Goal**: a reader goes from nothing to a first run with only "Getting started".

**Independent Test**: follow `docs/getting-started/` word for word on a fresh sample project; every
command works and every output looks as shown (SC-002).

- [ ] T028 [US3] Write `docs/getting-started/install.md`: requirements (Python ≥ 3.10, Claude Code logged in, Node and Playwright for the frontend loop, `uv` or `pip`), installing devloops (as the manual's "Install" says, checked against `pyproject.toml`), checking the install (`devloops --version`); `sources`: `pyproject.toml`, `bin/devloops`
- [ ] T029 [US3] Write `docs/getting-started/first-run.md` (FR-009): `devloops init` in an application folder, what it creates, writing requirements, `devloops check`, `devloops run`, reviewing the plan and `devloops approve`, following it (progress output and `devloops dashboard`), where the results are (`outputs/`), and a table "the run stopped: what it means, what to do" linking `reference/exit-codes.md`; every output included from `docs-include/examples/`; `sources`: `cli.py`, `initcmd.py`, `checkcmd.py`, spec 002/003 IDs
- [ ] T030 [US3] Walk through `docs/getting-started/` on a fresh sample project (the sample application of T011 in a new folder), following the text exactly; fix every step that fails or differs; record the result in `specs/006-docs-site/quickstart.md` under "Getting started works"

**Checkpoint**: P1 stories done: the site explains devloops and gets a reader to a first run (MVP).

---

## Phase 6: User Story 4 - Look up exact details (Priority: P2)

**Goal**: guides answer "how do I…" and the reference answers "what exactly…", matching the code.

**Independent Test**: pick any command option, configuration key or exit code at random; the
reference page agrees with devloops (quickstart "Drift is caught").

- [ ] T031 [P] [US4] Write `docs/guides/configuration.md`: where configuration lives (project file, local file, workspace file, `--config`, flags) and which wins, the most used keys with when to change them (each linking `reference/configuration.md#<key>`), models per step, the visible browser; `sources`: `config.py`, `project.py`, `defaults.json`
- [ ] T032 [P] [US4] Write `docs/guides/approval-and-questions.md`: reviewing a plan, `approve`, `replan`, `retry`, open questions and suggested answers, the `questions` modes, questions during implementation, reviewing accepted suggestions; `sources`: `engine.py`, `cli.py`, spec 001/003 IDs
- [ ] T033 [P] [US4] Write `docs/guides/prompts.md` (prompt overrides: the files, what each part is, how an override applies; linking `reference/steps.md`) and `docs/guides/spec-kit.md` (using a spec-kit feature as requirements); `sources`: `prompts.py`, `inputs.py`, `loops/shared/project/prompts/README.md`
- [ ] T034 [P] [US4] Write `docs/guides/skills.md` (the Claude Code skills `devloops init` installs: what each does, when to use it), `docs/guides/upgrades.md` (upgrading devloops and the installed files, kept local changes) and `docs/guides/limitations.md` (known limitations from the manual and spec follow-ups, including the exit-code question of R-5); `sources` per page
- [ ] T035 [P] [US4] Write `docs/guides/security.md` (FR-011): secrets kept out of recorded data (redaction, `secrets` settings), Claude's writes kept inside the target (hook and audit), the dashboard server's protections (local address, token, host check, read-only, content security policy); `sources`: `redact.py`, `boundary.py`, `loops/shared/hooks/`, `serve.py`
- [ ] T036 [US4] Read each generated page in `docs/reference/` as a newcomer would and fix wording at its source (argparse `help=` in `cli.py`, schema descriptions, `descriptions.json`), then regenerate; add `docs/reference/index.md` (hand-written: what each reference page holds); check quickstart scenarios "Drift is caught", "Broken link is caught" and "Unknown path is caught"

**Checkpoint**: reference and guides done.

---

## Phase 7: User Story 5 - Use the dashboard and understand what it shows (Priority: P2)

**Goal**: every dashboard view and number is explained, with screenshots from a real run.

**Independent Test**: with `docs/guides/dashboard.md` beside a real dashboard, a reader names what
every view and headline number shows.

- [ ] T037 [US5] Create `tools/docs/screenshots.mjs` (R-10): run `examples.py`'s sample run (or reuse its workspace via an argument), start `devloops dashboard --daemon` on a free port, drive headless Chromium over the DevTools protocol at 1400×900, light theme, and save one PNG per view (overview, run, loop, trial, Claude calls, a conversation, files with the viewer, questions, events, search) to `docs/assets/screenshots/<view>.png`; stop the server; usage note at the top
- [ ] T038 [US5] Run `node tools/docs/screenshots.mjs` and commit the screenshots
- [ ] T039 [US5] Write `docs/guides/dashboard.md` (FR-010): starting it (`devloops dashboard`, `--daemon`, `--stop`, the port), each view with its screenshot and what it answers, each number (cost, tokens, cache hit rate, first-try pass rate, cost per achieved milestone, step shares) and how it is worked out, search, following a live run, the export and what it contains and leaves out; link `how-it-works/dashboard-data.md`; `sources`: `dashboard.py`, `assets/app/views/`, spec 005 FR IDs

**Checkpoint**: dashboard documented.

---

## Phase 8: User Story 6 - Contribute to devloops (Priority: P3)

**Goal**: a contributor knows how the code is organised, how to test, how features are specified,
and how to keep the docs true.

**Independent Test**: from `docs/contributing/architecture.md` alone, a contributor names the part
that runs a backend check, and runs the suite from `testing.md`.

- [ ] T040 [P] [US6] Write `docs/contributing/architecture.md` (FR-012): kit vs project, the driver flow `cli.py → orchestrator.py → engine.py → claude.py`, validators, the write boundary, state as files, the dashboard server and app, with a Mermaid diagram and one sentence per part (from CLAUDE.md's Architecture, rewritten for humans); `sources`: those files
- [ ] T041 [P] [US6] Write `docs/contributing/index.md` (how to contribute, Conventional Commits, where things are) and `docs/contributing/testing.md` (the full suite, one module, the browser tests, `DEVLOOPS_TEST_PACKAGING`, `DEVLOOPS_SKIP_PERF`, the fake Claude and scenarios, rules the tests enforce); `sources`: `CLAUDE.md`, `loops/shared/tests/helpers.py`, `fake_claude.py`
- [ ] T042 [P] [US6] Write `docs/contributing/specs-process.md` (spec-kit, `specs/NNN-*`, the constitution, requirement IDs in code comments, "Changed by / Revised by spec NNN" notes now on site pages) and `docs/contributing/documentation.md` (the documentation rule: behavior changes update the pages in the same commit; how to regenerate reference and examples; screenshots by hand; how `test_docs` and the strict build report; the independent review before a page's first publish; upgrading Zensical deliberately); `sources`: `.specify/memory/constitution.md`, `tools/docs/`

**Checkpoint**: all stories done.

---

## Phase 9: Replacing the manual and publishing

**Purpose**: the site replaces `loops/README.md`, everything points at it, and it is checked and live.

- [ ] T043 Write `specs/006-docs-site/manual-map.md` (SC-008): every heading of `loops/README.md` and `loops/orchestrator/README.md` (file:line) → its new page and section, or "dropped" with the reason; fill any gap it shows in the pages
- [ ] T044 Point everything at the site (FR-023, FR-024, R-13): `pyproject.toml` `readme = "README.md"`; `loops/shared/skills/devloops-run/SKILL.md` links the recovery page at `https://youssef7ussien.github.io/claude-devloops/how-it-works/trials-and-recovery/`; the `bin/devloops` docstring and the `initcmd.py` comment cite site pages; `loops/shared/tests/test_no_app_specifics.py` excludes `docs/`, `docs-include/` and `README.md` instead of `loops/README.md` and `loops/orchestrator/README.md`
- [ ] T045 Update `CLAUDE.md` (specs in `specs/` that mention `loops/README.md` stay as they are, FR-025): user documentation is the site in `docs/` (built with Zensical, published by `.github/workflows/docs.yml`); "Changed by / Revised by spec NNN" notes and "describe the system as built" apply to `docs/` pages; generated pages are regenerated, never edited; the docs commands (`gen_reference.py`, `examples.py`, `test_docs`, `zensical serve`)
- [ ] T046 Remove `loops/README.md` and `loops/orchestrator/README.md` (FR-022); replace every `sources: [loops/README.md]` left from T003 (none may remain); `test_packaging` passes with the root README as the package description (`DEVLOOPS_TEST_PACKAGING=1`)
- [ ] T047 Independent review (FR-021, R-14): for each hand-written page, a separate agent reads the page against its `sources` and lists every statement it cannot confirm and every devloops term that is neither explained where first used nor linked to the glossary (FR-015, SC-007), and anything that describes planned or removed behavior as current (FR-013); fix or remove each; record the pages reviewed in `specs/006-docs-site/quickstart.md`
- [ ] T048 Readers (SC-001, SC-003, R-14): the two readers the developer names read `index.md`, then `how-it-works/`; record their answers and fix what they misunderstood
- [ ] T049 Run the full suite (`VISUAL=true EDITOR=true DEVLOOPS_TEST_PACKAGING=1 python3 -m unittest discover -s loops/shared/tests`) and `zensical build --strict --clean`; both pass
- [ ] T050 Publish: the developer switches Pages on (Settings → Pages → Source: GitHub Actions); push to `main`; the workflow passes and the site is live within 10 minutes (SC-006); check the landing page, search, the dark theme, a diagram and a phone-width page on the live site

---

## Dependencies & Execution Order

- **Setup (T001–T005)** → **Foundational (T006–T015)** → story phases → **Phase 9**.
- Within Foundational: T006–T008 before T009; T011–T012 before T013 and before `state-files.md`
  is meaningful; T009–T010 and T011–T013 can proceed side by side once T006–T008 are done; T014,
  T015 in parallel with all of them.
- **US1 (T016–T017)**, **US2 (T018–T027)**, **US3 (T028–T030)** need only Foundational; they
  can be written in parallel. T024 needs T023. T030 needs T028–T029.
- **US4 (T031–T036)**, **US5 (T037–T039)**, **US6 (T040–T042)** need only Foundational. T038 needs
  T037; T039 needs T038.
- **Phase 9**: T043 after all content; T044–T046 after T043; T047 after all pages; T048 after T016
  and Phase 4; T049 after T044–T047; T050 last.

## Parallel Examples

- Foundational: T007, T008, T014, T015 together; then T009 and T011 together.
- US2: T019, T020, T021, T022, T025, T026, T027 together (one file each), then T023 → T024.
- US4: T031, T032, T033, T034, T035 together, then T036.
- US6: T040, T041, T042 together.

## Implementation Strategy

1. **MVP**: Setup + Foundational + US1 (landing page, README) + US2 (How it works) + US3 (Getting
   started). At that point the site explains devloops and gets a reader to a first run; it can be
   published (T050) even before the manual is removed, since both describe the same system.
2. **Increment 2**: US4 guides and the reference read-through; US5 dashboard with screenshots.
3. **Increment 3**: US6 contributing; then Phase 9 replaces the manual, reviews, readers, publish.
