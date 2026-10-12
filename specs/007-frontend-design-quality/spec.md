# Feature Specification: Modern, Consistent Frontend Design

**Feature Branch**: `main` (no branch hook configured)

**Created**: 2026-10-12

**Status**: Draft

**Input**: User description: "Make frontend-dev build modern, polished user interfaces with an
excellent user experience: modern visual design, clear flows, responsive layouts, accessibility,
clear interaction states, reusable components, consistency." The developer agreed in conversation
to these changes: a design chosen once at planning, a foundation milestone that builds it, short UI
quality rules, quality criteria the browser can check, and an optional design reference in the
configuration. A step that grades how the pages look is left out.

## Scope and Source Classification

**Problem**: the frontend loop's instructions say nothing about UI quality. Every implement call
designs its own page, so spacing, colours, buttons and states differ from page to page, and
nothing asks for phone layouts, keyboard use, or loading, empty and error states. Validation checks
only the acceptance criteria, so the model builds pages that work and stops there.

**In scope**:
- a design brief in every frontend plan, chosen in the same priority order as the stack;
- a first milestone that builds the design foundation when the target has none;
- UI quality rules for the implement and fix steps;
- acceptance criteria for states, narrow screens and keyboard use, checked in the browser;
- a `design.references` configuration key: files that show the look the developer wants;
- the brief shown in `plan-summary.md` and on the dashboard.

**Out of scope**:
- grading how the pages look (taste is not a pass or fail criterion);
- a new validator or any relaxed validation rule;
- naming a component library or stack in the loops (constitution II);
- web addresses as design references (only files).

Every requirement is tagged with its source:

| Tag | Meaning |
|-----|---------|
| **[E]** | **Explicit**: a decision the developer confirmed for this feature |
| **[I]** | **Implied**: needed to satisfy an explicit requirement; the reason is given inline |
| **[K]** | **Kept**: an existing guarantee this feature must not weaken (item cited) |

## Clarifications

### Session 2026-10-12

- Q: Rules in the instructions, or something validation checks? → A: Both. The rules guide the
  model; the points a browser can check (states, narrow screens, keyboard) become acceptance
  criteria, so validation enforces them.
- Q: Should a step judge how the pages look? → A: No. A model's taste is inconsistent; it would fail
  trials for subjective reasons and cost an extra browser call.
- Q: How does the developer give a visual direction? → A: A new configuration key,
  `design.references`, lists files (screenshots, a brand guide); the requirements may also
  describe one.
- Q: Which states become criteria? → A: Only the error for invalid input, which a user can always
  bring about in the browser. Loading and backend failures cannot be produced on demand, and an
  empty list cannot be reached once the backend holds data (from its own checks or an earlier
  trial); making them criteria would fail trials for no fault of the code, so they stay rules.
- Q: Does the loop name a component library? → A: No. The plan picks one that suits the stack, as
  it picks the stack, and says why.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A frontend that looks designed, page after page (Priority: P1)

A developer runs devloops on requirements with several pages and an empty frontend target. The plan
describes one visual direction. The first milestone builds the shared pieces: theme, layout shell,
navigation and base components. Every later page reuses them, so the pages look like one product.

**Why this priority**: consistency is what the developer noticed missing first, and the other
stories build on the foundation.

**Independent Test**: plan with fake Claude and check that a frontend plan without a design brief
is rejected and one with a brief is accepted, and that the brief reaches `plan-summary.md`, the
dashboard and every implement and fix call.

**Acceptance Scenarios**:

1. **Given** a frontend plan with no `design`, **When** devloops checks it, **Then** the planning
   trial fails, saying the design is required for this loop.
2. **Given** an approved frontend plan with a design brief, **When** a milestone's implement or fix
   step runs, **Then** its context carries the brief.
3. **Given** a target that already has a design system, **When** the frontend plans, **Then** the
   brief's source is `existing-code` and no foundation milestone rebuilds it.

---

### User Story 2 - Pages that work for everyone (Priority: P1)

The developer opens a page on a phone, uses it with the keyboard only, and waits for slow data. The
page fits the screen, every action can be reached and done with the keyboard, and the user always
sees what is happening: loading, nothing to show, or an error.

**Why this priority**: these are the quality points a browser can check, so they are the ones
validation can enforce.

**Independent Test**: read the frontend instructions and the validate-ui prompt; a plan that follows
them gives each page criteria for its states, a narrow width and keyboard use, and the tester knows
how to check each one in the browser.

**Acceptance Scenarios**:

1. **Given** a milestone that adds a page that loads data, **When** the plan is written, **Then** its
   criteria cover its error for invalid input, the page at 375 px and 1280 px
   wide, and its main actions done by keyboard.
2. **Given** such a criterion, **When** validate-ui runs, **Then** the tester resizes the browser or
   uses the keyboard to check it, with a screenshot as evidence.

---

### User Story 3 - Show the look you want (Priority: P2)

The developer has a brand guide and a screenshot of a site they like. They list both under
`design.references`. The plan's design follows them, and the implement steps can open them.

**Why this priority**: a concrete reference gives better results than words, but most runs work
without one.

**Independent Test**: set `design.references` to a file and to a missing file; the first run passes
the existing file to the plan and implement calls and gives them read access, and the missing file
stops the run with `missing-input` (exit 30).

**Acceptance Scenarios**:

1. **Given** `design.references` lists an existing file, **When** the frontend plans and
   implements, **Then** each call's context lists it and the call may read it.
2. **Given** a listed file does not exist, **When** the developer runs `devloops run`, **Then** the
   run stops with `missing-input`, naming the file, before the backend loop makes any call.
