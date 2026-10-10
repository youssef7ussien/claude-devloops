---
title: State files
description: >-
  Every file a run writes in its workspace, and the fields of the main ones.
generated: true
---

# State files

!!! note "Generated page"
    This page is generated from devloops' code; do not edit it. Change the code (or
    `tools/docs/descriptions.json`), then run `python3 tools/docs/gen_reference.py`.

Everything devloops knows about a run is in files in the workspace, so a run can be read, shared, and resumed. These are the files a run writes, relative to the workspace folder. In the names, `<loop>` is `backend-dev` or `frontend-dev`, `<id>` a milestone (`M01`), `<n>` a trial number, `<seq>` a call's number, `<step>` a [step](steps.md), and `<check>` a check's id.

| File | What it records |
|---|---|
| <span id="loop-outputs-final-report.md"></span>`<loop>/outputs/final-report.md` | The loop's final report, written when every milestone is achieved, or when the loop stops for good after planning: what was built and what each milestone's validation showed. |
| <span id="loop-outputs-milestone-nn-slug.md"></span>`<loop>/outputs/milestone-<NN>-<slug>.md` | One milestone of the plan, readable: its goal, tasks and acceptance criteria. |
| <span id="loop-outputs-open-questions.md"></span>`<loop>/outputs/open-questions.md` | The plan's open questions, with Claude's suggested answers. You write your answers here before approving. |
| <span id="loop-outputs-openapi.json"></span>`<loop>/outputs/openapi.json` | The backend's OpenAPI document, published after each achieved milestone with only the operations validation called. |
| <span id="loop-outputs-plan-summary.md"></span>`<loop>/outputs/plan-summary.md` | The plan in one page, for review before approval. |
| <span id="loop-progress.md"></span>`<loop>/progress.md` | Where the loop stands: each milestone, its status and its trials. Rewritten as the run goes. |
| <span id="loop-state-conversations-seq-step.jsonl"></span>`<loop>/state/conversations/<seq>-<step>.jsonl` | A copy of one call's Claude Code conversation (its transcript), kept so it can be read later. |
| <span id="loop-state-events.jsonl"></span>`<loop>/state/events.jsonl` | One line per thing that happened in the loop, in order: run started, plan stored, trial started, validation passed or failed, and so on. |
| <span id="loop-state-invocations.jsonl"></span>`<loop>/state/invocations.jsonl` | One line per call to Claude Code: its step, milestone and trial, when it ran, its tokens and cost, and how it ended. See [its fields](#loop-state-invocations.jsonl-fields). |
| <span id="loop-state-milestones-id-checks.json"></span>`<loop>/state/milestones/<id>/checks.json` | A backend milestone's checks: the HTTP requests and expected answers written before any code, kept unchanged for every trial. See [its fields](#loop-state-milestones-id-checks.json-fields). |
| <span id="loop-state-milestones-id-trials-n-evidence-check.body"></span>`<loop>/state/milestones/<id>/trials/<n>/evidence/<check>.body` | The body of the answer a check's HTTP request got. |
| <span id="loop-state-milestones-id-trials-n-evidence-check.command"></span>`<loop>/state/milestones/<id>/trials/<n>/evidence/<check>.command` | The exact curl command a check ran. |
| <span id="loop-state-milestones-id-trials-n-evidence-check.headers"></span>`<loop>/state/milestones/<id>/trials/<n>/evidence/<check>.headers` | The headers of the answer a check's HTTP request got. |
| <span id="loop-state-milestones-id-trials-n-evidence-check.request-body.json"></span>`<loop>/state/milestones/<id>/trials/<n>/evidence/<check>.request-body.json` | The body a check sent with its HTTP request. |
| <span id="loop-state-milestones-id-trials-n-runtime.log"></span>`<loop>/state/milestones/<id>/trials/<n>/runtime.log` | What the application printed while it ran for this trial's validation. |
| <span id="loop-state-milestones-id-trials-n-trial.json"></span>`<loop>/state/milestones/<id>/trials/<n>/trial.json` | One trial: its kind (implement or fix), its status, the calls it made, the assumptions and questions Claude reported, and why it failed, if it did. |
| <span id="loop-state-milestones-id-trials-n-validation.json"></span>`<loop>/state/milestones/<id>/trials/<n>/validation.json` | What validation found for one trial: each check and acceptance criterion, passed or failed, with its evidence. See [its fields](#loop-state-milestones-id-trials-n-validation.json-fields). |
| <span id="loop-state-plan.json"></span>`<loop>/state/plan.json` | The plan: the milestones in order, their tasks and acceptance criteria, and how to start the application. See [its fields](#loop-state-plan.json-fields). |
| <span id="loop-state-prompts-seq-step.md"></span>`<loop>/state/prompts/<seq>-<step>.md` | The exact prompt one call sent to Claude Code, with secrets replaced by ***. |
| <span id="loop-state-prompts-seq-step.settings.json"></span>`<loop>/state/prompts/<seq>-<step>.settings.json` | The Claude Code settings one call ran with: the hooks that keep writes inside the target and stop Claude from ending processes by name. |
| <span id="loop-state-run.json"></span>`<loop>/state/run.json` | The loop's run: its status and why it stopped, its inputs, the settings it started with, the approval, and each milestone's progress. See [its fields](#loop-state-run.json-fields). |
| <span id="loop-state-run.log"></span>`<loop>/state/run.log` | Every progress line the loop printed, whatever --quiet or --verbose said. |
| <span id="loop-task.md"></span>`<loop>/task.md` | The run's inputs in one page: the requirements, the target folder and the settings in effect. |
| <span id="exports-stamp.html"></span>`exports/<stamp>.html` | A dashboard export: the whole dashboard in one file, written by devloops dashboard --export. |
| <span id="run-progress.md"></span>`run/progress.md` | Where the whole run stands: each loop and its status. |
| <span id="run-state.json"></span>`run/state.json` | The run across its loops: its status, each loop's step, and the handoff from the backend loop to the frontend loop. |
| <span id="workspace.json"></span>`workspace.json` | The workspace's identity: its name, the requirements it was started with, the target folder of each loop, and its configuration file. |

## `<loop>/state/invocations.jsonl` {#loop-state-invocations.jsonl-fields}

| Field | Type | Meaning |
|---|---|---|
| `seq` | integer, at least 1 |  |
| `session_id` | string |  |
| `loop` | one of `"backend-dev"`, `"frontend-dev"` |  |
| `step` | one of `"plan"`, `"replan"`, `"implement"`, `"fix"`, `"author-checks"`, `"validate-ui"` |  |
| `model` | string or null | The --model this call was started with (from `models` or `model`); null when none was passed and Claude Code used its default. |
| `milestone_id` | string or null |  |
| `trial` | integer or null |  |
| `prompt_path` | string |  |
| `started_at` | string |  |
| `ended_at` | string |  |
| `duration_ms` | integer or null |  |
| `num_turns` | integer or null |  |
| `tokens` | object | null values = unavailable (Edge Case). |
| `cost_usd` | number or null |  |
| `is_error` | boolean |  |
| `subtype` | string or null |  |
| `permission_denials` | array |  |
| `timed_out` | boolean |  |
| `api_error_status` | integer or null |  |
| `failure_class` | one of `"none"`, `"work"`, `"service"` | Research R-19; service failures void the trial (FR-067). |
| `redacted` | boolean | true if any secret values were replaced (FR-070). |
| `conversation` | one of `"copied"`, `"unavailable"` | 002 FR-042: whether the call's Claude Code transcript was copied into the workspace. |
| `conversation_path` | string | The copy, relative to the loop directory: state/conversations/<seq>-<step>.jsonl. |
| `conversation_reason` | one of `"not-found"`, `"interrupted"`, `"unreadable"` | Why the conversation is unavailable. |
| `prompt_sources` | list of objects | 002 FR-031: the source of each prompt part of this call (research P-8). |

## `<loop>/state/milestones/<id>/checks.json` {#loop-state-milestones-id-checks.json-fields}

| Field | Type | Meaning |
|---|---|---|
| `milestone_id` | string |  |
| `checks` | list of objects |  |

## `<loop>/state/milestones/<id>/trials/<n>/validation.json` {#loop-state-milestones-id-trials-n-validation.json-fields}

| Field | Type | Meaning |
|---|---|---|
| `kind` | one of `"curl"`, `"playwright"` |  |
| `passed` | boolean | Computed by driver only; a criterion with no entry counts as failed (FR-068). |
| `ui_url` | string | Playwright only (D-2). |
| `criteria` | list of objects |  |
| `checks` | list of objects |  |
| `network_requests` | list of objects |  |
| `contract` | object |  |
| `unit_tests` | object |  |
| `boundary` | object |  |

## `<loop>/state/plan.json` {#loop-state-plan.json-fields}

| Field | Type | Meaning |
|---|---|---|
| `requirements_inventory` | list of objects |  |
| `stack` | object |  |
| `runtime` | object |  |
| `milestones` | list of objects |  |
| `open_questions` | list of objects |  |
| `assumptions` | list of objects |  |
| `speckit_omitted` | list of objects | 002 FR-023b: in-scope spec-kit tasks this plan leaves out, each with a reason. |

## `<loop>/state/run.json` {#loop-state-run.json-fields}

| Field | Type | Meaning |
|---|---|---|
| `loop` | one of `"backend-dev"`, `"frontend-dev"` |  |
| `status` | one of `"planning"`, `"awaiting-approval"`, `"implementing"`, `"completed"`, `"stopped-on-failure"`, `"stopped-on-input-error"`, `"stopped-on-service-error"` |  |
| `status_reason` | object or null | Why the run stopped, set with a stopped-* status; or `interrupted` on a planning or implementing run that Ctrl+C interrupted and that can still be resumed (cleared when it resumes). |
| `inputs` | object |  |
| `target_dir` | string |  |
| `effective_config` | object (the run configuration keys) |  |
| `approval` | object or null |  |
| `answers_sha256` | string or null | T055: the answers fingerprint later starts compare against; set by the approval, each retry, and each automatic answer. |
| `milestones` | object | Id -> {status: pending\|in-progress\|achieved\|failed, tasks: {id: pending\|implemented\|achieved\|failed}, trials: [{n, status: in-progress\|passed\|failed\|void, reason?}], started_at, ended_at}. |
| `invocation_count` | integer, at least 0 |  |
| `ui_url` | string or null |  |
| `openapi_artifact` | object or null |  |
| `resume_status` | one of `"planning"`, `"implementing"`, `null` | For stopped-on-service-error: state restored on the next run (FR-067). |
| `project_root` | string | 002: the project root at the first start; a resume from another root relocates the recorded paths under it (FR-013). |
| `config_sources` | object | 002 research P-5: sha256 (or null) of each configuration file when the configuration was frozen. |
| `config_cli_keys` | list of strings | 002 research P-5: the dotted keys the command line set; not reported as drift. |
| `grants` | list of objects | FR-063 trial-budget grants. |
| `prompt_sources` | list of objects | 002 FR-032: the source of every prompt part the loop can use when the configuration was frozen; status compares them with the current files (prompt_drift). |
| `auto_answers` | list of objects | needs-input questions answered with Claude's suggestions under questions: accept-suggested. |
