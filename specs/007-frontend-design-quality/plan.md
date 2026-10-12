# Implementation Plan: Modern, Consistent Frontend Design

**Branch**: `main` | **Date**: 2026-10-12 | **Spec**: [spec.md](spec.md)

## Summary

Most of this feature is prompt text: the frontend loop's instructions gain a design section, a UI
quality section and planning rules for quality criteria, and the validate-ui prompt says how to
check them. The driver changes are small and make the prompts enforceable or reachable: an optional
`design` object in the plan schema, required for loops whose `loop.json` sets `requires_design`; a
`design.references` configuration key, checked at the first start and passed to the calls with read
access; and the brief shown in `plan-summary.md` and on the dashboard.

## Technical Context

- **Language**: Python ≥ 3.10, standard library only; the dashboard app is plain JavaScript.
- **Touched**: `loops/frontend-dev/{Loop-instructions.md,loop.json}`,
  `loops/shared/prompts/steps/{plan.md,validate-ui.md}`, `loops/shared/schemas/{plan,config}.schema.json`
  (and their contracts in `specs/001-reusable-dev-loops/contracts/`), `plan.py`, `engine.py`,
  `render.py`, `dashboard.py`, `assets/app/views/loop.js`, `config/defaults.json`.
- **Testing**: unittest with fake Claude; `node --test` for the dashboard view.
- **Constraints**: no stack or library named in the loops (FR-014); validation unchanged (FR-015).

## Constitution Check

| Principle | Check |
|---|---|
| I. Requirements-driven | Design conflicts become open questions (FR-003). Pass. |
| II. Reusability | The rules are generic; the plan chooses the library (FR-014). Pass. |
| III. Verifiable | The brief is checked by the driver; quality points become acceptance criteria validated in the browser (FR-002, FR-006). Pass. |
| IV. Controlled automation | Rules apply only to what the milestone builds; existing design systems are reused (FR-004, FR-007). Pass. |
| V. Bounded execution | No new loop or retry; a missing reference fails clearly (FR-011). Pass. |
| X. Simplicity | No new validator or grading step; one optional schema object and one configuration key. Pass. |

## Project Structure

```text
specs/007-frontend-design-quality/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── tasks.md
└── checklists/requirements.md
```

## Key flows

- **Planning**: `plan.validate_plan` rejects a plan without `design` when the loop sets
  `requires_design`, and one with `design.conflicts` but no open question.
- **Before the run**: `Engine.check_tools` (called by the run for every selected loop) and
  `devloops check` resolve `design.references` against the project root and report a missing one
  (`missing-input`, frontend loop only).
- **First start**: `Engine._first_start` checks them again and copies them into
  `state/design-references/` (`inputs.freeze_design_references`).
- **Calls**: `_plan_context` and `_milestone_context` add `design_references` (the copies);
  `_milestone_context` adds the plan's `design`; `_input_dirs` adds the copies' folder only.
- **Review**: `render_plan_summary` writes a "Design" section; the dashboard's loop answer carries
  `design` and the plan panel shows it.

## Complexity Tracking

None.
