# Contract: full dashboard

A single self-contained HTML file per generation. It can be opened anywhere, with no network and no
other file (FR-035, SC-009).

## Name and location

```text
<dashboards_dir>/<workspace>/<YYYYMMDDTHHMMSSZ>.html     # UTC time of generation
<dashboards_dir>/<workspace>/<YYYYMMDDTHHMMSSZ>-2.html   # on a same-second collision (-3, …)
```

- The file is created exclusively, so it never replaces an earlier one (FR-036).
- `dashboards_dir` defaults to `.devloops/dashboards` (project configuration).
- Generated automatically when a command ends in a final status, and by `devloops dashboard`
  (FR-039).

## Content

Everything in the lightweight dashboard (001): KPIs, orchestrator, charts, milestones, criteria,
checks, sessions, and events. In addition:

| Section | What is embedded | How |
|---------|------------------|-----|
| Header notice | "Contains full Claude Code conversations — review before sharing", plus the generation time, the devloops version, and the workspace | text |
| Per loop → Inputs | `requirements` (and `plan.md` / `tasks.md` for spec-kit inputs), the API spec for frontend-dev | text in `<details>` |
| Per loop → Plan | `state/plan.json`, `outputs/plan-summary.md`, `outputs/open-questions.md`, the milestone files | text / JSON in `<details>` |
| Per milestone → Checks | `checks.json` | JSON in `<details>` |
| Per trial | `trial.json`, `validation.json`, `stream.jsonl`, every file in `evidence/` | images as `data:` URIs (shown as thumbnails, open full size); other files inline when text, otherwise a `data:` download link |
| Per loop → Outputs | every file in `outputs/` (e.g. `openapi.json`, `ui-url.txt`) | text in `<details>` |
| Per loop → Progress | `progress.md` | text in `<details>` |
| Per call → Prompt | `state/prompts/<seq>-<step>.md`, with `prompt_sources` | text in `<details>` |
| Per call → Conversation | `state/conversations/<seq>-<step>.jsonl` (FR-040) | rendered transcript (below) |
| Orchestrator | `orchestrator/state.json`, `orchestrator/progress.md` | text / JSON |
| Events | `events.jsonl` (all of them) | table |

**Every embedded item is labelled with**: its workspace-relative path, its size, and its milestone,
trial, and step where they apply.

**Missing or unreadable items** stay in place, shown as `missing: <path>` (FR-037, FR-042). For a
conversation, its session ID is also shown.

## Conversation rendering (research P-9)

Each call shows a header line: `seq`, step, milestone, trial, session ID, model, tokens, cost, and
duration. Then the transcript records, in order:

| Record | Rendering |
|--------|-----------|
| `user` message, `text` content | "User" block (the prompt; long text collapsed) |
| `assistant` message, `text` | "Claude" block |
| `assistant` message, `thinking` | collapsed "Thinking" block |
| `assistant` message, `tool_use` | "Tool: <name>" with its input as JSON. For an `Edit`/`Write`, the path and the old and new text |
| `user` message, `tool_result` | "Result" block, collapsed when longer than 40 lines. Errors are marked |
| any other record type | collapsed "<type>" block with the raw JSON |

Nothing is truncated. Collapsing only hides text until it is opened.

## Safety

- **Escaping**: all model-written and file text is HTML-escaped (as in 001). Embedded HTML files
  are shown as text, never rendered.
- **Secrets**: every embedded string passes through the `Redactor` of the loop's frozen
  configuration, including keys inside JSON (FR-041, SC-010).
- **No network**: no external references. There is one inline script, as in 001 (the theme
  toggle).

## Output report

The command prints:
- the path and the size in bytes;
- the five largest embedded items (path, bytes);
- the number of conversations marked unavailable.
