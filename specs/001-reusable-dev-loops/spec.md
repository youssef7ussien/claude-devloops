# Feature Specification: Reusable Development Loops

**Feature Branch**: `main` (no branch hook configured)

**Created**: 2026-09-27

**Status**: Draft

**Input**: User description: "Create the specification for Goal #1 only: implementing the reusable
development loops (backend-dev, frontend-dev, shared loop functionality, optional orchestration)
from `specs/claude-loops/task-description.md`. Do NOT specify the application described by the PRD."

## Scope and Source Classification

**In scope**: the reusable development-loop infrastructure only — the `backend-dev` loop, the
`frontend-dev` loop, functionality shared by both, and an optional orchestrator that can drive them.

**Out of scope**: the application described by any PRD (including the reference application in
`quickflow/PRD.md`), its requirements, design, stack, and decomposition. The reference PRD is
context showing the kind of input the loops will consume; nothing in it is a requirement here.

Every requirement below is tagged with its source:

| Tag | Meaning |
|-----|---------|
| **[E]** | **Explicit** — stated in the task description (quoted or closely paraphrased) |
| **[I]** | **Implied** — not stated, but necessary to satisfy an explicit requirement or a MUST in the constitution; the justification is given inline |
| **[C]** | **Constitution** — required by a MUST in `.specify/memory/constitution.md` (principle cited) |
| **[D]** | **Decided** — an ambiguity in the task description resolved by the user (see Clarifications) |
| **[R]** | **Review decision** — adopted by the author from the requirements review in `checklists/loops-review.md` (item cited as CHKnnn) or from the cross-artifact analysis (`/speckit-analyze`, finding cited by its ID) |

Items that are neither stated nor necessary are recorded under **Open Questions** or
**Assumptions**, not as requirements.

## Clarifications

### Session 2026-09-27

- Q: What do the "3 trials" in the stop condition count, and what happens when they run out? →
  A: Trials are counted per milestone (phase). When a milestone runs out of trials, the whole loop
  run stops; no later milestone is attempted in that run.
- Q: What is the "UI artifact URL"? → A: An output: the URL where `frontend-dev` serves the
  frontend it built. Playwright tests that URL. There is no design or mockup input.
- Q: How are one application's loop records kept separate from another's? → A: Each target
  application or run gets its own workspace folder holding its own `outputs/`, `state/`, and
  `progress.md`. The loop's reusable files are not changed between applications.
- Q: When a loop finds a requirement it cannot resolve (missing, contradictory or unclear), what
  should it do? → A: During planning, it lists all open questions in its outputs and pauses for the
  developer's answers or approval before implementing. After approval, any new issue is recorded as
  an explicit assumption in the milestone file, work continues, and the assumption is flagged for review
  at the end of the run.
- Q: How should a loop decide which technology stack to build with for a given application? →
  A: In priority order: the stack of existing code in the target project; otherwise a stack named in
  the requirements or run configuration; otherwise a stack the loop proposes during planning, which
  the developer approves at the planning pause.
- Q: When a loop is asked to implement a single user story, how is that story given to it? → A:
  Either as a standalone Markdown file containing only that story, or as a PRD file plus an
  identifier for the story within it.
- Q: Where should a loop write the application code it builds, and where is it allowed to make
  changes? → A: In a target project directory given at run time, which may be inside or outside
  this repository. The loop writes only there and in its run workspace.
- Q: If the requirements file changes after a loop has started (partially completed), what should
  the loop do when it is run again? → A: Detect the change by comparing against a record of the
  input taken at planning, stop, and report it. The developer decides whether to start a new run.

## User Scenarios & Testing *(mandatory)*

The actor in every story is a **developer** who wants Claude Code to build (part of) an application
from written requirements, using the loops in this repository.

### User Story 1 - Build a backend from requirements (Priority: P1)

A developer points the `backend-dev` loop at a requirements document (a full PRD or a single user
story). The loop plans the backend work as milestones with tasks, writes the milestone files to its
`outputs/`, then implements the milestones one at a time. After each milestone it verifies the implemented
endpoints with HTTP requests issued via curl, and it produces a Swagger (OpenAPI) description of the
backend endpoints. Completed tasks are marked in the milestone files, in `progress.md`, and in `state/`.

**Why this priority**: The backend loop is the first required loop, and the frontend loop depends on
its Swagger output. It alone delivers a working, verified backend.

**Independent Test**: Run only `backend-dev` against a small requirements document. It passes when
the loop creates milestone files, backend code, and a Swagger document, and when every milestone has recorded
curl results showing the specified behavior.

**Acceptance Scenarios**:

1. **Given** a requirements document and no prior loop state, **When** the developer starts
   `backend-dev`, **Then** the loop writes one Markdown file per milestone to its `outputs/`, each
   listing that milestone's tasks, before it implements any code.
2. **Given** a milestone whose tasks are implemented, **When** the loop finishes the milestone, **Then** it
   exercises that milestone's endpoints with curl and records the requests and observed responses as
   validation evidence.
