---
title: Glossary
description: >-
  The words devloops uses, each explained in plain language, with a link to where it is
  explained in depth.
sources:
  - loops/shared/devloops/engine.py
  - loops/shared/devloops/orchestrator.py
  - loops/shared/devloops/claude.py
  - loops/shared/devloops/validators
  - loops/shared/tests/fake_claude.py
  - spec 001 FR-005
  - spec 003 FR-005
  - spec 005 FR-001
  - spec 006 FR-015
---

# Glossary

The words devloops uses, in alphabetical order. On every page of this site, hovering over one of
these words shows its short definition.

## acceptance criterion {#acceptance-criterion}

A statement that must be true for a milestone to pass, such as "GET /items returns 200 and a
list". The plan gives each milestone its acceptance criteria, and validation checks every one.
See [validation](how-it-works/validation.md).

## approval {#approval}

Accepting a plan, so that building can start. You approve with `devloops approve`, or devloops
approves by itself and accepts Claude's suggested answers (the default). See
[approval and questions](guides/approval-and-questions.md).

## assumption {#assumption}

A decision Claude Code made where the requirements say nothing, such as "items are kept in
memory". Assumptions are recorded with the plan and with each trial, so you can review them. See
[approval and questions](guides/approval-and-questions.md).

## backend-dev {#backend-dev}

The loop that builds an HTTP API (the backend). Its milestones are validated by sending real HTTP
requests to the running application, and it publishes an OpenAPI document that describes the API.
See [the backend loop](guides/backend-loop.md).

## call {#call}

One run of Claude Code for one step. devloops records each call: the prompt it sent, the
conversation, the tokens used and the cost. See [steps](how-it-works/steps.md).

## check {#check}

For the backend loop: an HTTP request and the answer it must get. A milestone's checks are written
before any of its code, and stay the same for every trial, so the code cannot be made to fit the
test afterwards. See [validation](how-it-works/validation.md).

## contract {#contract}

The OpenAPI document the backend loop publishes: the list of operations the API offers. The
backend publishes only operations its validation actually called, and the frontend may call only
operations in it. See [the frontend loop](guides/frontend-loop.md).

## dashboard {#dashboard}

A web page, served on your own machine by `devloops dashboard`, that shows a workspace: the
progress of each loop, every call to Claude Code, the files, the questions and the events. See
[the dashboard](guides/dashboard.md).

## evidence {#evidence}

What validation keeps to show what it saw: the answers to HTTP requests, screenshots, and the
browser's list of network requests. See [validation](how-it-works/validation.md).

## export {#export}

The dashboard written as one HTML file, with all its data inside, to share or keep. It opens
without devloops. See [the dashboard](guides/dashboard.md).

## frontend-dev {#frontend-dev}

The loop that builds the user interface (the frontend). Its milestones are validated in a real
browser, and every request a page makes to the backend is checked against the backend's contract.
See [the frontend loop](guides/frontend-loop.md).

## handoff {#handoff}

What the backend loop passes to the frontend loop when it completes: its OpenAPI document and how
to start the backend. The frontend loop starts only after it. See
[the run lifecycle](how-it-works/run-lifecycle.md).

## headless Claude Code {#headless-claude-code}

Claude Code run as a command (`claude -p`) instead of in its interactive screen: devloops gives
it a prompt, lets it work, and reads its answer. Every call devloops makes is headless. See
[steps](how-it-works/steps.md).

## loop {#loop}

One of devloops' two ways of building: backend-dev and frontend-dev. Each makes a plan, then
builds and validates its milestones one at a time. A run includes the loops the project uses. See
[how it works](how-it-works/index.md).

## milestone {#milestone}

A part of the application that can be built and validated on its own, such as "List items". The
plan splits the work into milestones, which are built one at a time, in order. A milestone passes
only when devloops' own validation passes. See [the run lifecycle](how-it-works/run-lifecycle.md).

## open question {#open-question}

Something the requirements leave unclear, which Claude Code asks about while planning or
building. Each comes with a suggested answer when Claude has one; you can answer in
`outputs/open-questions.md`. See [approval and questions](guides/approval-and-questions.md).

## plan {#plan}

What devloops builds from the requirements before writing any code: the milestones in order,
their tasks and acceptance criteria, and how to start the application. It is approved before
building starts. See [the run lifecycle](how-it-works/run-lifecycle.md).

## project {#project}

A folder set up for devloops with `devloops init`. It holds the configuration file
`.devloops/devloops.json`, and usually the application's code. See
[your first run](getting-started/first-run.md).

## requirements {#requirements}

The written description of what to build: a Markdown file (a product description, or one story)
or a spec-kit feature. Everything devloops builds traces back to them. See
[the run lifecycle](how-it-works/run-lifecycle.md).

## retry grant {#retry-grant}

More trials for a milestone that used all of its own, given with `devloops retry`, optionally with
guidance for the next attempt. See [trials and recovery](how-it-works/trials-and-recovery.md).

## runtime {#runtime}

How to start and reach the application while it is validated: the command that starts it, the
folder it runs in, and the address it answers on. The plan chooses it, and the configuration can
change it. See [validation](how-it-works/validation.md).

## stand-in {#stand-in}

A program that answers in place of Claude Code with fixed answers. devloops' tests and the
examples on this site use it, so their runs are the same every time and cost nothing. See
[testing](contributing/testing.md).

## step {#step}

One kind of call to Claude Code, with its own instructions and tools: plan, replan,
author-checks, implement, fix and validate-ui. See [steps](how-it-works/steps.md).

## story {#story}

One user story: a small piece of the requirements written from a user's point of view. A run can
build one story, either a file that holds just that story or one story picked from a larger
file. See [the run lifecycle](how-it-works/run-lifecycle.md).

## suggested answer {#suggested-answer}

Claude Code's proposed answer to an open question. By default devloops accepts it without
stopping and marks it for your review. See
[approval and questions](guides/approval-and-questions.md).

## target {#target}

The folder a loop writes the application's code to. Claude Code may change files only inside
it; a write anywhere else fails the trial. See [security](guides/security.md).

## task {#task}

One piece of work inside a milestone, such as "GET /items". Claude Code reports each task done;
it counts as achieved only when its milestone passes validation. See
[the run lifecycle](how-it-works/run-lifecycle.md).

## trial {#trial}

One attempt at a milestone: Claude Code writes the code (or fixes it, after a failed trial), then
devloops validates the result. A milestone gets a limited number of trials. See
[trials and recovery](how-it-works/trials-and-recovery.md).

## validation {#validation}

devloops' own test of a trial's result, never Claude's word: real HTTP requests to the running
backend, or a real browser for the frontend. A milestone passes only when validation passes. See
[validation](how-it-works/validation.md).

## workspace {#workspace}

The folder that holds everything about one run: its state, the record of every call, the
evidence and the outputs. A run can be read, shared, and resumed from it. See
[state and files](how-it-works/state-and-files.md).
