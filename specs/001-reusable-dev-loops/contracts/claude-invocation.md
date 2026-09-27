# Contract: Claude Code Invocations

Every step that needs Claude runs as one headless call. In `-p` mode, tools that are not
allowed are denied instead of prompting, so the allowlist defines what each step can do. The flags are verified against Claude Code
2.1.283 (research, "Environment facts").

```text
claude -p "<composed prompt>" \
  --session-id <uuid assigned by driver> \
  --output-format json                     # stream-json for validate-ui (R-10)
  --json-schema '<step result schema>' \
  --permission-mode <mode> \
  --allowedTools <list> --disallowedTools <list> \
  --settings <per-call settings JSON: PreToolUse guard hook> \
  --strict-mcp-config [--mcp-config <playwright config>] \
  [--model <config.model>] [--max-budget-usd <config.max_budget_usd_per_invocation>]
```

- The call runs with `cwd = target_dir`.
- The driver enforces `invocation_timeout_seconds` by killing the process.
- The environment passes `DEVLOOPS_ALLOWED_ROOTS` to the guard hook.

## Prompt composition (FR-046, research R-16)

1. `loops/shared/prompts/common.md`: shared rules. Work only on the given milestone. Change only
   what its tasks need. Do not refactor unrelated code. Keep existing conventions. Never alter the
   requirements. Report ambiguity as an assumption, never silently.
2. `loops/<loop>/Loop-instructions.md`.
3. `loops/shared/prompts/steps/<step>.md`.
4. A driver context block with:
   - input paths;
   - the story ID and scope rule;
   - the approved answers;
   - the stack and runtime;
   - the milestone, its tasks, and its acceptance criteria;
   - on fix trials, the previous trial's failure summary and evidence paths.

## Steps

| Step | Loop | Tools | Permission mode | Structured result |
|------|------|-------|-----------------|-------------------|
| `plan` / `replan` | both | `Read Glob Grep` | default; write tools and `Bash` in `--disallowedTools` | [plan.schema.json](./plan.schema.json) |
| `implement` / `fix` | both | `Read Edit Write Glob Grep Bash` (configurable) | `acceptEdits` | `{tasks: [{task_id, status: implemented\|not-implemented, note}], assumptions: [{text, affects}], needs_input: [{question, requirement_refs}], files_changed: [path]}`. Put anything that would add, remove, or contradict a requirement in `needs_input`, never in `assumptions` (FR-055a) |
| `author-checks` | backend-dev | `Read Glob Grep` | default; write tools and `Bash` in `--disallowedTools` | [checks.schema.json](./checks.schema.json) |
| `validate-ui` | frontend-dev | `Read` + `mcp__playwright__*` | default; write tools and `Bash` in `--disallowedTools` | `criteria[]` and `network_requests[]` (see [validation-result.schema.json](./validation-result.schema.json)) |

## Driver post-conditions for every call

**Failure classification (FR-067, research R-19)**:
- A **service failure** (`api_error_status` ∈ {401, 403, 429, 5xx}, an authentication or connection
  error before any result, or the network unreachable) voids the trial and stops the run as
  `stopped-on-service-error`.
- Every other failure is a **work failure** and counts as a trial.
- The class is stored in the invocation record as `failure_class`.

**Redaction (FR-070)**: The composed prompt, the stream log, the invocation record, and any evidence
are passed through `redact.py` (configuration `secrets`) before they are written.

**Least privilege (FR-071)**: The tool list per step is the table above. No step gets more by
default, and write tools are only ever granted to implement and fix steps, which are confined to the
target by the guard hook.

A call's result is used only if all of the following hold:
1. The call exited before the timeout, `is_error == false`, and `subtype == "success"`.
2. `structured_output` matches the step schema. Otherwise the trial fails with `invalid-output`.
3. The boundary audit is clean. Otherwise the trial fails with `boundary-violation`.
4. An invocation record was appended, even for failed calls. Its tokens are `null` if `usage` is
   missing.

## Fake binary for tests (constitution VIII)

`DEVLOOPS_CLAUDE_BIN` overrides the `claude` executable. The test suite points it at
`loops/shared/tests/fake_claude.py`, which returns canned JSON for each step. This lets the whole
engine be tested without a model or network access.