3. **Given** a milestone whose curl validation succeeded, **When** the loop marks the milestone complete,
   **Then** the milestone's tasks appear as achieved in the milestone file, in `progress.md`, and in
   `state/`.
4. **Given** an implemented backend, **When** the loop completes, **Then** a Swagger document
   describing the implemented endpoints exists and matches the endpoints that were verified.

---

### User Story 2 - Build a frontend from requirements and a backend contract (Priority: P1)

A developer points the `frontend-dev` loop at a requirements document and a backend Swagger
document. The loop plans the frontend work as milestones with tasks, writes the milestone files to its
`outputs/`, implements each milestone, and after each milestone verifies the running UI at its URL
using the Playwright MCP server. Progress is marked the same way as in the backend loop.

**Why this priority**: The frontend loop is the second required loop. It also provides the only
browser-level verification of the resulting application.

**Independent Test**: Run only `frontend-dev` with a requirements document and an existing Swagger
document. It passes when the loop creates milestone files and frontend code, and when each milestone has
recorded Playwright results against the UI URL.

**Acceptance Scenarios**:

1. **Given** a requirements document and a Swagger document, **When** the developer starts
   `frontend-dev`, **Then** the loop writes one Markdown file per milestone to its `outputs/` before it
   implements code.
2. **Given** a completed frontend milestone, **When** the loop validates it, **Then** it
   drives the UI at its URL through the Playwright MCP server and records the observed results.
3. **Given** a Swagger document, **When** the frontend calls the backend, **Then** those calls use
   the endpoints described in that Swagger document.
4. **Given** that Playwright validation for a milestone failed, **When** the loop evaluates the milestone,
   **Then** the milestone is not marked achieved.

---

### User Story 3 - Stop safely, retry within limits, and resume (Priority: P1)

A developer's loop run is interrupted (session ends, machine restarts) or a milestone keeps failing
validation. The loop stops after at most the configured number of trials (3 by default), records why,
and on the next start resumes from its persisted state without redoing completed work.

**Why this priority**: The stop condition is an explicit requirement, and the constitution
(Principles IV and V) requires bounded, recoverable automation. Without this story, neither
long-running loop is safe to leave unattended.

**Independent Test**: Force a milestone to fail validation every time. Confirm the loop stops after
the configured number of trials and records the failure. Then interrupt a healthy run mid-milestone,
restart it, and confirm no completed task is executed again.

**Acceptance Scenarios**:

1. **Given** a milestone that fails validation on every attempt, **When** the loop has made the
   configured number of trials (default 3), **Then** it stops working on that milestone, records the
   failure and the last validation evidence in `state/` and `progress.md`, makes no further
   attempts, and ends the whole loop run without starting any later milestone.
2. **Given** a run interrupted after some tasks were marked achieved, **When** the developer starts
   the same loop again with the same inputs, **Then** it continues from the first unachieved task and
   does not re-implement achieved tasks.
3. **Given** a milestone that validated successfully, **When** the loop evaluates its stop
   condition, **Then** the milestone counts as complete and the loop proceeds or finishes.

---

### User Story 4 - Implement a single user story (Priority: P2)

A developer gives a loop a single user story instead of a full PRD. The loop plans and implements
only what that story needs, and records it in the same artifact structure.

**Why this priority**: This input mode is explicitly required (Hint 2). It builds on the same
mechanics as Stories 1 and 2.

**Independent Test**: Run a loop with a one-story input. Confirm that its milestone files, code changes,
and validation cover only that story.

**Acceptance Scenarios**:

1. **Given** a single user story as input, **When** the loop plans, **Then** its milestones and tasks
   are derived only from that story.
2. **Given** a single user story and a project with existing code, **When** the loop implements the
   story, **Then** it does not change code unrelated to the story.
3. **Given** a PRD file plus a story identifier, **When** the loop plans, **Then** it may read the
   rest of the PRD for context (shared rules, data definitions), but it plans tasks only for the
   identified story.
4. **Given** a PRD file plus a story identifier that does not appear in the PRD, **When** the
   loop checks its inputs, **Then** it stops with an input error naming the missing identifier.

---

### User Story 5 - Run both loops through an orchestrator (Priority: P2)

A developer starts one orchestrator run that drives `backend-dev` and `frontend-dev` for the same
requirements, passing the backend's Swagger output to the frontend loop.

**Why this priority**: Required ("through orchestrator or direct use any of them"). It is still
secondary, because each loop must work on its own first.

**Independent Test**: Start the orchestrator on a requirements document. It passes when both loops
run, the frontend loop receives the backend loop's Swagger document, and each loop keeps its own
artifacts exactly as it would when run directly.

**Acceptance Scenarios**:

1. **Given** a requirements document, **When** the developer starts the orchestrator, **Then** it
   invokes the backend and frontend loops and hands the backend Swagger output to the frontend loop.
2. **Given** an orchestrated run where one loop stopped on failure, **When** the orchestrator
   evaluates the run, **Then** it records which loop stopped and why, and it does not start work that
   depends on the failed output.
