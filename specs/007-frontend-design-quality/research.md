# Research: Modern, Consistent Frontend Design

## R-1: Instructions alone are not enough

**Decision**: pair the instructions with things the driver checks: a required design brief in the
plan and acceptance criteria for states, widths and keyboard use.

**Rationale**: devloops trusts only validation. Advice the validator never checks is followed in
some trials and not others. The points a browser can check reliably become criteria; the rest stays
advice.

**Alternatives**: a "design review" step grading screenshots. Rejected: a model's taste is
inconsistent, it would fail trials for subjective reasons, and it costs one more browser call per
trial.

## R-2: Decide the design once

**Decision**: the plan records the design brief, and a first milestone builds the foundation when
the target has none.

**Rationale**: without a shared foundation, every implement call designs its own page and the pages
drift apart. Building the theme and base components first also makes later milestones cheaper.

## R-3: `requires_design` in `loop.json`

**Decision**: the plan schema gains an optional `design` object; a loop that sets
`requires_design: true` (frontend-dev) must fill it.

**Rationale**: the same pattern as `requires_openapi_path`. The schema stays shared by both loops,
and the backend is not affected.

## R-4: Design references are files, copied at the first start

**Decision**: `design.references` lists files or folders relative to the project root. At the
frontend loop's first start, devloops copies them to `state/design-references/<n>-<name>` and the
calls get the copies' paths in their context and read access to that folder only (`--add-dir`). A
missing path stops `devloops run` before any loop runs: `Engine.check_tools`, the check the run
makes on every selected loop before anything is spent, checks them too.

**Rationale**: images and documents are what Claude Code reads well; files need no network access.
`--add-dir` takes folders, so reading in place would open each reference's folder; for a file at
the project root that is the whole project, `.devloops/` included. A copy also fixes the
references for the run. They are not fingerprinted: they guide the calls, like the instructions,
rather than define what is built, so an edit is ignored rather than stopping the run.

**Alternatives**: reading in place (rejected, above); fingerprinting with `input-changed` (rejected:
too strict for guidance); web addresses (rejected for now: the steps have no web tool, and pages
change).

*Revised 2026-10-12 after review: the first version read the references in place and checked them
only at the frontend's first start, after the backend loop had run.*

## R-5: Widths and keyboard

**Decision**: criteria name 375 px and 1280 px, and keyboard use with visible focus. The tester
resizes the browser and presses keys through the Playwright MCP tools it already has.

**Rationale**: two widths cover phone and desktop with two screenshots. Colour contrast stays a rule,
not a criterion: judging it from a screenshot is unreliable.
