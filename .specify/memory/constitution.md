<!--
Sync Impact Report
==================
Version change: 1.0.1 → 2.0.0
Bump rationale: MAJOR. Principle VI's MUST "orchestration MUST be optional, not a prerequisite for
  running either loop" is redefined: devloops has one run command, a project chooses which loops
  run, and each loop MUST be runnable without the other once its own inputs exist.
Motivation: a frontend-dev run started on its own skipped the backend handoff and spent its trials
  with no backend to test against. One run command (specs/003-single-run-command) makes the
  handoff impossible to skip.
Affected sections: Principle VI (second bullet).
Migration impact: specs/001-reusable-dev-loops FR-039 and FR-040 (each loop runnable directly
  through the CLI) and the commands in specs/002-devloops-init are revised in place by spec 003.
  `devloops orchestrate` and `devloops run <loop>` are removed; `devloops run` runs the loops the
  project configures.
Temporary deviation: until feature 004 (frontend-only runs), frontend-dev can be started from the
  CLI only after backend-dev in the same run. The engine still runs frontend-dev on its own once
  given an API contract, and tests keep covering that (spec 003 research R-11, plan Complexity
  Tracking).

Previous entry (1.0.1):
Version change: 1.0.0 → 1.0.1
Bump rationale: PATCH. Project renamed from "Claude Loops" (claude-loops) to "Devloops" (devloops);
  title wording only, no principle or governance change.
Motivation: a project name without the "Claude" trademark.
Affected sections: document title only.
Migration impact: specs/001-reusable-dev-loops and loop infrastructure renamed in the same change
  (CLI bin/devloops, package devloops, env DEVLOOPS_*, schema $id prefix devloops/).
  specs/claude-loops/task-description.md is the original brief and keeps its wording and path.

Previous entry (1.0.0):
Version change: (unratified template) → 1.0.0
Bump rationale: Initial ratification; all placeholders replaced with concrete governance content.

Modified principles (template placeholder → new title):
  - [PRINCIPLE_1_NAME] → I. Requirements-Driven Development
  - [PRINCIPLE_2_NAME] → II. Reusability
  - [PRINCIPLE_3_NAME] → III. Incremental and Verifiable Development
  - [PRINCIPLE_4_NAME] → IV. Controlled and Recoverable Automation
  - [PRINCIPLE_5_NAME] → V. Bounded Execution