3. **Given** the loops, **When** they are run directly without the orchestrator, **Then** they
   behave the same as they do under the orchestrator.

---

### User Story 6 - Reuse the loops for a different application (Priority: P3)

A developer uses the same loops, unchanged, to build an application whose requirements differ from
the reference application.

**Why this priority**: Reusability is the core purpose (Hint 2; constitution Principle II). It is
listed last because it is proven by running Stories 1–5 on different inputs.

**Independent Test**: Run the loops on a second requirements document from an unrelated domain,
changing only the inputs and configuration. No loop instructions or shared infrastructure may change.

**Acceptance Scenarios**:

1. **Given** a requirements document for an application other than the reference application,
   **When** the developer runs the loops, **Then** they produce the same kinds of artifacts and
   verification without edits to the loop infrastructure.
2. **Given** the loop infrastructure, **When** it is inspected, **Then** it contains no
   reference-application-specific requirements, business rules, entities, or UI/API behavior.

---

### Edge Cases

- **Missing or unreadable input**: The requirements file does not exist, is empty, or (for
  `frontend-dev`) no Swagger document is available. The loop stops before planning and records the
  missing input.
- **Ambiguous requirements found during planning**: The loop lists them as open questions and
  pauses before implementing (FR-053). It does not turn a guess into a requirement (constitution
  Principle I).
- **Ambiguous requirements found after approval**: The loop records an explicit, flagged assumption
  in the milestone file and continues (FR-055).
- **Validation target not reachable**: The backend or frontend cannot be started or reached, so
  curl or Playwright cannot run. This counts as a failed validation trial, not a pass.
- **Validation passes but behavior is wrong**: A process starts or code compiles, but the observed
  behavior does not match the requirement. This counts as a failure (Principle III).
- **Re-run after completion**: Starting a loop whose state shows all milestones complete makes no
  changes and reports that the work is already complete.
- **Changed inputs between runs**: The requirements document (or Swagger document) changes after a
  partial run. The loop detects the change, stops, and reports it without replanning or continuing
  (FR-051a).
- **Trials exhausted mid-plan**: A milestone exhausts its trials while later milestones remain. The
  loop run stops; no later milestone is started, whether or not it depends on the failed one
  (D-1).
- **Workspace reuse**: A run is started against a workspace that belongs to a different application.
  See FR-051.
- **Interrupted trial**: A session ends in the middle of a trial. On the next start, that trial is
  recorded as failed with reason *interrupted* and counts toward the limit (FR-030a).
- **Concurrent runs**: A second run is started on a workspace that already has an active run. The
  second run refuses to start (FR-065).
- **Claude Code service failure**: A call fails because of an outage, rate limiting, or expired
  authentication. The run stops as *stopped-on-service-error* without consuming a trial (FR-067).
- **Story depends on an unimplemented story**: In single-story mode, the story needs another story
  that has not been built. The loop records the dependency as an open question at the planning pause
  and does not implement the other story (D-4, FR-010a; R, CHK028).
- **Tool-managed caches**: Installing dependencies writes to package caches outside the target.
  This is allowed and is not a boundary violation (FR-035b).
- **Token usage unavailable**: The run cannot measure token consumption for a milestone. The loop
  records it as unavailable rather than omitting the field or inventing a number.

## Requirements *(mandatory)*

### Functional Requirements

#### Loop structure (shared by both loops)

- **FR-001** [E, located per D-3]: Each loop MUST have its own `Loop-instructions.md`, `task.md`,
  `progress.md`, `state/` folder, and `outputs/` folder. `Loop-instructions.md` is part of the
  reusable loop. `progress.md`, `state/`, and `outputs/` belong to a run workspace (FR-049).
  `task.md` exists in both places: the loop's copy is a standing-assignment template, and each
  workspace has a copy filled in for that run (D-10).
- **FR-002** [E]: Each loop's `outputs/` MUST contain one Markdown file per milestone (the task
  description's "spec or milestone"), listing that milestone's tasks.
- **FR-003** [E]: Tasks MUST be marked as achieved in the relevant `outputs/` milestone file, in
  `progress.md`, and in `state/` when they complete.
- **FR-004** [E]: `progress.md` MUST list every implemented action item and, for each milestone,
  record its start time, end time, and token consumption.
- **FR-004a** [R, CHK010]: Token consumption MUST be recorded as four figures: input, output,
  cache-creation, and cache-read tokens. Cost MUST also be recorded where available. Each figure
  is summed over all Claude Code calls of the milestone.
- **FR-004b** [R, CHK011]: A milestone's start time is the start of its first trial, and its end
  time is the end of its last validation, even when the milestone spans several runs or
  interruptions. The start and end time of every trial MUST also be recorded.
- **FR-005** [E, scoped by D-1]: Each loop MUST count trials per milestone (phase). A milestone is
  finished when it is complete and validated. If a milestone fails validation on its final trial
  (the configured trial limit, default 3; FR-006; wording per R, CHK008), the whole loop run MUST stop and MUST NOT start
  any later milestone in that run.