3. **Given** the developer edits a reference after the frontend loop started, **When** a later call
   runs, **Then** it reads the copy made at the first start.

---

### Edge Cases

- **Target already has code and a design system**: the plan keeps it (`source: existing-code`) and
  plans no foundation milestone; it may add a missing base component inside the milestone that
  first needs it.
- **References disagree with the existing code or the requirements**: each disagreement is listed in
  `design.conflicts`, and the plan must ask about it in an open question, as with the stack.
- **Spec-kit feature**: the foundation work goes in the first milestone of the first phase that has
  frontend tasks; the coverage rules are unchanged.
- **Single-story run on an existing app**: the existing look is the foundation; the story's pages
  follow it.
- **A page with no data and no actions** (a static page): the state and keyboard criteria do not
  apply; only the width criterion does.
- **Backend-only project**: nothing changes; `design` is neither required nor read.
- **A reference that is a folder**: allowed; the calls may read its files.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001** [E]: A frontend plan MUST include a design brief, `design`: a summary of the visual
  direction (the design system or component library, colour palette, typography, spacing, layout
  shell and base components) and its `source`, chosen in the stack's priority order: the target's
  existing code, then the requirements or the configuration, and only then a proposal.
- **FR-002** [I]: devloops MUST reject a frontend-dev plan without `design` (the planning trial
  fails), so the brief is checked rather than requested (constitution III). Backend plans are not
  affected.
- **FR-003** [I]: When `design.conflicts` is not empty, the plan MUST have at least one open
  question, as for `stack.conflicts` (constitution I: ambiguity is surfaced).
- **FR-004** [E]: When the target has no UI foundation, the frontend plan's first milestone MUST
  build it (theme values, layout shell with navigation, base components including the loading,
  empty and error states), with criteria a browser can check. When the target has one, the plan
  reuses it.
- **FR-005** [E]: Later milestones MUST reuse the foundation: no new visual styles or UI
  dependencies outside it.
- **FR-006** [E]: Each frontend milestone that adds or changes a page MUST have acceptance
  criteria for (a) the error a user sees for invalid input, in each form; the other states
  (loading, empty, a backend failure) depend on timing or on data the browser does not control
  (the backend may hold data from its own checks or an earlier trial), so they stay rules
  (FR-007), not criteria; (b) the page
  at 375 px and 1280 px wide, with no sideways scrolling; and (c) its main actions done with the
  keyboard alone, with visible focus.
- **FR-007** [E]: The frontend instructions MUST give the implement and fix steps short UI quality
  rules: use the foundation, start from narrow screens, cover every state, keep focus visible and
  the keyboard usable, use semantic HTML with labels, add motion only where it helps, and apply
  this only to what the milestone builds.
- **FR-008** [I]: The validate-ui instructions MUST say how to check such criteria in the browser
  (resizing the window, pressing keys, reading the page's structure), so FR-006 can be enforced.
- **FR-009** [E]: A configuration key, `design.references`, MUST list files or folders (relative to
  the project root) that show the look the developer wants. It applies to the frontend loop only.
- **FR-010** [I]: At the frontend loop's first start, devloops MUST copy the references into the
  loop's state (`state/design-references/`). The plan, replan, implement and fix calls MUST receive
  the copies in their context and MUST be allowed to read them, not the originals' folders: a
  reference at the project root must not open the project to the calls. (The requirements' folder
  is readable by every call already; that access is not changed here.) A change to an original
  after the first start does not reach the run. A reference that holds the workspace, or that
  cannot be copied, stops the first start with `missing-input`.
- **FR-011** [I]: A reference that does not exist MUST stop `devloops run` with `missing-input`
  (exit 30), naming it, before any loop runs, so the backend spends nothing on a run the frontend
  cannot start (constitution V: fail clearly). `devloops check` MUST report it too.
- **FR-012** [I]: The implement and fix calls MUST receive the plan's design brief in their context,
  so each milestone follows it.
- **FR-013** [I]: `plan-summary.md` and the dashboard's plan panel MUST show the design brief, so it
  is reviewed with the plan.
- **FR-014** [K]: The loops MUST NOT name a component library, stack or application (constitution
  II; `test_no_app_specifics.py`).
- **FR-015** [K]: Validation MUST NOT change: no new pass or fail rule beyond the acceptance criteria
  the plan writes, and how a page looks is never graded.

### Key Entities

- **Design brief** (`plan.design`): `summary`, `source`, `conflicts`.
- **Design references** (`config.design.references`): a list of paths.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every approved frontend plan has a design brief: devloops rejects one without it.
- **SC-002**: Every implement and fix call of the frontend loop carries the design brief and the
  design references in its context.
- **SC-003**: Given the same requirements, a run after this feature gives each page criteria for
  its states, narrow width and keyboard use, and they pass in validation.
- **SC-004**: A missing design reference stops the run before any call to Claude Code.
- **SC-005**: The full test suite passes, including `test_no_app_specifics.py` and
  `test_schemas_sync.py`.

## Assumptions

- 375 px and 1280 px stand for a phone and a desktop; a tablet width is not checked separately.
- Colour contrast is not a criterion: a browser check of it from screenshots is unreliable. It stays
  a rule for the implement step.
- References are copied once, at the first start, rather than fingerprinted like the requirements:
  they guide the calls rather than define what is built, so an edit is ignored instead of stopping
  the run. Large folders are copied whole; the developer chooses what to list.
- More criteria make validation calls longer and may need more fix trials; the developer accepted
  this cost.
