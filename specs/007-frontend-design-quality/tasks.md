---

description: "Task list for 007: modern, consistent frontend design"
---

# Tasks: Modern, Consistent Frontend Design

**Input**: `specs/007-frontend-design-quality/` (spec.md, plan.md, research.md, data-model.md)

**Tests**: included. Run the suite with `VISUAL=true EDITOR=true python3 -m unittest discover -s
loops/shared/tests` and the app tests with `node --test loops/shared/devloops/assets/app/tests/`.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Foundational (schemas)

- [X] T001 Add the optional `design` object (`summary`, `source`, `conflicts`) to
  `specs/001-reusable-dev-loops/contracts/plan.schema.json` and copy it to
  `loops/shared/schemas/plan.schema.json` (FR-001)
- [X] T002 Add `design.references` to `specs/001-reusable-dev-loops/contracts/config.schema.json`,
  copy it to `loops/shared/schemas/config.schema.json`, and add its default to
  `loops/shared/config/defaults.json` (FR-009)
- [X] T003 Add `design` to the sample plan in `loops/shared/tests/samples.py`, so frontend tests
  keep valid plans

## Phase 2: User Story 1 – A frontend that looks designed (P1)

- [X] T004 [US1] Tests in `loops/shared/tests/test_plan.py` and `test_frontend_loop.py`: a `requires_design` plan
  without `design` is rejected; `design.conflicts` without an open question is rejected; a backend
  plan without `design` is accepted (FR-002, FR-003)
- [X] T005 [US1] `requires_design` in `plan.validate_plan` and `loops/frontend-dev/loop.json`
- [X] T006 [US1] `design` in the implement and fix context (`engine._milestone_context`) (FR-012)
- [X] T007 [US1] "Design" section in `render.render_plan_summary`, with a test (FR-013)
- [X] T008 [US1] `design` in the dashboard's loop answer and a "Design" card in
  `assets/app/views/loop.js`, tested in `test_dashboard_data.py`; note it in
  `specs/005-dashboard-redesign/data-model.md` (FR-013)
- [X] T009 [US1] Design section in `loops/frontend-dev/Loop-instructions.md` (brief, foundation
  milestone, reuse) and the `design` field in `loops/shared/prompts/steps/plan.md` (FR-001, FR-004,
  FR-005)

## Phase 3: User Story 2 – Pages that work for everyone (P1)

- [X] T010 [US2] Quality criteria rule in the planning section, and a "UI quality" section, in
  `loops/frontend-dev/Loop-instructions.md` (FR-006, FR-007)
- [X] T011 [US2] How to check widths, keyboard and structure in
  `loops/shared/prompts/steps/validate-ui.md` (FR-008)

## Phase 4: User Story 3 – Show the look you want (P2)

- [X] T012 [US3] Tests: an existing reference reaches the plan and implement contexts and the
  calls' `--add-dir`; a missing one stops the first start with `missing-input` before any call
  (FR-010, FR-011)
- [X] T013 [US3] Resolve and check `design.references` at the frontend loop's first start; add
  `design_references` to the plan and milestone contexts and their folders to `_input_dirs`

## Phase 5: Polish

- [X] T014 Docs: `docs/guides/frontend-loop.md` (design section), `docs/guides/configuration.md`
  (the settings table); regenerate `docs/reference/` with `tools/docs/gen_reference.py`
- [X] T015 "Changed by spec 007" notes in `specs/001-reusable-dev-loops` where the plan and the
  configuration keys are described
- [X] T016 Full suite and app tests pass (SC-005)

## Phase 6: Review fixes (2026-10-12)

- [X] T017 Check `design.references` in `Engine.check_tools` and `devloops check`, so `devloops
  run` stops before the backend runs; tests in `test_run_command.py` and `test_check.py` (FR-011)
- [X] T018 Copy the references into `state/design-references/` at the first start and give the
  calls the copies and their folder only; test that an edit after the start is not used, and that
  replan and fix get the references (FR-010, research R-4)
- [X] T019 validate-ui: the size to resize back to, and empty states checked first; planning:
  empty-state criteria only where reachable (FR-006, FR-008)
- [X] T020 Dashboard guide mentions the design brief; one loop over stack and design in `plan.py`
  and `render.py`

## Phase 7: Second review fixes (2026-10-12)

- [X] T021 validate-ui: resize back to 1280 × 720 and read the network log again after a resize;
  planning: the invalid-input error is the only state criterion (FR-006, FR-008)
- [X] T022 Reject a reference that holds the workspace, and turn a failed copy into
  `missing-input`; tests in `test_frontend_loop.py` and `test_check.py` (FR-010, FR-011)
- [X] T023 `devloops check` shares `inputs.design_references`, reads `requires_design` from each
  loop, and skips a loop that has started (FR-011)
- [X] T024 `requires_design` in the plan context; the copies looked up once per command
