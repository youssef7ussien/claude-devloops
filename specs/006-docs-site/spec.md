# Feature Specification: Documentation Site

**Feature Branch**: `main` (no branch hook configured)

**Created**: 2026-10-10

**Status**: Draft

**Input**: User description: "Create the devloops documentation site, published to GitHub Pages and
built with Zensical (pinned version) from a `docs/` folder. It replaces `loops/README.md`; a short
root `README.md` links to the site. The audience is people new to devloops: the writing is plain
and simple, each technical term is explained where it is first used, there is a glossary, and
readers never need the source code. It includes a landing page; getting started; how it works (the
run lifecycle, the steps plan/approve/implement/fix/validate, statuses as diagrams, validation,
trials and recovery, the state files, and how the dashboard gets its data); the backend and
frontend loops; the dashboard; commands; configuration; security; skills; upgrades; limitations;
and a contributing section (architecture map, tests, specs process, writing style). Accuracy:
reference pages (commands, options, config keys and defaults, exit codes, steps, statuses, state
file formats) are generated from the code, and a test fails if they drift. Tests check that
commands, flags, config keys, workspace paths and internal links in the hand-written pages exist,
and that the site builds with no warnings. Examples and screenshots come from real runs. Each page
lists the sources it was checked against. Update `pyproject.toml`'s readme, the run skill (site
URL), and CLAUDE.md's docs rule." The developer agreed each decision in conversation before this
spec was written: replace the manual rather than keep it, Zensical as the site builder, GitHub
Pages as the host, and the accuracy layers above.

## Scope and Source Classification

**Problem**: devloops' only user documentation is one 1,182-line Markdown file
(`loops/README.md`). It is accurate and complete for someone who already knows devloops, but a
newcomer meets it as a long wall of reference text: there is no landing page that says what
devloops is and why it exists, no single picture of how a run moves from requirements to working
code, no explanation of what the statuses mean or how the dashboard knows what it shows, and
many terms (trial, milestone, check, handoff, workspace) are used before they are explained. It
can only be read on GitHub or in the package description, and nothing stops it from drifting
from the code except reviewers' care.

**In scope**:
- a public documentation website for devloops, built from Markdown pages kept in the repository
  and published automatically when they change;
- a landing page, getting started, how it works, the two loops, the dashboard, commands,
  configuration, security, skills, upgrades, limitations, a glossary, and a contributing section;
- a writing standard for the whole site: plain language for readers new to devloops;
- reference pages generated from the code, and tests that keep every page true to the code;
- replacing `loops/README.md` with the site, and a short root `README.md` that links to it;
- updating what points at the old manual: the package description, the installed run skill,
  the project's contributor instructions, and code comments that cite manual sections.

**Out of scope**:
- documentation for more than one devloops version at a time (the site describes the current
  `main`);
- translations into other languages;
- a custom domain (the default GitHub Pages address is used);
- documentation shipped inside the installed package for reading offline;
- changes to devloops' behavior: where writing a page shows the behavior is wrong or confusing,
  it is recorded as a follow-up, not changed in this feature;
- publishing the `specs/` folder as part of the site (contributors are pointed to it in the
  repository).

