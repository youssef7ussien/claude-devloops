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

**Layout** (both dashboards share it, `ui.py` and `assets/`): a sidebar of views (Overview,
Orchestrator, one per loop, Claude calls, Files, Questions, Events), one shown at a time; a viewer
dialog that opens files and calls; and a "go to" palette that matches names and, from three
characters, the text of every file and conversation (a result opens at the matching line). The
Overview starts with a "Needs attention" panel: stopped or paused loops and their next action,
criteria failing on a milestone's latest trial, unanswered questions while a loop is not done,
failed calls, evidence over 1 MB, and milestones that passed only after failed or voided trials. Without the script, the views are shown
one after another and each file or call opens in place, so nothing depends on the script to be
read.

| Section | What is embedded | How |
|---------|------------------|-----|
| Header notice | "Contains full Claude Code conversations — review before sharing", plus the generation time, the devloops version, and the workspace | text |
| Per loop → Inputs | `requirements` (and `plan.md` / `tasks.md` for spec-kit inputs), the API spec for frontend-dev | a file in the Files explorer |
| Per loop → Plan | `state/plan.json`, `outputs/plan-summary.md`, `outputs/open-questions.md`, the milestone files | a file in the Files explorer |
| Per milestone → Checks | `checks.json` | a file in the Files explorer |
| Per trial | `trial.json`, `validation.json`, `stream.jsonl`, every file in `evidence/` | images as `data:` URIs (shown as thumbnails, open full size); other files inline when text, otherwise a `data:` download link |
| Per loop → Outputs | every file in `outputs/` (e.g. `openapi.json`, `ui-url.txt`) | a file in the Files explorer |
| Per loop → Progress | `progress.md` | a file in the Files explorer |
| Per call → Prompt | `state/prompts/<seq>-<step>.md`, with `prompt_sources` | a file in the Files explorer; the call's Prompt tab shows it with its parts |
| Per call → Conversation | `state/conversations/<seq>-<step>.jsonl` (FR-040) | rendered transcript (below) |
| Orchestrator | `orchestrator/state.json`, `orchestrator/progress.md` | text / JSON |
| Events | `events.jsonl` (all of them) | table |

**Every embedded item is labelled with**: its workspace-relative path, its size, and its milestone,
trial, and step where they apply.

**Files explorer**: a tree per loop (Inputs, Plan, Milestones → each trial → `evidence/`, Calls,
Outputs, Run state, `progress.md`), then the orchestrator's and the workspace's own files. A file's
kind picks its viewer (`ui.KINDS`, by extension, else JSON when it parses, else text): Markdown
(rendered, or source), JSON (indented and highlighted, or a tree), JSON lines (one record per
row), code and logs (highlighted), images (fit, or full size), and other binary files (download).
JSON is indented when embedded, with every value redacted. Markdown is rendered into DOM nodes, so
model-written text never becomes HTML; its links are not followed, except to files in the page.

**Missing or unreadable items** stay in place, shown as `missing: <path>` (FR-037, FR-042). For a
conversation, its session ID is also shown.

## Conversation rendering (research P-9)

Each call shows a header line: `seq`, step, milestone, trial, session ID, model, tokens, cost, and
duration. Then the transcript records, in order:

| Record | Rendering |
|--------|-----------|
| `user` message, `text` content | "User" block (the prompt; collapsed when longer than 40 lines) |
| `assistant` message, `text` | "Claude" block, rendered as Markdown |
| `assistant` message, `thinking` | collapsed "Thinking" block, hidden until shown |
| `assistant` message, `tool_use` | collapsed "Tool: <name>" block with a one-line hint (the command, path, or URL); its input as JSON. For a `Bash` call, the command; for an `Edit`/`Write`, the path and the old and new text |
| `user` message, `tool_result` | "Result" block, collapsed when longer than 12 lines unless it is an error. Errors are marked |
| any other record type | collapsed "<type>" block with the raw JSON, hidden until "System records" is shown |

Nothing is truncated. Collapsing only hides text until it is opened.

## Safety

- **Escaping**: all model-written and file text is HTML-escaped (as in 001). Embedded HTML files
  are shown as text, never rendered.
- **Secrets**: every embedded string passes through the `Redactor` of the loop's frozen
  configuration, including keys inside JSON (FR-041, SC-010).
- **No network**: nothing is loaded from outside the page. The one external link is the
  project's GitHub page in the sidebar, which only navigates when clicked. There is one inline
  script (the shared `assets/dashboard.js`), as in 001.

## Output report

The command prints:
- the path and the size in bytes;
- the five largest embedded items (path, bytes);
- the number of conversations marked unavailable;
- the files not embedded because they are over the size limit (path, bytes).

**Size limit**: a file over 5 MB (`fulldash.MAX_EMBED_BYTES`) is listed in the explorer with its
path and size, marked "Not embedded", and opened from disk. Conversations are always embedded
whole.
