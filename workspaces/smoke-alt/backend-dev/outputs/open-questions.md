# Open questions: backend-dev

Write each answer after its **Answer:** marker (more lines are fine), then run `devloops approve backend-dev --workspace smoke-alt` to accept the plan, or `devloops replan backend-dev --workspace smoke-alt` to plan again with the answers.

### OQ1

**Question:** Should the backend also serve the page with the increment button (e.g. GET / returning HTML), or is the page built by a separate frontend in the sibling workspace directory?
**Context:** COUNTER-1 mentions a page with a button. The target directory is named 'backend', suggesting a separate frontend. The plan currently excludes the page from the backend and enables CORS so a separately hosted page can call the API. If the backend should serve it, a milestone M02 adding GET / (200, text/html containing a button wired to POST /counter/increment and a display of the value) would be added.
**Affects:** M01

**Answer:** A separate frontend loop builds the page; the backend serves only the counter API (keep CORS enabled).