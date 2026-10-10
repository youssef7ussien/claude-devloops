# Data Model: Dashboard Redesign

Nothing here is stored by the engine except **Live call** (a view file). Every other entity is
worked out from the workspace's existing records on request (contracts/api.md), redacted, and
cached by workspace version.

## Totals (FR-017, research R-9)

The same shape at every level: workspace, loop, planning, milestone, trial, step, call.

| Field | Type | Rule |
|-------|------|------|
| `calls` | int | number of invocation records summed |
| `cost` | number (USD) | sum of `cost_usd` |
| `tokens` | `{input, output, cache_creation, cache_read, total}` | sums of the record's `tokens.*`; `total` is the sum of the four |
| `partial` | bool | true when a summed record lacks `tokens` or `cost_usd` |
| `seconds` | number \| null | wall time from first start to last end of the level's records or trials |

Loop level adds `cache_hit_rate` = `cache_read / (input + cache_creation + cache_read)` (null when
the denominator is 0) and `cost_per_achieved` = `cost / achieved` (null when none achieved).

**Validation**: the totals of a level equal the sum of the totals of its children (SC-004);
`partial` propagates upward.

## Workspace summary (`api/summary`)

`{workspace, generated_at, version, requirements, targets, status, totals, loops: [LoopCard],
run: RunState|null, attention: [AttentionItem], large_evidence: [{path, bytes}],
workspaces: [name], running: [loop]}`

- **LoopCard**: `{loop, status, status_reason, next_action, milestones: {total, achieved},
  trials, first_try, totals}`.
- **AttentionItem**: `{kind, loop, milestone?, trial?, call?, message, route}` — the kinds of today's
  "Needs attention" panel (stopped/paused loop and next action, failing criteria on the latest
  trial, unanswered questions, failed calls, evidence over 1 MB, milestones that passed only after
  failed or voided trials, interrupted loops).

## Loop (`api/loops/<loop>`)

`{loop, status, status_reason, next_action, approval, grants, inputs, ui_url, openapi_artifact,
totals (with cache_hit_rate, cost_per_achieved), planning: {trials: [TrialSummary], totals},
milestones: [MilestoneSummary], by_step: {<step>: Totals}, outputs: [FileRef]}`

- **MilestoneSummary**: `{id, title, status, trials: [TrialSummary], totals, seconds}`.
- **TrialSummary**: `{key, n, attempt, kind, status, reason, started_at, ended_at, seconds, totals,
  route}`. `key` is `n` or `n.k` for an earlier, voided attempt that shares the number.

## Plan (`api/loops/<loop>/plan`)

`{loop, status, approval, milestones: [PlanMilestone], open_questions: [Question],
assumptions: [{id, text, source}], stack, runtime, routes: {loop}}`

- **approval**: `{status: "waiting", commands: [approve, replan]}` while the plan waits (each
  command with `--workspace` when the workspace is not the default), `{status: "approved",
  approved_at, action}` once approved, else `{status: "none"}`.
- **PlanMilestone**: `{id, title, goal, status, trials_used, depends_on: [id], criteria:
  [{id, text, requirement_refs, state: "passing"|"failing"|"unchecked", trial_route?}], tasks:
  [{id, title, description, requirement_refs, status}], route}`. A criterion's `state` comes from
  the milestone's latest counted (not voided) trial with a validation result, so a trial still
  running, or one that failed before validating, leaves the last result shown: unchecked without
  one, failing when the result does not mention it (FR-068); `trial_route` links a failing one to
  that trial. The loop view's criteria come from the same trial, read the same way.
  `trials_used` counts the counted trials; `route` is the milestone in the loop view.

## Trial (`api/loops/<loop>/milestones/<id>/trials/<key>`)

`{loop, milestone, title, key, n, attempt, kind, status, reason, detail, started_at, ended_at,
seconds, totals, steps: [Step], validation: Validation|null, why: [Reason], evidence: [FileRef],
files_changed: [{path, step, tool, call_route, block}], routes: {loop, trials: [{key, status,
route}]}}`. `evidence` is every file in the trial's folder (none for an earlier voided attempt,
whose folder holds the later attempt's files).

- **Step**: `{step, totals, calls: [CallRef]}` in the order the calls ran.
- **Validation**: the trial's `validation.json` as recorded (schema `validation-result`), redacted.
- **Reason** (FR-019), one per cause, in this order:
  `{kind: "check", check_id, command, status, failures, evidence: [FileRef]}` |
  `{kind: "criterion", criterion_id, text, steps, observed, evidence: [FileRef]}` |
  `{kind: "contract", problem, unmatched_operations, network_requests}` |
  `{kind: "unit-tests", command, exit_code, log: FileRef}` |
  `{kind: "boundary", violations}` |
  `{kind: "voided"|"interrupted", message}` |
  `{kind: "failure", reason, detail}` (a failed trial with none of the above: its call failed).
  A criterion without a result counts as failing (FR-068).