Added principles (beyond template's five slots):
  - VI. Separation of Concerns
  - VII. Existing Infrastructure First
  - VIII. Testability and Traceability
  - IX. Documentation
  - X. Simplicity
Added sections:
  - Constitutional Boundary (template SECTION_2)
  - Reference Application and Loop Validation (template SECTION_3)
  - Governance (filled from GOVERNANCE_RULES)
Removed sections: none

Deferred TODOs: none
-->

# Devloops Constitution

## Core Principles

### I. Requirements-Driven Development

- Implementation MUST be driven by explicit requirements, PRDs, or user stories.
- Requirements, assumptions, implementation decisions, and recommendations MUST remain
  distinguishable in every artifact that records them.
- Ambiguity MUST be identified and surfaced rather than silently converted into assumptions.

**Rationale**: Automated development amplifies whatever it is given. Unstated assumptions
become shipped behavior; keeping them visible lets humans correct them before they propagate.

### II. Reusability

- Development loops MUST be application-agnostic and reusable across projects.
- Application-specific behavior MUST be introduced through project requirements, not embedded
  in shared loop infrastructure.

**Rationale**: The value of this repository is loops that work for any application. Every
application-specific shortcut in shared infrastructure reduces that value.

### III. Incremental and Verifiable Development

- Work SHOULD be decomposed into independently implementable and verifiable tasks.
- A task MUST NOT be considered complete until its required validation succeeds.
- Validation MUST verify observable behavior; successful compilation or process startup alone
  MUST NOT count as validation.

**Rationale**: Small, verified increments localize failures and make progress trustworthy.
A build that compiles but does not behave correctly is not done.

### IV. Controlled and Recoverable Automation

- Automated development MUST make controlled, scoped changes and preserve existing project
  conventions.
- Automation MUST NOT perform unrelated refactoring or repeat work already completed.
- Long-running loops MUST maintain sufficient persistent state to support progress tracking,
  failure handling, bounded retries, interruption, and safe recovery.

**Rationale**: Unattended loops will be interrupted and will fail. Persistent state makes
resumption safe; scoped changes keep diffs reviewable and prevent regressions.

### V. Bounded Execution

- Automation MUST have explicit completion and stopping conditions.
- Retries MUST be bounded and configurable.
- When execution cannot complete within its limits, the system MUST preserve relevant state
  and clearly record the failure.

**Rationale**: Unbounded loops waste resources and hide failure. An explicit stop with a
recorded reason is a useful outcome; an endless retry is not.

### VI. Separation of Concerns

- Requirements, planning, implementation, validation, state management, and orchestration
  SHOULD remain clearly separated.
- Backend and frontend loops MUST remain separate loops, each runnable without the other once its
  own inputs exist. devloops MAY offer one command that runs the loops a project chooses, in
  order; running one loop MUST NOT require running another, except to produce inputs the first
  one needs.
- Shared functionality SHOULD be implemented once and reused rather than duplicated.

**Rationale**: Separated concerns can be tested, replaced, and reasoned about in isolation.
Independent loops let teams adopt only what they need.

### VII. Existing Infrastructure First

- Implementations SHOULD inspect and reuse existing repository conventions, tooling,
  configuration, scripts, and infrastructure before introducing new ones.
- New dependencies, abstractions, or infrastructure MUST have a clear, documented purpose.

**Rationale**: Reusing what exists keeps projects coherent and lowers maintenance cost.
Parallel mechanisms for the same job create drift and confusion.

### VIII. Testability and Traceability

- Loop infrastructure MUST be testable independently of the applications it develops.
- Important execution and development outcomes SHOULD be traceable through appropriate
  artifacts such as requirements, tasks, state, progress, validation results, and development
  records.

**Rationale**: Loops that can only be tested through a specific application are coupled to it.
Traceability lets reviewers see why a change was made and whether it was verified.

### IX. Documentation

- Important architecture, workflows, configuration, usage, and operational behavior MUST be
  documented.
- Documentation MUST reflect the implemented system, not an idealized or planned design.

**Rationale**: Reusable infrastructure is only reusable if others can understand and operate
it. Inaccurate documentation is worse than none.

### X. Simplicity

- The simplest architecture that satisfies the requirements SHOULD be preferred.
- Unnecessary abstractions, dependencies, orchestration, and automation SHOULD be avoided.
- Added complexity MUST have an explicit, recorded justification.

**Rationale**: Every layer of automation is another thing that can fail. Complexity is
accepted only when it pays for itself.

## Constitutional Boundary

- This constitution MUST contain stable engineering principles only.
- Application-specific requirements, backend or frontend implementation details, tool-specific
  procedures, retry values, workflow details, and project-specific conventions MUST be defined
  in the appropriate specifications, plans, tasks, or configuration, not in this constitution.
- Where a principle requires a concrete value (for example, a retry limit), the constitution
  states only that the value MUST exist and be configurable; the value itself belongs in
  configuration or plans.

## Reference Application and Loop Validation

- The repository MAY contain a reference application used to demonstrate and validate the
  reusable development loops.
- The reference application is a consumer of the loop infrastructure and MUST NOT cause the
  loops to become application-specific.
- Development loops MUST be designed independently of the reference application and SHOULD
  remain capable of developing other applications with different requirements.
- Reference-application-specific requirements, business rules, UI behavior, API behavior, and
  implementation details MUST be defined in that application's PRD, specification, or other
  project artifacts, not in this constitution or in reusable loop infrastructure.
- The development loops SHOULD be validated end-to-end against the reference application to
  demonstrate that they can consume real project requirements and produce a working
  application.

## Governance

- This constitution supersedes conflicting practices, specifications, plans, and tasks in this
  repository. Where a conflict exists, the constitution prevails until it is amended.
- **Amendments** MUST be made through a documented change to this file that states the
  motivation, the affected principles or sections, and any migration impact on existing
  specifications, plans, or loop infrastructure.
- **Versioning** follows semantic versioning:
  - MAJOR: backward-incompatible removal or redefinition of a principle or governance rule.
  - MINOR: a new principle or section, or materially expanded guidance.
  - PATCH: clarifications, wording, or typo fixes with no semantic change.
- **Compliance review**: Plans MUST include a constitution check before design work begins and
  again after design. Reviews of loop infrastructure and generated work MUST verify compliance
  with these principles. Any deviation MUST be recorded with its justification, per
  Principle X.

**Version**: 2.0.0 | **Ratified**: 2026-09-27 | **Last Amended**: 2026-10-09
