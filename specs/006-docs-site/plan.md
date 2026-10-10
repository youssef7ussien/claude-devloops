# Implementation Plan: Documentation Site

**Branch**: `main` (no feature branch) | **Date**: 2026-10-10 |
**Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/006-docs-site/spec.md`. Every decision in it was
agreed with the developer in conversation; no clarification session was needed.

**Decision tags**: the same as the earlier plans.

| Tag | Meaning |
|-----|---------|
| **[ER]** | Explicit requirement (spec FR or SC) |
| **[RD]** | Repository-derived (verified in this repository) |
| **[RC]** | Recommendation (the rationale is in [research.md](./research.md), R-n) |

## Summary

devloops' manual becomes a documentation website for people new to devloops, built with Zensical
from `docs/` and published to GitHub Pages, and kept true to the code by generated reference pages
and tests.

**What changes**:
- **The site:** `zensical.toml` and `docs/` at the repository root; tabs Home, Getting started, How
  it works, Guides, Reference, Contributing; a glossary whose terms also show as hover definitions;
  Mermaid diagrams for every flow and set of statuses [ER: FR-001, FR-003, FR-005–FR-012; RC: R-1,
  R-3, R-12].
- **Writing standard:** plain language for a reader new to devloops; each term explained where it
  is first used or linked to the glossary; a mention of a command, key, step, status or exit code
  links to its reference entry; written down in `contributing/writing-style.md` [ER: FR-014–FR-016;
  RC: R-7].
- **Generated reference:** `tools/docs/gen_reference.py` writes `docs/reference/` from the parser,
  the schemas, `claude.STEPS`, the exit codes and the statuses; meanings the code does not hold are
  in `tools/docs/descriptions.json`; missing config descriptions are added to the schemas [ER:
  FR-017; RC: R-5, R-6].
- **Examples and screenshots from a real run:** `tools/docs/examples.py` runs devloops against the
  stand-in Claude Code and writes the outputs pages include; `tools/docs/screenshots.mjs` captures
  the dashboard of that run [ER: FR-019; RC: R-9, R-10].
- **Tests:** `test_docs.py` fails when a reference page, an example, a description, a source list,
  a command, an option or a workspace path drifts; the strict build fails on broken links and
  anchors [ER: FR-002, FR-017, FR-018, FR-020; RC: R-2, R-7, R-8].
- **Publishing:** `.github/workflows/docs.yml` runs the docs tests and the strict build on every
  push and pull request, and deploys `main` to `https://youssef7ussien.github.io/claude-devloops/`
  [ER: FR-001, FR-002; RC: R-11].
- **The manual goes:** `loops/README.md` and `loops/orchestrator/README.md` are replaced by the
  site (every section mapped in `manual-map.md`); a short root `README.md` becomes the package
  description; the run skill, `bin/devloops`, a code comment and `CLAUDE.md` point at the site [ER:
  FR-022–FR-025; RC: R-12, R-13].

## Technical Context

**Language/Version**: Markdown pages; Python ≥ 3.10, standard library only, for the generator,
the example script and the tests [RD]; Node (already a test tool) for the screenshot script [RD];
the site builder needs Python ≥ 3.11 and runs only in CI and on writers' machines [RC: R-11].

**Primary Dependencies**: Zensical `0.0.69`, pinned, build-time only (not a devloops runtime
dependency) [RC: R-1]; GitHub Actions `checkout@v7`, `setup-python@v7`, `configure-pages@v6`,
`upload-pages-artifact@v5`, `deploy-pages@v5` [RC: R-11].

**Storage**: files in the repository (`docs/`, `docs-include/`, `tools/docs/`); the built site in
`site/` (git-ignored) [RC: R-1].

**Testing**: `unittest` (`loops/shared/tests/test_docs.py`), run by the full suite and by the docs
workflow; the strict site build, in the test when Zensical is installed and always in CI [RC: R-8].

**Target Platform**: a static site on GitHub Pages, read in current desktop and phone browsers
[ER: FR-003].

**Project Type**: documentation site inside the devloops repository.

**Performance Goals**: a change reaches the live site within 10 minutes of reaching `main` [ER:
SC-006]; the docs tests add under 30 seconds to the suite (the example run uses the stand-in
Claude Code) [RC: R-9].

**Constraints**: devloops stays standard-library only at runtime [RD: CLAUDE.md]; no application
specifics in examples (constitution II) [RD]; schemas stay byte-identical to their spec contracts
[RD: test_schemas_sync]; the docs describe the branch they are built from (FR-013).

**Scale/Scope**: about 35 pages (6 generated); the manual's 1,182 lines plus the orchestrator
README's are rewritten, not copied.

## Constitution Check

*GATE: checked before Phase 0 and again after Phase 1.*

| Principle | How this plan meets it | Result |
|-----------|------------------------|--------|
| I. Requirements-Driven | every page and check traces to FR/SC IDs; pages list their sources (FR-020) | Pass |
| II. Reusability | examples come from a generic sample application and plan (R-9); no application in the docs' examples | Pass |
| III. Incremental and Verifiable | the docs are "done" only when the tests and the strict build pass; pages land section by section | Pass |
| IV. Controlled Automation | no change to devloops' behavior (spec: out of scope); the status constants (R-5) replace literals without changing values, guarded by the existing suite | Pass |
| V. Bounded Execution | not affected | Pass |
| VI. Separation of Concerns | generator, examples, screenshots and tests are separate scripts; the site build is separate from devloops | Pass |
| VII. Existing Infrastructure First | reuses `build_parser()`, the schemas, `claude.STEPS`, the exit codes, the test helpers and fake Claude, and the CDP approach used for the dashboard | Pass |
| VIII. Testability and Traceability | drift in any generated fact fails the suite and names the page | Pass |
| IX. Documentation | the feature: the docs describe the implemented system and are tested against it | Pass |
| X. Simplicity | one new build-time dependency (Zensical), justified below; checks lean on the builder's own link validation instead of new tooling | Pass, see Complexity Tracking |