- **FR-006** [C, Principle V]: The trial limit MUST be configurable, and 3 MUST be the default.
- **FR-007** [C, Principle V]: When a loop stops because trials ran out, it MUST keep all state and
  record the failure: which milestone failed, how many trials ran, and the last validation evidence.
- **FR-008** [E]: Unit testing MUST be supported as optional extra verification in both loops. It
  MUST NOT replace the required curl or Playwright validation. When unit tests are enabled for a
  run, a failing unit-test run MUST fail the milestone's validation [R, CHK013]. When they are
  disabled, they have no effect on validation.

#### Inputs

- **FR-009** [E]: Both loops MUST accept a full set of project requirements (a PRD Markdown file) as
  input.
- **FR-010** [E, form set by D-6]: Both loops MUST accept a single user story as input, in either
  of two forms: (a) a standalone Markdown file containing only that story, or (b) a PRD file plus an
  identifier for the story within it. In both forms the loop MUST limit its planned work to that
  story.
- **FR-010a** [I — from D-6 form (b)]: With form (b), the loop MAY read other parts of the PRD as
  context for the story. It MUST NOT plan or implement other stories from the PRD.
- **FR-010b** [I — from D-6 plus FR-013]: With form (b), if the story identifier is not found in
  the PRD, the loop MUST stop with an input error that names the missing identifier.