**Source classification**: requirements below come from the developer's description and the
decisions confirmed in conversation; constitution principle IX ("documentation MUST reflect the
implemented system") and the project rule that the user documentation describes the system as
built. Choices made here where the description was silent are listed under Assumptions.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Understand what devloops is in a few minutes (Priority: P1)

A developer who has never heard of devloops opens the site. The landing page tells them, in plain
words, what devloops does (it has Claude Code build an application from written requirements,
one milestone at a time), why it can be trusted (a milestone passes only when devloops' own checks
pass, never because the model says it is done), what they need to try it, and where to go next.
A diagram shows the cycle from requirements to a finished, validated application.

**Why this priority**: the landing page decides whether anyone reads further. Without it, the
rest of the site serves only people who already use devloops.

**Independent Test**: give the landing page alone to someone new to devloops; afterwards they can
say in their own words what devloops does, why its results can be trusted, and what they would do
first to try it.

**Acceptance Scenarios**:

1. **Given** the published site, **When** a reader opens its address, **Then** the landing page
   explains what devloops is, the problem it solves, its core idea (validation by devloops, not
   by the model), its two loops, and its key features, and links to getting started and to how it
   works.
2. **Given** the landing page, **When** a reader looks for what they need to install, **Then**
   the requirements and a link to the install steps are on that page.
3. **Given** a reader who does not know a term used on the landing page (for example
   "milestone"), **When** they meet it, **Then** it is explained in that sentence or linked to
   the glossary.

---

### User Story 2 - Learn how a run works, end to end (Priority: P1)

A developer wants to know what actually happens when they run devloops: how requirements become
a plan, what approval is, what a milestone and a trial are, what happens in each step (plan,
approve, author checks, implement, fix, validate), what makes a milestone pass or fail, what
happens when it fails, how a stopped run resumes, what each status means, what devloops writes
to disk, and how the dashboard gets what it shows. They read "How it works" and understand all
of it without opening the source code.

**Why this priority**: understanding the loop is what lets people trust the results, choose the
right options, and act when a run stops. It is the gap the current manual leaves widest.

**Independent Test**: after reading "How it works", a reader new to devloops can trace a
milestone through its trials and say, for a given failure (a check failed, the run was stopped,
the milestone ran out of trials), what devloops does next and where to look.

**Acceptance Scenarios**:

1. **Given** the "How it works" section, **When** a reader follows it in order, **Then** it
   covers the run lifecycle; each step and what it is given, allowed to do, and must return;
   validation for each loop; trials, retries and recovery; the statuses of a run, a loop, a
   milestone, a trial and a plan approval; the files devloops keeps; and how the dashboard
   collects its data.
2. **Given** each set of statuses, **When** a reader looks it up, **Then** it is shown as a
   diagram of the states and what moves a run, loop, milestone or trial from one to the next.
3. **Given** the flow of a whole run, **When** a reader looks for it, **Then** a diagram shows
   the order of the loops, the steps inside a milestone, and the handoff from the backend loop to
   the frontend loop.
4. **Given** any concept in that section, **When** a reader wants the exact details (a field,
   a file name, an option), **Then** a link leads to the reference page that has them.

---

### User Story 3 - Get a first run working (Priority: P1)

A developer with an application to build installs devloops, sets up a project, checks the setup,
starts a run, reviews and approves the plan, follows the run in the dashboard, and finds the
results, following "Getting started" step by step.

**Why this priority**: a reader who cannot get a first run working does not become a user.

**Independent Test**: on a fresh sample project, follow "Getting started" word for word; every
command works as written and every result looks as the page describes.

**Acceptance Scenarios**:

1. **Given** a machine with the stated requirements, **When** a reader follows "Getting
   started", **Then** they reach a completed or paused-for-approval run without needing any other
   page.
2. **Given** a command shown on that page, **When** the reader runs it, **Then** it exists, its
   options exist, and its output looks like the example shown.
3. **Given** a run that stops or pauses, **When** the reader looks at the page, **Then** it tells
   them what the stop means and which command or page comes next.

---

### User Story 4 - Look up exact details (Priority: P2)

A developer already using devloops needs one exact fact: an option of a command, a configuration
key and its default, what an exit code means, what a state file contains. They find it in the
reference pages, and it matches what their installed devloops does.

**Why this priority**: reference lookups are the most frequent visits once someone uses
devloops, and a wrong fact here costs them a failed run.

**Independent Test**: pick any command option, configuration key or exit code at random and
compare the reference page with devloops' behavior; they agree.

**Acceptance Scenarios**:

1. **Given** the reference pages, **When** a reader looks up any command, **Then** they find
   every option it accepts with a plain description.
2. **Given** any configuration key devloops reads, **When** a reader looks it up, **Then** they
   find its meaning, type, allowed values and default.
3. **Given** a change to the commands, configuration, exit codes, steps, statuses or state
   files, **When** the repository's tests run without the reference pages being updated,
   **Then** a test fails and says which page is out of date.

---

### User Story 5 - Use the dashboard and understand what it shows (Priority: P2)

A developer opens the dashboard during or after a run and uses the documentation to understand
each view: overview, run, each loop, trials, Claude calls and conversations, files, questions,
events, the live panel, search, and export. The page explains what each number means (cost,
tokens, cache hit rate, first-try pass rate) and where it comes from, with screenshots.

**Why this priority**: the dashboard is how developers follow and judge a run; numbers without
explanation are easy to misread.

**Independent Test**: with the dashboard page open next to a real dashboard, a reader can name
what every view and every headline number shows.

**Acceptance Scenarios**:

1. **Given** the dashboard page, **When** a reader looks for a view, **Then** it is described
   with a screenshot taken from a real run.
2. **Given** a number shown in the dashboard, **When** the reader looks it up, **Then** the page
   says what it measures and how it is worked out.
3. **Given** a reader who wants a snapshot to share, **When** they read the page, **Then** it
   explains the export and what the exported file contains and leaves out.

---

### User Story 6 - Contribute to devloops (Priority: P3)

A developer who wants to change devloops reads the contributing section: how the code is
organised and how the parts connect, how to run the tests, how features are specified and
planned, and how to write documentation in the site's style. They can make a change, update the
pages it affects, and pass the tests.

**Why this priority**: it matters for the project's future, but readers who only use devloops do
not need it.

**Independent Test**: a contributor new to the code can name, from the architecture page alone,
which part of devloops would change for a given behavior (for example, how a backend check is
run), and run the test suite from the testing page.

**Acceptance Scenarios**:

1. **Given** the contributing section, **When** a contributor reads the architecture page,
   **Then** it shows the main parts of devloops, what each does, and how a run passes through
   them, as a diagram with a sentence per part.
2. **Given** a change to devloops' behavior, **When** the contributor follows the documentation
   rule, **Then** they know which pages to update in the same change and how the tests check
   them.
3. **Given** the writing style page, **When** anyone writes a new page, **Then** it tells them
   the audience, the language rules, and how to explain a term, with examples.

---

### Edge Cases

- A page mentions a command, option, configuration key, workspace path, or another page that no
  longer exists: the tests fail and name the page and the item.
- A reference page is edited by hand instead of regenerated: the tests fail because it no longer
  matches what the code produces.
- A behavior changes but the hand-written explanation of it does not mention anything the tests
  can check (for example, the order of two steps): each page lists the sources it was checked
  against, so the change's reviewer knows which pages to re-read; the documentation rule requires
  the pages to change in the same commit.
- An example output or screenshot is out of date after a change: examples come from a script that
  runs devloops, so re-running it refreshes them; a test checks that every example output file
  shown is one the script produces.
- The site build reports a warning (a broken link, a missing page in the navigation, a diagram
  that does not render): the build fails, and the site is not published.
- The site builder changes between versions: the version is fixed; moving to a new version is a
  deliberate change that rebuilds the site with no warnings.
- A reader opens an address of the old manual (a link to `loops/README.md#some-section`): the
  file is gone; the root `README.md` and the package description link to the site instead.
- A reader reads the site on a phone: the pages, diagrams and tables are readable without
  sideways scrolling of the whole page.
- The run skill installed in a user's project, which has no copy of the repository, needs to
  point a user at an explanation: it links to the site's address.

## Requirements *(mandatory)*

### Functional Requirements

**Site and publishing**

- **FR-001**: devloops' user documentation MUST be a public website built from Markdown pages in
  the repository's `docs/` folder, and MUST be published automatically when a change to those
  pages reaches the main branch.
- **FR-002**: The site build MUST fail on any warning (a broken link, a missing page, a diagram
  that does not render), and a failed build MUST NOT be published.
- **FR-003**: The site MUST have navigation by section, search across all pages, a light and a
  dark theme, readable layouts at phone width, and diagrams drawn from text in the pages.
- **FR-004**: The tool that builds the site MUST be fixed to one version, changed only on
  purpose.

**Content**

- **FR-005**: The site MUST have these sections: a landing page; getting started; how it works;
  the backend loop and the frontend loop; the dashboard; commands; configuration; security;
  skills; upgrades; known limitations; a glossary; and contributing.
- **FR-006**: The landing page MUST say what devloops is, the problem it solves, its core idea
  (a milestone passes only when devloops' own validation passes, never on the model's word), its
  two loops, its key features, what is needed to use it, and where to start, with a diagram of
  the cycle from requirements to a validated application.
- **FR-007**: "How it works" MUST explain: the run lifecycle (plan, approve, milestones, complete);
  each step that calls Claude Code (plan, replan, author checks, implement, fix, validate the UI),
  with what it is given, what it may do, and what it must return; what passes and fails a
  milestone in each loop; trials, retries granted, and recovery after a stop or crash; the
  statuses of a run, a loop, a milestone, a trial and a plan approval; the files devloops keeps
  and what each records; and how the dashboard collects and refreshes its data.
- **FR-008**: Each set of statuses and each flow named in FR-007 MUST be shown as a diagram, with
  text that says what moves it from one state or step to the next.
- **FR-009**: "Getting started" MUST take a reader from installation to a first run, its plan
  approval, following it in the dashboard, and finding its results, using only that page.
- **FR-010**: The dashboard page MUST describe each view, with screenshots from a real run, and
  explain each number it shows (cost, tokens, cache hit rate, first-try pass rate, cost per
  achieved milestone) and how it is worked out.
- **FR-011**: The security page MUST explain how secrets are kept out of recorded data, how
  Claude's writes are kept inside the target folder, and how the dashboard server is protected.
- **FR-012**: The contributing section MUST include an architecture page (the main parts of
  devloops, what each does, and how a run passes through them, with a diagram), how to run the
  tests, how features are specified and planned, the documentation rule, and the writing style.
- **FR-013**: The documentation MUST describe devloops as it is implemented on the branch it is
  published from, and MUST NOT describe planned or removed behavior as current.

**Writing standard**

- **FR-014**: Every page MUST be written for a reader new to devloops: plain language, short
  sentences, what a part does and why before how it works, and no need to read source code to
  understand it.
- **FR-015**: Every technical term specific to devloops or its tools MUST be explained in the
  sentence where it is first used on a page, or linked to its glossary entry; the glossary MUST
  define every such term used on the site.
- **FR-016**: The writing standard MUST itself be a page in the contributing section, with the
  audience, the language rules, and examples of a term explained well.

**Accuracy**

- **FR-017**: The reference pages MUST be generated from devloops itself: every command and its
  options, every configuration key with its type, allowed values and default, the exit codes, the
  steps, the statuses, and the formats of the state files. A test MUST fail when a committed
  reference page differs from what the generator produces now, naming the page.
- **FR-018**: Tests MUST check the hand-written pages: every command and option they mention
  exists, every configuration key they mention exists, every workspace path they show is one
  devloops writes, and every link between pages and to a section of a page resolves. A failure
  MUST name the page and the item.
- **FR-019**: Example outputs and screenshots MUST come from a script that runs devloops on a
  sample project (with the test suite's stand-in for Claude Code where a real call is not needed),
  so that re-running it refreshes them; examples MUST NOT be typed by hand.
- **FR-020**: Every hand-written page MUST end with a list of the sources it was checked against
  (files of devloops, and requirement IDs from `specs/`), kept out of the rendered page, so a
  reviewer can check the page against them.
- **FR-021**: Each page MUST be checked against its sources by a reviewer independent of its
  writer before it is published the first time, and every statement that could not be confirmed
  MUST be corrected or removed.

**Replacing the manual**

- **FR-022**: `loops/README.md` MUST be removed; its content MUST all be present in the site
  (rewritten to the writing standard), or recorded as dropped with the reason.
- **FR-023**: A short root `README.md` MUST say what devloops is, show a quick start, and link to
  the site's main sections; the package's description MUST be that file.
- **FR-024**: Everything that pointed at the old manual MUST point at the site: the run skill
  installed into projects (by the site's address), the project's contributor instructions
  (`CLAUDE.md`, including the rule that documentation describes the system as built, now for
  `docs/`), and code comments that cite manual sections.
- **FR-025**: Specifications in `specs/` that mention `loops/README.md` MUST be left as they
  are (they record decisions at the time); the rule for later specs ("Changed by / Revised by
  spec NNN" notes) MUST apply to the site's pages instead.

### Key Entities

- **Page**: one Markdown file in `docs/`; hand-written or generated; has a section in the
  navigation and, when hand-written, a list of the sources it was checked against.
- **Reference page**: a generated page (commands, configuration, exit codes, steps, statuses,
  state files); never edited by hand.
- **Glossary entry**: a term with a plain definition and a link to where it is explained in
  depth.
- **Example**: an output, file excerpt or screenshot shown on a page, produced by the example
  script from a real run.
- **Source list**: the files and requirement IDs a page was checked against.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A reader new to devloops can say what it does, why its results can be trusted, and
  how to start, after reading only the landing page (checked with at least two readers who have
  not used devloops).
- **SC-002**: A reader new to devloops can follow "Getting started" on a fresh sample project to
  a run that has planned and is waiting for approval, or has completed, with no step failing or
  differing from the page.
- **SC-003**: After reading "How it works", a reader can say what devloops does next for each of
  these: a check fails, a milestone runs out of trials, the run is interrupted, the plan has an
  open question.
- **SC-004**: 100% of the commands, options, configuration keys, exit codes, steps and statuses
  devloops has appear in the reference pages, and the tests fail within one test run when any of
  them changes without the pages.
- **SC-005**: 0 broken links, unknown commands, unknown options, unknown configuration keys or
  unknown workspace paths across the site, as reported by the tests.
- **SC-006**: The site builds with 0 warnings, and a change to a page is live on the site within
  10 minutes of reaching the main branch.
- **SC-007**: Every devloops-specific term used on the site has a glossary entry (0 undefined
  terms in a review of every page).
- **SC-008**: Every section of the old manual is accounted for: present in the site or recorded
  as dropped with a reason.
- **SC-009**: Every hand-written page has a source list, and the independent review of it found
  no unconfirmed statement left in the published page.

## Assumptions

- The site is built with Zensical, at a pinned version, as the developer chose (its predecessor,
  Material for MkDocs, reaches the end of its support in November 2026); the build runs in the
  repository's continuous integration, not in devloops' runtime, so devloops stays
  standard-library only.
- The site is hosted on GitHub Pages at the repository's default address,
  `https://youssef7ussien.github.io/claude-devloops/`; the repository is public, so Pages is free.
  Pages must be switched on for the repository (source: GitHub Actions) once, by the owner.
- The site describes the main branch only; earlier versions of devloops are not documented
  separately.
- The site is in English.
- Reference pages and examples are produced by scripts that use only the standard library and
  run with the rest of the test suite; screenshots need a headless browser, so the screenshot
  script is run by hand when the dashboard changes, not in every test run.
- The work is done on `main`, after spec 005's dashboard work (the export, and the removal of the
  summary page and the old dashboard code) was committed, so the dashboard pages describe the
  dashboard as it ships.
- "Readers new to devloops" are developers who know how to use a terminal and what a web
  application, an API and a test are, but do not know Claude Code's headless mode, devloops, or
  its terms.