**Post-design re-check (after Phase 1)**: unchanged; the data model and contracts add no runtime
code to devloops beyond the status constants.

## Project Structure

### Documentation (this feature)

```text
specs/006-docs-site/
├── spec.md
├── plan.md              # this file
├── research.md          # R-1 … R-14
├── data-model.md        # pages, front matter, descriptions, examples
├── quickstart.md        # how to check the feature end to end
├── manual-map.md        # every manual section → its page, or dropped and why (created in tasks)
├── contracts/
│   ├── page-front-matter.md   # the front matter every hand-written page carries
│   ├── reference-pages.md     # what each generated page holds, and its source
│   ├── descriptions.md        # tools/docs/descriptions.json format
│   └── docs-tests.md          # what test_docs checks and how it reports
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
README.md                         # new: short front door, package description
zensical.toml                     # new: site configuration
docs/                             # new: the site's pages
├── index.md                      # landing page
├── getting-started/              # install.md, first-run.md
├── how-it-works/                 # index, run-lifecycle, steps, validation, trials-and-recovery,
│                                 # statuses, state-and-files, dashboard-data
├── guides/                       # backend-loop, frontend-loop, dashboard, approval-and-questions,
│                                 # configuration, prompts, spec-kit, skills, security, upgrades,
│                                 # limitations
├── reference/                    # GENERATED: commands, configuration, exit-codes, steps,
│                                 # statuses, state-files
├── glossary.md
├── contributing/                 # index, architecture, testing, specs-process, writing-style,
│                                 # documentation
└── assets/                       # screenshots/, diagrams' images if any
docs-include/                     # new: snippets (not pages)
├── abbreviations.md              # glossary terms as hover definitions
└── examples/                     # GENERATED: command outputs, workspace-files.txt
tools/docs/                       # new
├── requirements.txt              # zensical==0.0.69
├── gen_reference.py              # writes docs/reference/
├── descriptions.json             # meanings of exit codes, steps, statuses, files
├── examples.py                   # writes docs-include/examples/
└── screenshots.mjs               # writes docs/assets/screenshots/ (run by hand)
.github/workflows/docs.yml        # new: docs tests, strict build, deploy
loops/shared/tests/test_docs.py   # new
loops/shared/devloops/state.py    # status constants (R-5)
loops/shared/devloops/engine.py, orchestrator.py, selector.py   # use the constants
loops/shared/schemas/config.schema.json, project-config.schema.json   # descriptions (R-6)
specs/001-*/contracts/, specs/002-*/contracts/   # the same schema copies
loops/README.md, loops/orchestrator/README.md    # removed
pyproject.toml, CLAUDE.md, bin/devloops, loops/shared/devloops/initcmd.py,
loops/shared/skills/devloops-run/SKILL.md, loops/shared/tests/test_no_app_specifics.py,
.gitignore (site/)                # pointers and exclusions (R-13)
```

**Structure Decision**: the site lives at the repository root (`docs/`, `zensical.toml`), beside
`loops/`, because it documents the whole repository; the tooling that feeds it is in `tools/docs/`
so that nothing in `docs/` is a script, and snippets are in `docs-include/` so that the builder
does not treat them as pages (R-3).

## Phases (for /speckit-tasks)

1. **Scaffold and publishing**: `zensical.toml`, the empty navigation, `docs/index.md` stub, the
   workflow, `.gitignore`, `tools/docs/requirements.txt`; the strict build passes.
2. **Generated reference and its tests**: status constants, schema descriptions,
   `descriptions.json`, `gen_reference.py`, the six reference pages, `test_docs` checks 1–2 and 7.
3. **Examples**: `examples.py`, `docs-include/examples/`, `test_docs` check 6; the path list for
   check 4.
4. **Landing page and getting started** (P1 stories 1 and 3), the glossary, the writing style page.
5. **How it works** (P1 story 2), with the diagrams; `test_docs` checks 3–5.
6. **Guides** (P2 stories 4 and 5), screenshots for the dashboard guide (after the spec 005 work is
   merged).
7. **Contributing** (P3 story 6).
8. **Replacing the manual**: `manual-map.md`, root `README.md`, pointers, removal of the old
   READMEs, `CLAUDE.md`.
9. **Review and readers**: the independent review of every page (FR-021), the two readers
   (SC-001, SC-003), the walkthrough (SC-002).

## Complexity Tracking

| Addition | Why needed | Simpler alternative rejected because |
|----------|------------|--------------------------------------|
| Zensical as a build-time dependency | the site needs navigation, search, themes, diagrams and link validation (FR-002, FR-003) | hand-built HTML with the standard library would re-implement a static site generator; it stays out of devloops' runtime |
| A first CI workflow | the site must publish itself on every change (FR-001, SC-006) | publishing by hand is forgotten and lets the site drift from `main` |
| `descriptions.json` beside the code | the meanings of exit codes, steps and statuses exist nowhere in the code (R-5) | putting that prose into the driver's code moves documentation into runtime files |
