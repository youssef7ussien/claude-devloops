# Data Model: Modern, Consistent Frontend Design

## Plan: `design` (new, optional; required when the loop sets `requires_design`)

| Field | Type | Meaning |
|---|---|---|
| `summary` | string | The visual direction: design system or component library, colour palette, typography, spacing, layout shell and base components, and where the foundation lives or which milestone builds it. |
| `source` | `existing-code` \| `requirements` \| `configuration` \| `proposed` | Where the direction comes from, in the stack's priority order. `configuration` means `design.references`. |
| `conflicts` | string[] | Disagreements between the sources. Not empty → the plan needs an open question. |

Owned by `specs/001-reusable-dev-loops/contracts/plan.schema.json` (changed by this spec).

## Configuration: `design` (new)

| Key | Type | Default | Meaning |
|---|---|---|---|
| `design.references` | string[] | `[]` | Files or folders, relative to the project root, that show the look the developer wants. Frontend loop only. |

Owned by `specs/001-reusable-dev-loops/contracts/config.schema.json` (changed by this spec).

## `loop.json`: `requires_design` (new)

`true` for `frontend-dev`: its plans must have `design`.

## Loop state: `state/design-references/` (new)

The copies of the design references, made at the frontend loop's first start: `<n>-<name>` for the
n-th reference (a file or a folder).

## Step context (new keys)

- `design_references`: absolute paths of the copies, in the frontend loop's plan, replan,
  implement and fix calls (absent when none are set).
- `design`: the plan's design brief, in the implement and fix calls (absent when the plan has none).
- `requires_design`: `true` in the plan and replan calls of a loop that sets it, as
  `requires_openapi_path` is for the backend.

## Dashboard: loop answer

Gains `design`: the plan's design brief, or `null`.
