---
title: Exit codes
description: >-
  What each devloops exit code means and what to do next.
generated: true
---

# Exit codes

!!! note "Generated page"
    This page is generated from devloops' code; do not edit it. Change the code (or
    `tools/docs/descriptions.json`), then run `python3 tools/docs/gen_reference.py`.

Every devloops command ends with one of these exit codes, so scripts can tell what happened.

| Code | Name | Meaning | What to do |
|---|---|---|---|
| <span id="exit-0"></span>0 | `completed` | The command did what it was asked. For a run, every loop it includes is completed. | Nothing. A run's results are in each loop's outputs/ folder. |
| <span id="exit-1"></span>1 | `error` | Something went wrong that no other code covers, for example an export that could not be written. | Read the message devloops printed; it names what failed. |
| <span id="exit-2"></span>2 | `usage error` | The command was not usable as given: an unknown option, a missing value, no project found, or an invalid run configuration. Nothing was changed. | Fix the command or the configuration file the message names, then run it again. |
| <span id="exit-10"></span>10 | `awaiting-approval` | The run paused for you: a plan is waiting for review, or a question has no suggested answer. | Review the plan, then run devloops approve, or devloops replan with your feedback. |
| <span id="exit-20"></span>20 | `stopped-on-failure` | The run stopped: a milestone used all its trials, the plan could not be made, a question needs your answer, or the run reached its limit of calls to Claude Code. | Run devloops status to see why. Then devloops retry to grant more trials, or change the requirements and start again. |
| <span id="exit-30"></span>30 | `stopped-on-input-error` | Something the run needs is missing or wrong: the requirements, a story, a tool, the target folder, the project configuration, or an input that changed since the run started. devloops check and devloops init also exit 30 when they find a problem. | Fix what the message names, then run the same command again. |
| <span id="exit-40"></span>40 | `lock held` | Another devloops command is working in this workspace, or one that ended abruptly left its lock behind. | Wait for the other command to finish. If none is running, run devloops status, which says how to clear the lock. |
| <span id="exit-50"></span>50 | `stopped-on-service-error` | Claude Code could not be used: the service was unavailable, a rate limit was reached, or authentication failed. No trial was used up. | Wait, or log in to Claude Code again, then run devloops run to resume. |
| <span id="exit-130"></span>130 | `interrupted` | You pressed Ctrl+C. What was already recorded is kept. | Run devloops run to resume; devloops status shows where the run stands. |
