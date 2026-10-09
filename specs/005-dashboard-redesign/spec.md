# Feature Specification: Dashboard Redesign

**Feature Branch**: `main` (no branch hook configured)

**Created**: 2026-10-09

**Status**: Draft

**Input**: User description: "Redesign the devloops dashboard. Replace the server-rendered single page
with a browser app that loads each view's data when it is opened; remove the summary page that
commands rewrite; replace full dashboards with an explicit export of the same app; add a live 'now'
panel, tokens and cost at every level, a trial drill-down, a plan view, a why-a-trial-failed view,
conversation viewer upgrades, and faster search." The developer confirmed every decision below in
conversation before this spec was written. Numbered 005 because "feature 004" is reserved for
frontend-only runs (constitution 2.0.0, spec 003 FR-019).

## Scope and Source Classification

**Problem**: The dashboard is one page that holds every view at once: overview, run, each loop,
every call, every file, the events. The server builds all of it again whenever anything in the
workspace changes, and the browser then rebuilds all of it before it can be used, so a refresh
waits several seconds. The same UI also exists three times (the summary page every command
rewrites, the exported full dashboard, the served page), so each change has to be made in several
places. And the questions a developer asks most often are slow to answer: what is running right
now, how many tokens did this loop use, why did this trial fail. A multi-line list item in a
Markdown file also shows only its first line.

**In scope**:
- one browser app for the dashboard, which loads a view's data only when that view is opened and,
  while following a run, refreshes only the view that is open;
- `devloops dashboard` serves it (starting a server, or reusing a running one) and opens it;
- `devloops dashboard --export` writes the same app, with the workspace's data inside it, as one
  self-contained, read-only file;
- removing the summary page that commands write, the automatic full dashboard at a stop, and the
  full-dashboards folder;
- new and improved views: a live "now" panel (A1), tokens and cost at every level (A2), a trial
  drill-down (A3), a plan view (A5), a why-a-trial-failed view (B6), conversation viewer
  upgrades (B8), and faster search (B10);
- fixing the Markdown renderer's multi-line list items;
- skills, README, and the 001/002 contracts updated to match.

**Out of scope** (the design MUST let these be added later without restructuring, FR-030):
- actions from the browser: approve, replan, answer questions, retry, stop, edit and resubmit;
- history across runs, trends, and alerts;
- a trial diff (B7) and frontend contract coverage (B9), which are later features.

