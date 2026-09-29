# Open questions: backend-dev

Write each answer after its **Answer:** marker (more lines are fine), then run `devloops approve backend-dev --workspace smoke` to accept the plan, or `devloops replan backend-dev --workspace smoke` to plan again with the answers.

### OQ1

**Question:** Two fixed rules conflict, so M01 cannot pass as written. The contract check requires every request a frozen check sends to match an operation in openapi.json. Check C3 (for M01-AC3) sends GET /does-not-exist. But M01-AC4 says openapi.json may list only /health, and the loop rules say to document only real endpoints. The HTTP behavior already passes all of C1–C4; only the contract check fails. Which should change? (a) Allow a catch-all GET /{path} operation in openapi.json that documents the 404 {"error":...} response, and relax M01-AC4 to allow it. (b) Exempt negative or unknown-route checks (expected 4xx on an undeclared path) from the contract-matching rule. (c) Drop or reword M01-AC3 so it no longer probes an undeclared path.
**Context:** needs-input from M01 trial 2
**Affects:** HEALTH-1

**Answer:** The conflict was in the driver, and it is fixed: a check that expects 404 (unknown path) or 405 (unsupported method) on an undocumented operation now agrees with the contract. Keep openapi.json documenting only GET /health, and keep returning 404 for unknown paths.