# Open questions: backend-dev

Claude suggests an answer where it can. Leave **Answer:** empty to accept the suggestion, or write your own answer after the marker (more lines are fine). By default the run accepts the suggestions itself. When it pauses for review, run `devloops approve backend-dev --workspace golden` to accept the plan and continue, or `devloops replan backend-dev --workspace golden` to plan again with the answers. Approving (or `retry` after a needs-input stop) copies each accepted suggestion into its answer and marks it with **Answer source:**.

### OQ1

**Question:** Which database?
**Context:** Stack conflict
**Affects:** M02
**Suggested answer:** SQLite, in a file under the target.
**Why:** no database is configured and it needs no server

**Answer:**
