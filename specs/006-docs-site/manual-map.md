# Manual map: where the old manual went (SC-008)

Every heading of `loops/README.md` and `loops/orchestrator/README.md`, with the site page and
section that now covers it, or "dropped" with the reason. Anchors are the headings' real ids on
the built site. Facts a section holds that no page states yet are listed under [Gaps](#gaps).

## `loops/README.md`

| Manual heading (file:line) | Now covered by |
|---|---|
| Reusable development loops (`loops/README.md:1`) | `docs/index.md` (the whole page: what devloops is, the core idea, the two loops); `README.md` |
| Install (`:28`) | `docs/getting-started/install.md#what-you-need`, `#install-devloops`, `#check-the-install` |
| Quick start (`:59`) | `docs/getting-started/first-run.md` (steps 1–7); the phase table: `docs/how-it-works/index.md#the-big-picture`; the review prompt: `docs/guides/approval-and-questions.md#in-a-terminal`; the stop table: `docs/getting-started/first-run.md#when-a-run-stops` |
| `devloops init` (`:120`) | `docs/getting-started/first-run.md#2-set-up-the-project`; flags: `docs/reference/commands.md#init`; `--allow-skills`: `docs/guides/skills.md#permissions`; `--upgrade`: `docs/guides/upgrades.md` |
| `devloops check` (`:154`) | `docs/getting-started/install.md#check-the-install`; `docs/getting-started/first-run.md#3-check-the-machine`; browser warnings: `docs/guides/configuration.md#watching-the-browser` |
| The project (`:176`) | `docs/how-it-works/state-and-files.md#project-workspace-and-target`; `docs/guides/configuration.md#where-settings-live`, `#which-setting-wins`; keys: `docs/reference/configuration.md#project-file` |
| Commands (`:238`) | `docs/reference/commands.md` (every command and option); decisions: `docs/guides/approval-and-questions.md#what-the-three-decisions-have-in-common`; version warning: `docs/guides/upgrades.md#2-upgrade-each-project` |
| Progress (`:265`) | `docs/how-it-works/run-lifecycle.md#following-a-run` |
| `approve`, `replan`, and `retry` (`:333`) | `docs/guides/approval-and-questions.md#devloops-approve`, `#devloops-replan`, `#devloops-retry`, `#what-the-three-decisions-have-in-common` |
| `run` options (`:352`) | `docs/reference/commands.md#run`; targets: `docs/how-it-works/run-lifecycle.md#which-loops-a-run-includes`; spec-kit and `--story-id US<n>`: `docs/guides/spec-kit.md#use-a-feature`, `#build-one-user-story`; `--review-plan`/`--accept-suggested`: `docs/guides/approval-and-questions.md#who-answers-the-questions-setting` |
| Which loops a run includes (`:374`) | `docs/how-it-works/run-lifecycle.md#which-loops-a-run-includes` |
| Backend-only projects (`:397`) | `docs/guides/backend-loop.md#backend-only-projects`; `docs/guides/frontend-loop.md#when-the-project-has-no-frontend`; frontend-only not supported: `docs/guides/limitations.md#the-frontend-cannot-run-without-the-backend` |
| Exit codes (`:411`) | `docs/reference/exit-codes.md`; `docs/how-it-works/run-lifecycle.md#when-a-run-does-not-complete`; `docs/getting-started/first-run.md#when-a-run-stops` |
| How a run works (`:423`) | `docs/how-it-works/index.md#the-big-picture`; `docs/how-it-works/run-lifecycle.md#one-loop-step-by-step`; write rules: `docs/how-it-works/steps.md#what-a-step-may-do`, `docs/guides/security.md#where-claude-code-may-write` |
| backend-dev (`:450`) | `docs/how-it-works/run-lifecycle.md#the-backend-loop` (sequence diagram); `docs/guides/backend-loop.md` |
| frontend-dev (`:473`) | `docs/how-it-works/run-lifecycle.md#the-frontend-loop` (sequence diagram); `docs/guides/frontend-loop.md` |
| The whole run (`:501`) | `docs/how-it-works/run-lifecycle.md#the-whole-run` |
| Dashboards (`:522`) | `docs/guides/dashboard.md`; `docs/how-it-works/dashboard-data.md#it-only-reads-the-workspace`. The "Changed by spec 005" note (removed summary page and settings): dropped, the pages describe today's dashboard (FR-013) |
| The live dashboard (`:537`) | `docs/guides/dashboard.md#start-it`, `#around-every-view`, each view's section, `#search`, `#following-a-live-run`; mechanics: `docs/how-it-works/dashboard-data.md#following-a-run`, `#the-now-panel`, `#search`; safety and sharing: `docs/guides/security.md#who-can-reach-the-dashboard` |
| Exports (`:631`) | `docs/guides/dashboard.md#the-export`; `docs/how-it-works/dashboard-data.md#the-export` |
| Approval, replan, and open questions (`:660`) | `docs/guides/approval-and-questions.md#why-claude-asks`, `#who-answers-the-questions-setting` |
| Reviewing a plan (`:687`) | `docs/guides/approval-and-questions.md#reviewing-a-plan` |
| Questions during implementation (`:704`) | `docs/guides/approval-and-questions.md#questions-while-a-milestone-is-built` |
| Reviewing accepted suggestions (`:712`) | `docs/guides/approval-and-questions.md#reviewing-the-suggested-answers-devloops-accepted` |
| Trials and failures (`:720`) | `docs/how-it-works/trials-and-recovery.md#what-a-trial-is`, `#how-many-trials-a-milestone-gets` |
| What a trial sees (`:727`) | `docs/how-it-works/trials-and-recovery.md#what-a-trial-sees` |
| Why a trial fails (`:736`) | `docs/how-it-works/trials-and-recovery.md#why-a-trial-fails`, `#void-trials`; `docs/how-it-works/validation.md#why-a-trial-fails` |
| What passes a backend milestone (`:753`) | `docs/how-it-works/validation.md#what-passes-a-backend-milestone`, `#the-published-openapi-document` |
| What passes a frontend milestone (`:790`) | `docs/how-it-works/validation.md#what-passes-a-frontend-milestone`, `#the-browsers-network-log` |
| Questions raised during a trial (`:816`) | `docs/how-it-works/trials-and-recovery.md#questions-raised-during-a-trial` |
| Processes Claude starts (`:832`) | `docs/how-it-works/trials-and-recovery.md#processes-claude-starts` |
| Example: one milestone, three trials (`:860`) | `docs/how-it-works/trials-and-recovery.md#example-one-milestone-three-trials` (made generic: no application names) |
| When a milestone runs out of trials (`:878`) | `docs/how-it-works/trials-and-recovery.md#when-a-milestone-runs-out-of-trials` |
| Recovery (`:889`) | `docs/how-it-works/trials-and-recovery.md#interruptions-and-resuming`; `docs/how-it-works/statuses.md#stop-reasons`; `docs/how-it-works/state-and-files.md#why-a-run-can-resume` |
| Configuration (`:909`) | `docs/guides/configuration.md#which-setting-wins`, `#settings-are-fixed-when-a-loop-starts`, `#the-settings-you-are-most-likely-to-change`; every key: `docs/reference/configuration.md` |
| Visible browser (`:936`) | `docs/guides/configuration.md#watching-the-browser`; `docs/guides/frontend-loop.md#watching-the-browser` |
| Models per step (`:949`) | `docs/guides/configuration.md#models-per-step` |
| Prompt overrides (`:994`) | `docs/guides/prompts.md` |
| Spec-kit features (`:1017`) | `docs/guides/spec-kit.md` |
| Secrets (`:1044`) | `docs/guides/security.md#secrets-in-what-devloops-writes`; `docs/how-it-works/state-and-files.md#secrets-are-removed-before-anything-is-written` |
| Workspace layout (`:1054`) | `docs/how-it-works/state-and-files.md#what-a-workspace-holds` (the tree is the sample run's real file list); every file: `docs/reference/state-files.md`. The "Changed by spec 003" note (`run/` replaced `orchestrator/`): dropped, history (FR-013) |
| Claude Code skills (`:1090`) | `docs/guides/skills.md`. The two "Changed by spec 003 / 005" notes (removed skills): dropped, history (FR-013); that `init --upgrade` removes an unchanged removed file is in `docs/guides/upgrades.md#2-upgrade-each-project` |
| Upgrades (`:1127`) | `docs/guides/upgrades.md` |
| Known limitations (`:1144`) | `docs/guides/limitations.md` |
| Using this checkout (`:1160`) | `docs/contributing/index.md#where-things-are`; running from a checkout: `docs/getting-started/install.md#install-devloops` |
| Repository layout (`:1166`) | `docs/contributing/index.md#where-things-are`; `docs/contributing/architecture.md#the-kit-and-the-project`; the test command: `docs/contributing/testing.md#running-the-tests` |

## `loops/orchestrator/README.md`

| Manual heading (file:line) | Now covered by |
|---|---|
| The run (`loops/orchestrator/README.md:1`) | `docs/how-it-works/run-lifecycle.md#the-whole-run`; where the logic lives: `docs/contributing/architecture.md#from-a-command-to-a-call`. The "Changed by spec 003" note: dropped, history (FR-013) |
| Usage (`:15`) | `docs/how-it-works/run-lifecycle.md#which-loops-a-run-includes`; options: `docs/reference/commands.md#run`; the review mode: `docs/guides/approval-and-questions.md#who-answers-the-questions-setting` |
| Behavior (`:39`) | `docs/how-it-works/run-lifecycle.md#the-whole-run`, `#which-loops-a-run-includes`; the handoff: `docs/guides/backend-loop.md#the-handoff-to-the-frontend`; decisions: `docs/guides/approval-and-questions.md#what-the-three-decisions-have-in-common` |
| Files (`:63`) | `docs/how-it-works/state-and-files.md#what-a-workspace-holds`; fields: `docs/reference/state-files.md#run-state.json` |

## Counts

- Headings: 50 (46 in `loops/README.md`, 4 in `loops/orchestrator/README.md`).
- Mapped to a page: 50. No heading is dropped as a whole.
- Dropped in part: the five "Changed by spec NNN" notes (history; the pages describe devloops as
  it is now, FR-013), and the removed commands `devloops orchestrate` and `devloops run <loop>`
  (`:259`): they are usage errors today, which needs no page.
- Also dropped as reference-level detail, which `--help` and the generated reference hold: the
  exact JSON printed by `--json` for a selection stop (`:388`) and for `dashboard --json`
  (`:621`), and `dashboard_url` in `--json` output (`:276`).

## Gaps

Facts in the manual that no page stated when this map was first written. All 20 were then
checked against the code and filled on 2026-10-10, each in the page named in the last column
(gaps 2, 3, 4, 16 and 17 in `docs/how-it-works/run-lifecycle.md`; 5–7 in `validation.md`; 8–10
in `trials-and-recovery.md`; 1 and 11–13 in `docs/guides/configuration.md`; 14 and 18 in
`dashboard.md`; 15 in `docs/how-it-works/state-and-files.md`; 19 and 20 in
`approval-and-questions.md`). Where the manual and the code differed, the page follows the code.

| # | Manual (file:line) | Fact | Should be in |
|---|---|---|---|
| 1 | `loops/README.md:191` | `DEVLOOPS_PROJECT=<dir>` names the project explicitly, instead of searching upward from the current folder | `docs/guides/configuration.md#where-settings-live` |
| 2 | `:356`, `:364`; `loops/orchestrator/README.md:35` | Story options for a PRD: `--story-id` must match a whole ID with the same case, else `story-not-found`; `--story-file` says the requirements file is one standalone story, and cannot be combined with `--story-id` (only spec-kit's `US<n>` is covered) | `docs/how-it-works/run-lifecycle.md#1-plan`, or a short section in `docs/getting-started/first-run.md` / `docs/guides/spec-kit.md`'s PRD counterpart |
| 3 | `:366`–`:372`; `loops/orchestrator/README.md:24`, `:33` | Targets, inputs, story options and the review mode are recorded on the first run, so later runs and decisions need no flags; a flag given later must match: a different target or story option is refused (exit 2) and changes nothing; `--requirements` given later must be byte-identical to the recorded file | `docs/how-it-works/run-lifecycle.md#which-loops-a-run-includes` |
| 4 | `:358` | Target rules: a target is created if missing, must be writable, outside `.devloops/` and the installed devloops files, and must not overlap the other loop's target; a target flag also includes a loop the project leaves `null` (only "not the project root" is in `limitations.md`) | `docs/how-it-works/run-lifecycle.md#which-loops-a-run-includes` |
| 5 | `:774`–`:788` | Checks chain through captured values: `capture` saves a value from a response, a later check uses it as `${name}` (an exact `"${name}"` keeps its JSON type; inside a longer string it is text); a check whose captured value is missing fails without being sent, so fix the first failing check | `docs/how-it-works/validation.md#the-checks-are-written-first-and-frozen` |
| 6 | `:768`–`:771` | The operations left out of the published OpenAPI document are listed in `run.json`, in `final-report.md`, and in the document itself (`x-devloops-unverified-operations`); the frontend is told they exist but must not be called; a path item that is only a `$ref` is published as it is | `docs/how-it-works/validation.md#the-published-openapi-document` |
| 7 | `:873`–`:875` | If the target's OpenAPI document stops loading right after a milestone passes, the milestone is failed again and the run stops (`retry` publishes it), so an older artifact is never left in place | `docs/how-it-works/validation.md#the-published-openapi-document` |
| 8 | `:742` | Exit code 143 from Claude Code means the call was killed (SIGTERM), most often by a `pkill`/`killall` it ran itself | `docs/how-it-works/trials-and-recovery.md#why-a-trial-fails` |
| 9 | `:845`–`:851` | What the process guard still allows: killing by PID, checking a PID (`kill -0`, `ps -p`), freeing a port (`fuser -k`, `kill $(lsof -t -i:PORT)`), and a mere mention; the block message says what to do instead | `docs/how-it-works/trials-and-recovery.md#processes-claude-starts` |
| 10 | `:904`, `:905` | Exit 40 has two cases: another devloops command holds the lock (wait; one command per loop and workspace), or a stale lock (`--force-unlock`, recorded as a `lock-cleared` event) | `docs/how-it-works/trials-and-recovery.md#interruptions-and-resuming` |
| 11 | `:913`–`:914` | `status` lists the configuration keys that would now differ from the frozen ones; command-line overrides on a later start are recorded as `config-override` events | `docs/guides/configuration.md#settings-are-fixed-when-a-loop-starts` (the `status` half may already be there; the event is not) |
| 12 | `:928` | `git.commit_per_milestone` commits only paths under the target, with the message `feat(<loop>): complete <id> <title>`, and records a `git-commit` event | `docs/guides/configuration.md#the-settings-you-are-most-likely-to-change` |
| 13 | `:927` | `playwright.executable_path` expands `~` | `docs/guides/configuration.md#watching-the-browser` |
| 14 | `:985`–`:987` | In the cost-by-model view, calls made without `--model` count as "(Claude Code default)" and calls recorded before devloops kept the model as "(not recorded)"; the dashboard groups by the model ID each transcript names | `docs/guides/dashboard.md#claude-calls` |
| 15 | `:252`, `:1086`–`:1088` | `devloops export-sessions [--csv FILE]` writes every call as one CSV row: workspace, loop, step, model, milestone, trial, session ID, prompt path, the four token counts, cost, start and end (it is only named on the contributing architecture page) | `docs/how-it-works/state-and-files.md` (a short "Every call as CSV" section), linked from `docs/guides/configuration.md#models-per-step` for comparing runs |
| 16 | `:305` | Progress lines use colors only in a terminal, and never when `NO_COLOR` is set; secrets are redacted from every line | `docs/how-it-works/run-lifecycle.md#following-a-run` |
| 17 | `:313`–`:314` | `state/run.log` is devloops' own file: a call that runs while it is written is not charged with a write outside its target | `docs/how-it-works/run-lifecycle.md#following-a-run` (or `docs/guides/security.md#where-claude-code-may-write`) |
| 18 | `:617` | `DEVLOOPS_NO_BROWSER=1` also keeps `devloops dashboard` from opening a browser | `docs/guides/dashboard.md#start-it` |
| 19 | `:709`, `:821` | Questions raised during a trial are appended to `open-questions.md` as new `OQ<n>` entries; accepted ones are recorded in `run.json` (`auto_answers`) and as an `answers-accepted` event | `docs/guides/approval-and-questions.md#questions-while-a-milestone-is-built` |
| 20 | `loops/orchestrator/README.md:31` | Without a recorded review mode, the frontend loop takes the backend's frozen one | `docs/guides/approval-and-questions.md#who-answers-the-questions-setting` |
