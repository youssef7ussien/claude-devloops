# Contract: Page Front Matter

Every hand-written page in `docs/` starts with:

```yaml
---
title: How a run works            # the page title (also the navigation label unless set in nav)
description: >-                   # one plain sentence: what the reader learns here
  From requirements to a finished application: the plan, its approval, and each milestone.
sources:                          # what the page was checked against (FR-020), never rendered
  - loops/shared/devloops/engine.py
  - loops/shared/devloops/orchestrator.py
  - spec 001 FR-012
  - spec 003 FR-004
---
```

Rules (`test_docs` check 3):
- `title` and `description` are non-empty strings.
- `sources` is a non-empty list. An entry is either a repository path that exists (file or
  folder), or `spec NNN <ID>` where `specs/NNN-*/spec.md` (or its `research.md` for `R-n`)
  contains that ID.
- Generated pages carry `generated: true` instead of `sources`.