- **State transitions** shown: `in-progress → passed | failed | void` (as in run.json).

## Call list and call (`api/calls`, `api/calls/<loop>/<seq>`)

- **CallRef**: `{loop, seq, step, milestone_id, trial, model, started_at, duration_ms, totals,
  failure_class, conversation: "copied"|"history"|"unavailable", route}`.
- **Call**: `CallRef` + `{ended_at, num_turns, is_error, subtype, api_error_status, timed_out,
  permission_denials, prompt: FileRef|null, settings: FileRef|null, prompt_sources, routes:
  {loop, trial|null}, records: [Record], errors: [record index], files_changed: [{path, tool,
  block}], unavailable_reason?}`. `files_changed` paths are relative to the loop's target when
  inside it; `block` is the record index of the tool use. A conversation that cannot be read
  makes `conversation` "unavailable", with `unavailable_reason` and no records.
- **Record**: one non-blank transcript line parsed and redacted (`{"raw": text}` when it is not
  JSON); its index is what `?at=` and `errors` refer to.

## Files (`api/files`, `api/files/<id>`)

- **FileRef**: `{id, path, kind, lang, size, version, missing?}`. `id` is today's anchor
  (`f-<slug>`), stable for a path.
- **Tree**: `[{name, children?: [Tree], file?: FileRef, badge?}]` per loop (Inputs, Plan,
  Milestones → trials → evidence, Calls, Outputs, Run state, progress.md), then `run/` and the
  workspace's own files.
- **Content**: the bytes as today's `file/<anchor>` (redacted text, image, or download).

## Events, questions, index, search

- **Event**: an `events.jsonl` record plus `loop` and `n`, its place in that loop's file.
- **Question**: `{loop, id, question, context, affects, suggested_answer, answer?, status}`.
- **Index** (`api/index`): `[{kind: "view"|"loop"|"milestone"|"trial"|"call"|"file", label,
  detail, route}]`.
- **Search corpus item**: `{kind: "file"|"call"|"event", id, label, route, text}`, in search
  order: listed files (viewer text; a file streamed whole, over 16 MB, as it is), each loop's
  calls (one line per Record: what the conversation view shows of it, without ids, times, or
  set-up records), each loop's events (one line per event). The served search keeps these texts
  per item by size and modification time, up to 256 MB (UTF-8) shared by the two workspaces
  searched last; the export embeds them (`d:search-corpus`).
- **SearchHit**: `{kind, id, label, route, line, before, match, after}`: the first match in an
  item, case-insensitive, from 3 characters, at most 40. `route` opens it at the match: a file at
  `?line=<line>`, a call at `?at=<line - 1>` (its record), an event at
  `#/events?loop=<loop>&at=<line - 1>` (its `n`).

## Live call (`<loop>/state/live.json`, research R-8)

| Field | Type |
|-------|------|
| `loop`, `step`, `milestone_id`, `trial`, `model`, `session_id` | as the invocation record |
| `started_at` | ISO time |
| `pid` | the devloops process |
| `tools` | `[{at, name, summary}]`, the last 200, oldest first |

**Lifecycle**: written at `call_started`; replaced atomically after each `tool_use`; deleted at
`call_ended` (also on failure). Shown only while the loop's lock is held by the live process
that wrote it (the lock's `pid` is the file's);
otherwise ignored, and deleted by the next call's start. Never read by the engine; the write
boundary audit treats it as the driver's own write, like `run.log`.

## Now (`api/now`)

`{running: true, call: LiveCall, elapsed_seconds}` or `{running: false, status, loop,
next_action, waiting_for, busy}`: `loop` is the loop the overall status comes from, `waiting_for`
is `approval`, `questions`, `retry`, or null, and `busy` lists the loops a command runs between
calls (their next action is then null). Worked out on every request, not kept per version.

## Export (FR-011–FR-015)

One HTML file: the app shell, stylesheet, and joined script inline; one
`<script type="application/json" id="d:<route key>">` per API response; a root
`data-source="embedded"`, `data-exported-at`, `data-devloops-version`, `data-workspace`,
`data-running` (bool). File contents over 5 MB are replaced by `{not_embedded: true, size}`.

**Naming**: `<workspace>/exports/<YYYYMMDDTHHMMSSZ>.html`, `-2`, `-3`, … on a same-second collision,
created exclusively; or the given path, replaced.

## Server record (unchanged, plus the log)

`$XDG_RUNTIME_DIR/devloops/serve-<project hash>.json` (`{pid, hostname, host, port, local_url,
token: bool, project, started_at, daemon: bool, log?}`), and for a daemon its log
`serve-<project hash>.log` beside it.