**Source classification**:
- *Requirements* (the developer's words, confirmed in conversation): everything under In scope and
  Out of scope above, and the decisions in Clarifications.
- *Assumptions* (chosen here, open to correction): listed under Assumptions.
- *Revisions*: this feature revises specs/001-reusable-dev-loops (the per-command dashboard) and
  specs/002-devloops-init (FR-035 to FR-042d, `contracts/full-dashboard.md`, the dashboard skill).
  devloops is in development and has one user, so no migration is provided for removed settings,
  files, or fields.

## Clarifications

### Session 2026-10-09

- Q: Rewrite the dashboard as a separate frontend project (a framework and a build step), or keep
  it inside devloops? → A: Keep it inside devloops. The server sends data; the browser builds the
  page with plain scripts shipped with devloops. There is no framework and no build step, so
  installing devloops stays as it is. (This follows how lean-ctx built its dashboard.)
- Q: Keep the summary page (`dashboard.html`) that commands rewrite? → A: No. It is removed, with
  its setting. Commands print the running server's address, or the command that starts one.
- Q: Keep full dashboards? → A: As an explicit export only (`devloops dashboard --export`), built
  from the same app with the data inside it. No dashboard is written automatically when a run
  stops, and there is no full-dashboards folder any more.
- Q: Which new features are in this feature? → A: A1, A2, A3, A5, B6, B8, B10 (see In scope).
  Actions from the browser and history across runs are designed for, not built. B7 and B9 come
  later.
- Q: Where does `devloops dashboard --export` write when no path is given? → A: Inside the
  workspace, at `<workspace>/exports/<UTC time>.html`; a path can be passed instead (FR-011).
- Q: Fix the Markdown bug and add per-loop tokens separately first? → A: No. Both are part of this
  feature.
- Q: Does `devloops dashboard` keep the terminal until Ctrl+C, or run in the background? → A: In
  the foreground by default, as today; `--daemon` runs it in the background and returns, and
  `--stop` stops the project's running server (FR-001, FR-001a).
- Q: Should `devloops run` start a dashboard server by itself when none is running? → A: No. Run
  and decision commands only print the running server's address, or the command that starts one
  (FR-009).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A dashboard that opens fast and follows the run (Priority: P1)

A developer runs `devloops dashboard`. The browser opens on the overview, which shows within a
moment. Moving to a loop, the calls, or the files shows that view without first loading everything
else. While the run goes on, the open view updates in place; views not on screen are not touched
until they are opened.

**Why this priority**: The slow refresh is the problem that started this feature, and every other
view is built on this.

**Independent Test**: Serve a workspace with many calls and files. Time the first view after a
refresh and after switching views. Change a file of the workspace and confirm that only the open
view updates.

**Acceptance Scenarios**:

1. **Given** a workspace with 200 calls and 5,000 files, **When** the developer refreshes the
   page, **Then** the overview is usable within 1 second, and no other view's data has been loaded.
2. **Given** the overview is open, **When** the developer opens a loop, **Then** only that loop's
   data is loaded, and the view shows within 1 second.
3. **Given** a run is in progress and the loop view is open, **When** a trial ends, **Then** the
   loop view shows the new trial without a page reload, keeping its scroll position, open sections,
   and filters.
4. **Given** a server is already running for the project, **When** the developer runs
   `devloops dashboard` again, **Then** no second server starts, and the browser opens the running
   one's address.
5. **Given** the server stops, **When** the page next checks for changes, **Then** it shows that
   it is offline and keeps the data it has.

---

### User Story 2 - See what is running and what it costs (Priority: P1)

The developer wants to know, at a glance, what the run is doing now and what it has cost. A "now"
panel shows the loop, milestone, trial, and step that is running, how long it has run, and each
tool Claude uses as it happens. Tokens and cost appear for each loop, milestone, trial, step, and
call, split into input, output, cache write, and cache read.

**Why this priority**: Per-loop tokens is the first thing the developer asked for, and the "now"
panel answers the most common question during a run.

**Independent Test**: Run a fake loop and open the dashboard during a call: the now panel shows the
call and its tools as they happen. After the run, compare the tokens and cost shown at each level
with the sums of the recorded calls.

**Acceptance Scenarios**:

1. **Given** a call is running, **When** the developer opens the dashboard, **Then** the now panel
   shows the loop, milestone, trial, step, model, elapsed time, and the tools used so far, newest
   last, and adds each new tool within the refresh interval.
2. **Given** no call is running, **When** the developer opens the dashboard, **Then** the now panel
   says the run is idle and shows its status and next action, or what it is waiting for.
3. **Given** a loop with recorded calls, **When** the developer views its overview card and its
   loop view, **Then** each shows the loop's total tokens, and the loop view shows input, output,
   cache write, and cache read, the cache-hit rate, and the cost per milestone achieved.
4. **Given** a milestone, a trial, or a step, **When** the developer views it, **Then** its tokens
   and cost are shown with the same breakdown, and they add up to the loop's totals.

---

### User Story 3 - Find out why a trial failed (Priority: P1)

A milestone has failed trials. The developer opens a trial from the timeline and sees its steps,
the calls each step made, its validation result, and its evidence. A "why it failed" section lists
each failing criterion or check next to the evidence that decided it.

**Why this priority**: Diagnosing a failing milestone (like M08 on a real project, whose criterion
could never pass in the browser step) took reading several files by hand. This puts it on one
screen.

**Independent Test**: Use a workspace with a failed backend trial and a failed frontend trial.
Open each from the timeline and confirm that every failing item is shown with its evidence, and
that each step's calls open their conversations.

**Acceptance Scenarios**:

1. **Given** the trial timeline, **When** the developer selects a trial, **Then** a trial view
   opens showing its steps in order, each with its calls, duration, tokens, and cost, then the
   validation result and the evidence files.
2. **Given** a failed backend trial, **When** its trial view opens, **Then** each failing check is
   listed with its command, the response status, and its failures, and each failing criterion with
   what was observed.
3. **Given** a failed frontend trial, **When** its trial view opens, **Then** each failing
   criterion is listed with its steps, what was observed, and its screenshots; and the network log,
   the API contract problem or unmatched operations, and the unit-test exit code with a link to its
   log are shown where they decided the result.
4. **Given** a trial with a boundary violation, **When** its trial view opens, **Then** the
   violations are listed as a reason it failed.
5. **Given** a trial that was voided or interrupted, **When** its trial view opens, **Then** it
   says so and why, instead of a validation result.

---

### User Story 4 - Read the plan and its progress (Priority: P2)

The developer opens a loop's plan view: each milestone with its goal, acceptance criteria, tasks,
and the milestones it depends on, and its status. Open questions and assumptions are listed with
their answers.

**Why this priority**: The plan is the contract for the whole run, but today it can only be read as
raw files.

**Independent Test**: Open the plan view of a workspace with an approved plan and some achieved
milestones; confirm that every milestone, criterion, task, and dependency in the plan is shown
with the right status.

**Acceptance Scenarios**:

1. **Given** a loop with a stored plan, **When** the developer opens its plan view, **Then** every
   milestone is shown in plan order with its goal, status, trials used, dependencies, acceptance
   criteria, and tasks with their requirement references.
2. **Given** a milestone whose latest trial failed some criteria, **When** the plan view shows it,
   **Then** each of those criteria is marked failing and links to the trial view.
3. **Given** the plan is waiting for approval, **When** the developer opens the plan view, **Then**
   it says the plan is waiting for approval and which command approves or replans it.

---

### User Story 5 - Read a conversation quickly (Priority: P2)

The developer opens a call's conversation. Tool calls are folded to one line each; errors stand
out; and the files Claude changed are listed, each jumping to the tool call that changed it.

**Why this priority**: Conversations are long. Most of the time the developer is looking for the
error or the change that broke something.

**Independent Test**: Open a recorded conversation with errors and file edits; confirm that tool
calls are folded, errors are marked and countable, and each changed file jumps to its tool call.

**Acceptance Scenarios**:

1. **Given** a conversation, **When** it opens, **Then** each tool call shows as one line (tool
   name and a hint such as the command, path, or URL), unfolding on demand.
2. **Given** a conversation with failed tool calls, **When** it opens, **Then** the number of
   errors is shown in its header, each error is marked, and the developer can move from one error
   to the next.
3. **Given** a conversation in which Claude wrote or edited files, **When** it opens, **Then** a
   "Files changed" list shows each path once, and selecting one jumps to the tool call that last
   changed it.
4. **Given** a trial view, **When** it shows the trial's steps, **Then** it also lists the files
   changed during the trial, each with the step and call that changed it.

---

### User Story 6 - Search everything (Priority: P2)

The developer types in the "go to" palette. Names of views, milestones, calls, and files match at
once; from three characters, the text of files, conversations, and events also matches. Choosing a
result opens it at the match.

**Why this priority**: Search exists today; this keeps it and makes it fast enough to use as the
main way around a large workspace.

**Independent Test**: In a workspace with 200 calls, search for a string that appears in one
conversation and one file; confirm that both results appear within 1 second and open at the match.

**Acceptance Scenarios**:

1. **Given** the palette is open, **When** the developer types a name, **Then** matching views,
   loops, milestones, trials, calls, and files are listed as they type.
2. **Given** three or more characters, **When** the developer pauses typing, **Then** matches in
   file contents, conversations, and events are added, each with its line, and the first results
   show within 1 second.
3. **Given** an exported dashboard opened with no server, **When** the developer searches, **Then**
   the same kinds of results are found in the data inside the file.

---

### User Story 7 - Export a dashboard to keep or share (Priority: P3)

The developer runs `devloops dashboard --export`. One file is written. Opened on any machine,
without a network or devloops, it shows the same views as the served dashboard, as of the time of
the export, read-only.

**Why this priority**: The export replaces both the summary page and the full dashboards for
keeping a record of a run, but it is used less often than the live dashboard.

**Independent Test**: Export a workspace, copy the file alone to another folder, disconnect the
network, and open it: every view, file, and conversation within the size limit opens.

**Acceptance Scenarios**:

1. **Given** a workspace, **When** the developer runs `devloops dashboard --export`, **Then** one
   file is written and its path, size, largest embedded items, and items not embedded are printed.
2. **Given** an exported file, **When** it is opened with no network and no other file, **Then**
   every view of the served dashboard is available, with a notice that it is a snapshot taken at
   a given time, and nothing in it checks for changes.
3. **Given** configured secrets in the workspace's files, **When** the export is written, **Then**
   none of them appear anywhere in the file.
4. **Given** a file over the size limit, **When** the export is written, **Then** it is listed with
   its path and size and marked "not embedded".

---

### Edge Cases

- **Workspace with no loop started**: the overview says so and shows the run's setup state; other
  views say they have nothing yet instead of failing.
- **A file changes while it is open**: the viewer reloads it at the same position, or at its end
  when it was scrolled to the end (as today).
- **Data changes between two requests of one view**: the view shows one consistent version; a
  half-updated view is never shown.
- **Very large file or conversation**: the server streams it as today; the viewer asks before
  loading a file over 20 MB.
- **A recorded call with no conversation**: shown as unavailable, with the session ID and why.
- **Old or partial records** (a trial with no validation file, a call missing token fields): the
  missing values are shown as unknown, never as zero, and totals say they are partial.
- **Two browsers open on the same server**: each follows the run independently.
- **A run in another workspace**: the workspace switcher shows it; a view never mixes workspaces.
- **Markdown**: a list item that continues on the next line shows its whole text; nested lists,
  tables, and code blocks render as today.
- **Browser without scripts**: the served page says that the dashboard needs scripts enabled.
- **Export of a workspace during a run**: the export is consistent as of one moment and says that
  the run was still in progress.

## Requirements *(mandatory)*

### Functional Requirements

#### Serving and loading

- **FR-001**: `devloops dashboard` MUST serve the dashboard of the project's workspaces in the
  foreground until stopped (Ctrl+C), opening the requested workspace (default: the current one)
  in a browser unless told not to. If a server is already running for the project, it MUST NOT
  start another; it MUST print the running server's address, open it, and return. Serving is what
  `devloops dashboard` does with no option, so `--serve` is removed; opening the browser is the
  default, so `--open` is replaced by `--no-open`.
- **FR-001a**: `devloops dashboard --daemon` MUST start the server in the background, detached from
  the terminal, print its address once it answers, open the browser unless told not to, and
  return; when it cannot start, it MUST say why and exit non-zero. `devloops dashboard --stop`
  MUST stop the project's running server, whether started with or without `--daemon`, and remove
  its record; with no server running it MUST say so and succeed. A background server's output
  MUST go to a log file whose path `--daemon` prints.
- **FR-002**: The server MUST send the browser the app once and then only data: each view
  requests the data it shows when it is opened. Opening a view MUST NOT load the data of other
  views.
- **FR-003**: While following a run, the page MUST check for changes at a fixed interval (as today)
  and, when the workspace changed, reload only the data of the view on screen, plus the navigation
  and the now panel. Views not on screen MUST be reloaded when they are next opened.
- **FR-004**: An update MUST keep the view's scroll position, open sections, filters, and focus, and
  a file open in the viewer MUST be reloaded at the same position, or at its end when it was
  scrolled to the end.
- **FR-005**: The page MUST show when it is offline (the server does not answer) and when following
  is paused, and MUST keep showing the data it has.
- **FR-006**: The server MUST keep today's protections: it listens on the loopback address unless
  told otherwise; it requires a token beyond loopback; it rejects unexpected host names; it serves
  only files the workspace's listing contains; it hides configured secrets in everything it sends;
  and it sends the same security headers. It MUST accept only reading requests in this feature.
- **FR-007**: The server MUST work out a view's data only when asked, and MUST NOT work it out again
  while the workspace has not changed.

#### Removed outputs

- **FR-008**: Commands MUST NOT write `<workspace>/dashboard.html`. The `dashboard.light` setting,
  the `dashboard` field of `--json` results, and the summary page's code MUST be removed.
- **FR-009**: After a run or decision command, the output MUST point to the dashboard: the running
  server's address for the workspace when one is running, otherwise the `devloops dashboard
  --daemon` command (with `--workspace` when not the default). These commands MUST NOT start a
  server themselves. `--json` results MUST carry the address as `dashboard_url` when a server is
  running, and omit it otherwise.
- **FR-010**: No dashboard MUST be written automatically when a run stops. The
  `dashboard.full_on_stop` setting, the full-dashboards folder and its configuration, `init
  --track-dashboards`, and the list of earlier full dashboards in the page MUST be removed.

#### Export

- **FR-011**: `devloops dashboard --export [path]` MUST write one self-contained file holding the
  same app and the workspace's data as of one moment. It MUST open in a browser with no network,
  no server, and no other file, showing every view the served dashboard shows. With no path, it
  MUST write `<workspace>/exports/<UTC time>.html` (git-ignored with the workspace), never
  replacing an earlier export: a second export within the same second gets a `-2`, `-3`, …
  suffix. With a path, it MUST write that file, replacing it if it exists.
- **FR-012**: The export MUST embed every file and conversation the views list, with configured
  secrets hidden. A file over the size limit (5 MB, as today) MUST be listed with its path and size
  and marked "not embedded". Conversations MUST be embedded whole.
- **FR-013**: The export MUST be read-only: it MUST NOT check for changes, and it MUST show that it
  is a snapshot, when it was taken, the devloops version, the workspace, whether a run was in
  progress, and that it contains full Claude Code conversations.
- **FR-014**: The export MUST search its own data in the browser, with the same kinds of results as
  the served dashboard.
- **FR-015**: The export command MUST print the file's path and size, its five largest embedded
  items, the conversations marked unavailable, and the files not embedded.

#### Views

- **FR-016** (A1): Every view MUST show a "now" panel: when a call is running, its loop, milestone,
  trial, step, model, elapsed time, and the tools it has used so far (one line each, newest last);
  when none is running, the run's status and either its next action or what it waits for.
- **FR-017** (A2): Tokens and cost MUST be shown for the workspace, each loop (on its overview card
  and in its view), each milestone, each trial, each step, and each call, split into input, output,
  cache write, and cache read. A loop's view MUST also show its cache-hit rate (cache read divided by
  all input tokens) and its cost per milestone achieved. Totals at each level MUST equal the sum of
  the calls they contain; a total that includes calls with unknown values MUST say it is partial.
- **FR-018** (A3): The trial timeline MUST let the developer open any trial. A trial view MUST show
  the trial's outcome, its steps in order with each step's calls, duration, tokens, and cost, its
  validation result, its evidence files, and the files changed during it.
- **FR-019** (B6): A trial that did not pass MUST show a "why it failed" section listing each reason
  next to the evidence that decided it: failing checks with their command, response status, and
  failures; failing criteria with their steps, what was observed, and their evidence (screenshots
  shown as images); the API contract's problem or unmatched operations with the network requests;
  the unit tests' exit code with a link to their log; boundary violations; or why it was voided or
  interrupted.
- **FR-020** (A5): Each loop MUST have a plan view showing, in plan order, every milestone with its
  goal, status, trials used, dependencies, acceptance criteria (each marked passing, failing, or
  not yet checked, from the latest trial), and tasks with their requirement references; and the
  plan's open questions with their answers and its assumptions. When the plan waits for approval,
  the view MUST say so and name the command that approves or replans it.
- **FR-021** (B8): A conversation MUST show each tool call as one folded line (tool name and a hint)
  that unfolds on demand; MUST show the number of failed tool results in its header, mark each one,
  and let the developer move between them; and MUST list the files Claude wrote or edited, each
  once, jumping to the tool call that last changed it.
- **FR-022** (B10): The "go to" palette MUST match names of views, loops, milestones, trials, calls,
  and files as the developer types, and from three characters MUST add matches in file contents,
  conversations, and events, each opening at its line.
- **FR-023**: The views and features of today's served dashboard MUST remain: overview with
  "Needs attention", run, one view per loop, calls, questions, events, files explorer with its
  viewers (Markdown, JSON, JSON lines, code, logs, images, other files), workspace switcher, theme,
  and the conversation renderer's handling of every record type (contracts/full-dashboard.md).
- **FR-024**: Every view MUST have its own address, so a reload, the browser's back and forward
  buttons, and a copied link open the same view (and, for a trial, call, or file, the same item).

#### Markdown and safety

- **FR-025**: The Markdown viewer MUST show the whole text of a list item that continues on
  following lines, as a paragraph would.
- **FR-026**: Model-written and file text MUST never be inserted into the page as markup; Markdown
  MUST be built as page elements; HTML files MUST be shown as text; links MUST NOT be followed
  except to items in the dashboard (as today).
- **FR-027**: The served page and the export MUST load nothing from outside them (no network
  resources), as today.

#### Constraints and future

- **FR-028**: The dashboard MUST be part of devloops as it is installed today: it MUST NOT need a
  separate project, a build step, or tools beyond those devloops already needs.
- **FR-029**: Each view MUST be a separate part of the app, so a view can be added or changed
  without touching the others, and the data for each view MUST be a separate request.
- **FR-030**: The design MUST allow adding, without restructuring, (a) actions that change a run
  (approve, replan, answer questions, retry, stop, edit and resubmit), which would require writing
  requests with protection against requests from other sites and a token even on loopback, and (b)
  data that spans runs (history, trends, alerts). This feature MUST NOT implement either.

#### Skills and documentation

- **FR-031**: The `devloops-run` skill MUST report `dashboard_url` when present, and otherwise
  say that `devloops dashboard` shows the run live, instead of the summary page and
  full-dashboard paths; it MUST NOT start a dashboard server. *Revised during implementation:
  the `devloops-dashboard` skill, and the approve, replan, and retry skills, are removed (the run
  skill asks for those decisions); the dashboard is started by command only.*
- **FR-032**: The README and the affected contracts of specs 001 and 002 MUST be updated with
  "Revised by specs/005-dashboard-redesign" notes, and `contracts/full-dashboard.md` MUST be
  replaced by this feature's contracts.

### Key Entities

- **Dashboard app**: the page and its scripts and styles, shipped with devloops; the same for the
  served dashboard and the export.
- **View**: one screen of the app (overview, run, loop, plan, trial, calls, conversation, files,
  questions, events), with its own address and its own data.
- **View data**: what one view shows, worked out by the server from the workspace's records when
  asked, with secrets hidden; embedded in the export instead.
- **Workspace version**: a digest that changes whenever the workspace changes; the page compares it
  to decide when to reload the open view.
- **Now panel state**: the call that is running (if any) and its tools so far, from the loop's run
  records.
- **Export**: one file holding the app and every view's data as of one moment.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a workspace with 200 calls and 5,000 files (about twice the largest real
  workspace so far: 85 calls, 2,322 files, 46 MB), the first view is usable within
  1 second of a page refresh on the developer's machine, compared with several seconds today.
- **SC-002**: Opening any other view on that workspace shows it within 1 second.
- **SC-003**: While a run goes on, a change appears in the open view within the refresh interval
  plus 1 second, and views not on screen request no data.
- **SC-004**: For every loop, milestone, trial, and step, the tokens and cost shown equal the sum of
  the recorded calls (checked by tests on recorded workspaces).
- **SC-005**: For every failed trial in the test workspaces (backend and frontend), the trial view
  shows every failing check, criterion, contract problem, unit-test result, and boundary violation
  recorded in its validation result, with no file opened by hand.
- **SC-006**: Search returns its first results within 1 second on the 200-call workspace, served
  or exported.
- **SC-007**: An exported file copied alone to another machine, with no network, shows 100% of the
  views and of the embedded files and conversations.
- **SC-008**: 0 configured secret values appear in any data the server sends or in an export.
- **SC-009**: 0 files are written by run or decision commands for the dashboard.
- **SC-010**: Adding a new view needs one new view part and one new data request, with no change to
  other views (checked in review against FR-029).

## Assumptions

- "Reviewer notes" in B6 means what the validation step recorded about each criterion (its steps,
  what was observed, and its evidence) and each check's failures; devloops has no separate review
  step.
- The "now" panel reads a small view file that devloops writes while a call runs (the call and the
  tools used so far) and removes when the call ends; the engine never reads it (plan research
  R-8).
- "Files changed" (B8) covers files Claude wrote or edited through its file tools as recorded in the
  conversation; changes made by shell commands are not detected.
- Target files (the code Claude changed) are listed by path only; the dashboard serves workspace
  files, not the target repository, as today.
- The refresh interval and the 5 MB export limit stay as they are today.
- The developer's machine runs a current desktop browser; older browsers are not supported.
- The served dashboard is used by one developer at a time; several open pages are supported but
  not tuned for.

## Dependencies

- The run records devloops already writes: run state, invocation records, trial and validation
  files, evidence, events, the plan, prompts, conversations, and the run log.
- The current server's protections and file listing (spec 002 FR-042a to FR-042d), which this
  feature keeps.