- **FR-011** [E]: `frontend-dev` MUST also accept the backend Swagger document as input.
- **FR-012** [I — needed to run any application's requirements, Hint 2]: The requirements input
  MUST be supplied at run time (for example, as a path). It MUST NOT be embedded in the loop
  infrastructure.
- **FR-013** [I — a loop cannot plan without its required inputs]: A loop MUST check that its
  required inputs exist and are readable before planning. If one is missing, it MUST stop and record
  which input is missing.
- **FR-013a** [R, CHK029]: For `frontend-dev`, an API specification that cannot be parsed as an
  OpenAPI document MUST stop the run with an input error.
- **FR-013b** [R, CHK037]: Before planning, a loop MUST check that the tools it requires are
  available: the Claude Code CLI for both loops, curl for `backend-dev`, and the Playwright MCP
  server for `frontend-dev`. If one is missing, it MUST stop with an input error that names the
  tool.

#### backend-dev loop

- **FR-014** [E]: `backend-dev` MUST plan the backend work as milestones with tasks and write the milestone
  files to its `outputs/` before implementing.
- **FR-015** [E]: `backend-dev` MUST implement the backend code in the stack selected under
  FR-057.
- **FR-016** [E; format per R, CHK026]: `backend-dev` MUST produce a Swagger (OpenAPI 3)
  description of the backend endpoints as a machine-readable document. Serving an interactive
  Swagger page is optional.
- **FR-017** [E]: After finishing each milestone, `backend-dev` MUST test that milestone with curl commands.
- **FR-018** [I — from FR-017 plus constitution Principle III]: A milestone's curl tests MUST check
  observable responses (status and content) against the milestone's requirements. A server that merely
  starts or answers MUST NOT count as passing.
- **FR-019** [I — the Swagger is the frontend loop's contract, FR-011; scoped per R, CHK025]: The
  Swagger document handed to `frontend-dev` (the published artifact) MUST describe only endpoints
  verified in achieved milestones. The working copy in the target project may change during a
  milestone.

#### frontend-dev loop

- **FR-020** [E]: `frontend-dev` MUST plan the frontend work as milestones with tasks and write the
  milestone files to its `outputs/` before implementing.
- **FR-021** [E]: `frontend-dev` MUST implement the frontend code in the stack selected under
  FR-057.
- **FR-022** [E, defined by D-2]: `frontend-dev` MUST serve the frontend it built at a URL, record
  that URL as an output, and test that URL with the Playwright MCP server as each milestone is
  done. The loop takes no UI design or mockup URL as input.
- **FR-023** [I — from FR-022 plus constitution Principle III]: Playwright validation MUST check
  observable UI behavior required by the milestone (content present, interactions producing the expected
  result). A page that merely loads MUST NOT count as passing. Each UI criterion result MUST include
  what was observed and at least one stored evidence item [R, CHK022].
- **FR-024** [I — from FR-011]: The frontend MUST call the backend only through the endpoints
  described in the supplied Swagger document.

#### Iteration, next unit of work, and completion

- **FR-025** [E, plus D-4]: Each loop MUST follow the sequence plan → planning approval (FR-053) →
  implement a milestone → validate the milestone → mark it achieved → next milestone.
- **FR-026** [I — needed to avoid repeating work (constitution Principle IV) and to resume]: A loop
  MUST choose its next unit of work from its persisted state: the first task that is not achieved
  and whose milestone has not failed or been blocked.
- **FR-027** [C, Principle III]: A task or milestone MUST NOT be marked achieved until its required
  validation succeeds.
- **FR-028** [C, Principle V]: A loop run MUST finish in one of these explicitly recorded outcomes:
  - *completed*: all planned milestones validated;
  - *stopped-on-failure*: trials exhausted (FR-005, FR-061), the call cap reached (FR-062), or a
    milestone needs input (FR-055a);
  - *stopped-on-input-error*: FR-010b, FR-013, FR-013a, FR-013b, FR-035c, FR-051, or FR-051a;
  - *stopped-on-service-error*: FR-067 [R, CHK007];
  - *awaiting-approval*: planning finished and paused under FR-053.
- **FR-029** [I — from FR-028 plus the Edge Cases]: Starting a loop whose state is already
  *completed* for the same inputs MUST make no changes and MUST report that the work is complete.

#### Execution limits and recovery

- **FR-061** [R, CHK001]: Invalid or unusable planning output MUST count as a planning trial,
  under the same trial limit as milestones (FR-006). Running out of planning trials MUST end the
  run as *stopped-on-failure*. This stop is final for the workspace. Trial grants (FR-063) apply
  only to milestones, and the developer starts a new workspace instead, which loses nothing
  because no code has been written at that point [R, analysis U1].
- **FR-062** [R, CHK002; constitution V]: Each Claude Code call MUST have a configurable time limit,
  and each run a configurable maximum number of calls. A call that exceeds its time limit MUST count
  as a failed trial. Reaching the call maximum MUST end the run as *stopped-on-failure*. The values
  belong in configuration.
- **FR-063** [R, CHK003]: After *stopped-on-failure*, a developer MAY explicitly grant a new trial
  budget to one failed milestone. The grant, its reason, and its time MUST be recorded. Without such
  a grant, starting the loop again MUST make no changes and MUST report the stop.
- **FR-065** [R, CHK005]: Only one loop run MAY be active per workspace. A second run MUST refuse to
  start and MUST report the active run.
- **FR-067** [R, CHK007]: A Claude Code call that fails for reasons outside the work, such as the
  service being unavailable, rate limiting, or failed authentication, MUST stop the run as
  *stopped-on-service-error* with the reason recorded. It MUST NOT consume a trial.

#### State, recovery, and traceability

- **FR-030** [C, Principle IV]: Loop state MUST persist on disk and MUST be enough to resume after
  an interruption without redoing achieved tasks.
- **FR-030a** [R, CHK004]: A trial interrupted before its result is recorded MUST count as a failed
  trial with reason *interrupted*.
- **FR-031** [C, Principle IV]: State MUST record, for each milestone: its status, trial count, and
  the location of its validation evidence.
- **FR-032** [C, Principle VIII]: Validation evidence (the curl requests and responses, and the
  Playwright observations) MUST be kept as artifacts that `progress.md` or `state/` references.
- **FR-033** [I — the full-task deliverable requires a spreadsheet of "all used prompts and session
  IDs"; wording per R, CHK012]: Each loop MUST record the session ID and full prompt of **every**
  Claude Code call, tagged with its milestone and trial, so that deliverable can be compiled. Producing the spreadsheet itself is outside this spec.
- **FR-034** [I — the progress record may be edited mid-run; promoted from A-3 per R, CHK017]:
  `state/` is the authoritative record. The milestone files and `progress.md` are views derived
  from it. If they disagree about a task's status, the loop MUST NOT treat the task as achieved
  unless `state/` shows it validated.
- **FR-066** [R, CHK006; constitution VIII]: Every planned task and acceptance criterion MUST cite
  at least one requirement or story identifier from the input.
- **FR-068** [R, CHK021]: A milestone's validation MUST produce a result for every one of its
  acceptance criteria. A criterion with no result counts as failed.
- **FR-069** [R, CHK023]: A milestone's validation checks MUST NOT be weakened after its first
  trial. Pass or fail MUST be decided from recorded evidence, not from the implementing step's own
  claim.

#### Handling incomplete or ambiguous requirements

- **FR-053** [D-4]: After planning, each loop MUST record every open question it found in the
  requirements in its outputs. It MUST then pause before implementing and resume only after the
  developer answers the questions or approves the plan. The developer MAY either approve (the
  answers become binding context) or request replanning with the answers (the loop pauses again).
  Both actions and the answers MUST be recorded [R, CHK030].
- **FR-053a** [D-12]: Every open question, at planning and as *needs-input*, MUST carry the
  answer the loop suggests and why. An answer the developer leaves empty accepts the suggestion
  when they approve (or `retry` after *needs-input*): the suggestion is written into the answers
  file, marked as an accepted suggestion, before the file is fingerprinted. A question with neither
  an answer nor a suggestion still blocks `retry`.
- **FR-054** [D-4, plus FR-030]: The planning pause MUST be recorded in state, so that starting the
  loop again after approval continues with implementation instead of replanning.
- **FR-055** [D-4]: After approval, a loop that finds a new ambiguity MUST record an explicit
  assumption in the relevant milestone file, continue, and list every such assumption for review in its
  final report.
- **FR-055a** [R, CHK032]: An assumption that would remove, add, or contradict a requirement MUST
  NOT be made after approval. Instead, the milestone MUST fail immediately with reason
  *needs-input*, without using its remaining trials. That ends the run (D-1), and the developer can
  continue under FR-063.
- **FR-055c** [D-12]: An opt-in setting (`questions: accept-suggested`, default `ask`) MAY replace
  the developer's acceptance with an automatic one. Then the planning pause approves the plan
  with the suggested answers and implementation continues, and a *needs-input* trial fails alone
  (it counts) while its suggestions are accepted for the next trial, instead of ending the run. A
  question without a suggestion, or one raised on the milestone's last trial, still pauses or stops
  the run as under FR-053 and FR-055a. Every
  automatically accepted answer MUST be marked in the answers file, recorded in state and events,
  listed for review in the final report, and flagged in the dashboards.
- **FR-056** [I — from D-4 plus FR-040]: Under the orchestrator, each loop's planning pause MUST
  also pause the orchestrated run. Work that depends on the paused loop MUST NOT start.

#### Stack selection

- **FR-057** [D-5]: Each loop MUST choose its stack in this priority order: (1) the stack of
  existing code in the target project; (2) a stack named in the requirements input or the run
  configuration; (3) a stack the loop proposes during planning.
- **FR-058** [D-5]: Each loop MUST record the chosen stack and which of the three sources it came
  from in its planning outputs. A proposed stack (source 3) MUST be approved at the planning pause
  (FR-053) before implementation begins.
- **FR-059** [I — from D-5 plus constitution Principle II]: The reusable loop infrastructure MUST
  NOT assume or default to any particular stack.
- **FR-060** [I — from D-5 plus constitution Principle I]: If existing code and an explicitly
  named stack conflict, the loop MUST apply the priority order (existing code) and MUST record the
  conflict as an open question for the planning pause, so it is never resolved silently.

#### Safeguards against uncontrolled or unrelated change

- **FR-035** [C, Principle IV]: Loops MUST change only what the current task needs. They MUST NOT
  refactor unrelated code.
- **FR-035a** [D-7; per loop run per R, CHK015]: Each loop run MUST be given a target directory,
  which may be inside or outside this repository. The loop MUST write application code only in that
  directory. The backend and frontend loops of one application MAY use different targets, and
  neither may write to the other's.
- **FR-035b** [D-7]: A loop MUST NOT create, modify, or delete files outside its target project
  directory and its run workspace. This includes the reusable loop files and other applications'
  directories and workspaces. The only exceptions are caches managed by tools (for example, package
  manager caches and browser downloads) and system temporary directories [R, CHK033].
- **FR-035c** [I — from D-7 plus FR-013]: If the target project directory is not given, or cannot
  be created or written, the loop MUST stop with an input error before planning.
- **FR-035d** [I — from D-7 plus FR-049]: The run workspace MUST record each loop's target
  directory, so a resumed run and the orchestrator use the same one.
- **FR-036** [C, Principle IV and VII]: Loops MUST inspect and keep the target project's existing
  conventions, tooling, and structure when the project already has code.
- **FR-037** [C, Principle II]: Loop infrastructure (instructions, shared functionality,
  orchestrator) MUST NOT contain requirements, business rules, entities, or UI/API behavior specific
  to any one application, including the reference application.
- **FR-070** [R, CHK034]: Loops MUST NOT write secrets named in configuration into state,
  evidence, or recorded prompts. Workspaces containing evidence MUST be reviewable before they are
  committed.
- **FR-071** [R, CHK035]: Each automated step MUST run with only the tool permissions it needs.
  Permission to change files MUST be limited to the loop's target directory. The specific
  permission modes belong in the plan.

#### Shared functionality

- **FR-038** [C, Principle VI]: Behavior common to both loops MUST be defined once and reused by
  both, not duplicated. That behavior includes: input checks, milestone-file format, progress and state
  recording, trial counting and stop evaluation, token/time/session recording, and resume logic.
- **FR-039** [C, Principle VI]: Each loop MUST be runnable on its own, without the other loop or the
  orchestrator. For `frontend-dev`, this assumes a Swagger document is supplied. When run directly,
  `frontend-dev` MUST accept either the address of a running backend or instructions for starting
  one. Without either, criteria that need a backend MUST fail, never pass silently [R, CHK027].

#### Orchestration

- **FR-040** [E]: An optional orchestrator MUST be able to run the loops, and each loop MUST also be
  usable directly.
- **FR-041** [I — the frontend loop requires the backend Swagger, FR-011]: When the orchestrator
  runs both loops, it MUST give the Swagger output of `backend-dev` to `frontend-dev` as input.
- **FR-042** [I — from constitution Principle V]: The orchestrator MUST NOT start a loop whose
  required input depends on a loop that stopped on failure. It MUST record which loop stopped and
  why.
- **FR-043** [E, design freedom]: The task description allows sequential orchestration (all backend,
  then all frontend) or a prioritized plan with a dependency graph and possible parallel work. This
  spec requires only that the chosen order respect FR-041 and FR-042. The order chosen is
  sequential: `backend-dev` completes, then `frontend-dev` runs (D-9).

#### Claude Code interaction

- **FR-044** [E]: The loops MUST run within Claude Code, and Claude Code MUST do the planning,
  implementation, and validation.
- **FR-045** [E]: The loops MAY use existing skills, MCP servers, or Spec Kit workflows, or custom
  ones. The Playwright MCP server is required for frontend validation (FR-022).
- **FR-046** [I — from FR-001 and FR-044]: Each loop's `Loop-instructions.md` MUST be the
  authoritative instructions Claude Code follows for that loop.

#### Run workspaces

- **FR-049** [D-3]: Each target application or run MUST have its own workspace folder containing
  its own `outputs/`, `state/`, and `progress.md` for each loop that runs against it.
- **FR-050** [D-3, plus constitution Principle II]: Starting a loop for a new application MUST
  NOT require editing, resetting, or archiving any reusable loop file. The developer only selects or
  creates a workspace.
- **FR-051** [I — from D-3 plus constitution Principle IV]: A loop MUST resume only from a
  workspace whose recorded inputs match the current run. A workspace belonging to another
  application MUST NOT be resumed or overwritten; the loop stops with an input error instead.
- **FR-051a** [D-8; precision per R, CHK009 and CHK031]: At planning, each loop MUST record the
  content identity of its inputs: the requirements file and, for `frontend-dev`, the Swagger
  document. At approval it MUST also record the approved answers. Identity is byte-level: any byte
  change counts as a change. On every later start in the same workspace, it MUST compare the current
  inputs with that record. Answers are compared only once an approval or grant has recorded them.
  Editing answers while the plan awaits approval is expected and MUST NOT count as a change. If they differ, it MUST stop
  without changing code or state and report which input changed. Starting a new run is the
  developer's decision.
- **FR-052** [I — from D-3 plus FR-041]: Under the orchestrator, both loops for the same
  application MUST use the same workspace, so the backend Swagger output is found by the frontend
  loop.

#### Documentation

- **FR-047** [E]: A README for the loops MUST document them, including Mermaid sequence diagrams of
  each loop and of orchestrated use.
- **FR-048** [C, Principle IX]: Documentation MUST describe how to run each loop directly and
  through the orchestrator, the inputs each accepts, the artifacts each produces, configuration
  (including the trial limit), and recovery behavior. It MUST match the implemented behavior.

### Key Entities

- **Loop**: A reusable, independently runnable development process (`backend-dev`, `frontend-dev`)
  with its own instructions, task description, progress record, state, and outputs.
- **Requirements input**: A full PRD or a single user story supplied at run time. The loop plans
  from it.
- **Backend contract (Swagger document)**: Produced by `backend-dev`. Consumed by `frontend-dev`.
- **Milestone**: A planned unit of work containing tasks. It is recorded as one file in
  `outputs/`, is validated as a whole, and is the unit that time and tokens are measured against.
- **Task**: The smallest planned unit of work in a milestone. Its status is *pending*, *achieved*, or
  *failed/blocked*.
- **Trial**: One attempt to complete and validate a unit of work. The count is capped by the trial
  limit.
- **Validation evidence**: The recorded curl requests and responses, or the Playwright
  observations, that justify a pass or a fail.
- **Loop state**: The persistent record used to pick the next unit of work, count trials, and
  resume.
- **Progress record (`progress.md`)**: A human-readable log of action items, with start/end times,
  token consumption, and session references per milestone.
- **Run workspace**: The per-application (or per-run) folder that holds each loop's `outputs/`,
  `state/`, and `progress.md`, kept separate from the reusable loop files.
- **Orchestrator**: An optional driver that runs loops in a dependency-respecting order and passes
  outputs between them.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Each loop can be started on a requirements document with one command or one
  instruction to Claude Code, where the developer supplies only the inputs (and configuration if
  they want to override defaults).
- **SC-002**: 100% of tasks marked achieved have validation evidence recorded for their milestone.
- **SC-003**: After an interruption at any point, a restarted loop re-executes 0 already-achieved
  tasks.
- **SC-004**: No unit of work is attempted more times than the configured trial limit (3 by
  default) plus any trials explicitly granted and recorded under FR-063, in 100% of runs.
- **SC-005**: 100% of milestones in `progress.md` have a start time, an end time, and a token
  consumption entry, where the entry is either a value or an explicit "unavailable".
- **SC-006**: The same loop infrastructure, with 0 modified lines, runs successfully on at least two
  requirements documents from unrelated application domains, each in its own workspace. For this
  feature, the two documents are the smoke-test fixtures. Running on the reference application as
  well is measured in the consumer phase, like SC-007. "Unrelated" means the two documents share no entities or
  endpoints and need different milestone plans [R, CHK019].
- **SC-007** *(consumer-milestone criterion; not a deliverable of this feature; R, CHK018)*: The
  reference application built by the loops passes every recorded curl check and Playwright check for
  all planned milestones. This is measured when the loops are applied to the reference application.
- **SC-008** [R, CHK020]: Following only the README's commands, each loop and the orchestrator
  reach *completed* on the smoke-test requirement, with no steps beyond those documented.
- **SC-009**: In 100% of runs, 0 files in the repository or in other project directories are
  created, modified, or deleted outside the run's target directories and run workspace (D-7;
  scoped per R, CHK033).
- **SC-010**: In 100% of runs that start after an input changed in the same workspace, the loop
  stops before making any change and names the changed input (D-8).
- **SC-011** [R, CHK024]: Both loops reach *completed* on a minimal smoke-test requirement, and the
  orchestrator also completes it, with every milestone showing passing validation evidence. This is
  the end-to-end criterion for this feature, independent of the reference application.

## Assumptions

- **A-1**: The developer has Claude Code installed with the Playwright MCP server available, and
  has curl installed. Setting these up is prerequisite environment work, not loop behavior.
- **A-2**: "Phase" (backend loop), "feature/phase" (frontend loop), "spec", and "milestone"
  (loop structure) refer to the same unit of planned work. The trial limit, timing, and token
  measurements apply to that unit. "Milestone" is the canonical term in this spec (called "phase"
  in the task description) [R, CHK016].
- **A-3**: *(Promoted to requirement FR-034 per R, CHK017.)*
- **A-4**: The run workspaces (milestone files, `progress.md`, `state/`) are committed to the
  repository, as the full-task deliverable ("loops structures and outputs of each loop") suggests.
  The reference application's workspace is one such workspace.
- **A-5**: The human-written design document, the prompts/session-ID spreadsheet, and the
  reference application's code are full-task deliverables outside this spec. The loops only capture
  the data they need (FR-033).
- **A-6** [R, CHK038]: Loops do not create version-control commits unless configured to.
  Committing is the developer's responsibility.

### Out of Scope

- The reference application (`quickflow/PRD.md`): its planning, stack, code, and tests.
- Choosing a specific backend or frontend technology stack in the loop infrastructure.
- Producing the prompts/session-ID spreadsheet and the human-written design document.
- Deployment of applications built by the loops.
- Performance or duration targets for loop runs, beyond the configurable limits (FR-006, FR-062)
  [R, CHK036].

## Open Questions and Ambiguities

Resolved items are kept here as decisions (**D-n**, see Clarifications and the review decisions
below). No open questions remain.

- **D-1 (was Q-1) Trial scope**: Trials count per milestone; running out stops the whole loop
  run. Applied in FR-005 and User Story 3.
- **D-2 (was Q-2) "UI artifact URL"**: The URL where `frontend-dev` serves the built frontend; it is
  an output that Playwright tests. Applied in FR-022.
- **D-3 (was Q-3) Artifact location**: One workspace per target application or run. Applied in
  FR-001, FR-049 to FR-052, and A-4.
- **D-4 Unresolvable requirements**: Open questions pause the loop after planning; after approval,
  new issues become flagged assumptions. Applied in FR-025, FR-028, FR-053 to FR-056, and the Edge
  Cases.
- **D-5 (was Q-4) Stack selection**: Priority is existing code, then a named stack, then a stack
  proposed and approved at the planning pause. Applied in FR-015, FR-021, and FR-057 to FR-060.
- **D-6 Single-story input form**: A standalone story file, or a PRD file plus a story
  identifier. Applied in FR-010, FR-010a, FR-010b, and User Story 4.
- **D-7 Code location and write boundary**: A target project directory given at run time; writes
  only there and in the run workspace. Applied in FR-035 to FR-035d.
- **D-8 (was Q-5) Changed requirements between runs**: Detect the change, stop, and report it; the
  developer decides whether to start a new run. Applied in FR-051a and the Edge Cases.
- **D-9 (was Q-6) Orchestration order**: Sequential: `backend-dev` completes, then `frontend-dev`
  runs (plan R-15; adopted per R, CHK014). Applied in FR-043.
- **D-10 (was Q-7) `task.md` content**: The loop keeps a standing-assignment template, and each
  workspace gets a copy filled in for that run (plan R-14; adopted per R, CHK014). Applied in
  FR-001.
- **D-11 (was Q-8) Token measurement**: Taken from the usage report of each Claude Code call and
  summed per milestone, with "unavailable" when missing (plan R-13; adopted per R, CHK014). Applied
  in FR-004a.
- **D-12 Suggested answers** (decided 2026-10-06): Claude suggests an answer to each open question;
  an empty answer accepts it, and `questions: accept-suggested` accepts suggestions without the
  developer for unattended runs. Applied in FR-053a and FR-055c.
- **Review decisions**: Items marked **[R]** adopt the recommended fixes from
  `checklists/loops-review.md` (2026-09-27). They also settle plan decisions U-1 (FR-016), U-2
  (FR-030a), U-3 (FR-039), U-4 (FR-071), U-5 (FR-063), and U-6 (A-6).
