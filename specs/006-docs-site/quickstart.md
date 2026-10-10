# Quickstart: checking the documentation site

Run from the repository root.

## Build and preview

```sh
python3 -m venv .venv-docs && .venv-docs/bin/pip install -r tools/docs/requirements.txt
.venv-docs/bin/zensical serve                    # http://localhost:8000, live reload
.venv-docs/bin/zensical build --strict --clean   # must exit 0 with no warnings
```

## Regenerate what is generated

```sh
python3 tools/docs/gen_reference.py      # docs/reference/
python3 tools/docs/examples.py           # docs-include/examples/
node tools/docs/screenshots.mjs          # docs/assets/screenshots/ (needs Chromium; by hand)
```

## Tests

```sh
cd loops/shared/tests && VISUAL=true EDITOR=true python3 -m unittest test_docs
```

Expected: OK; check 7 runs when `zensical` is on PATH (activate `.venv-docs`).

## Scenarios (spec)

| Scenario | How to check | Expected |
|----------|--------------|----------|
| Drift is caught (US4, SC-004) | add a dummy `--flag` to a command in `cli.py`; run `test_docs` | check 1 fails naming `reference/commands.md`; revert |
| Broken link is caught (SC-005) | link to `reference/configuration.md#no-such-key` in a page; build strictly | the build fails naming the page; revert |
| Unknown path is caught | write `` `state/nope.json` `` in a page; run `test_docs` | check 4 names the page and the path; revert |
| Getting started works (US3, SC-002) | follow `getting-started/first-run.md` on a fresh sample project | every command works as shown |
| Landing page (US1, SC-001) | two readers new to devloops read only `index.md` | each can say what devloops does, why to trust it, how to start |
| How it works (US2, SC-003) | the same readers read `how-it-works/` | each answers what happens after a failed check, out of trials, an interruption, an open question |
| Manual covered (SC-008) | read `manual-map.md` | every manual heading has a page or a reason |
| Published (SC-006) | push to `main` | the workflow passes; the change is live within 10 minutes |

## Getting started works

Walked through on 2026-10-10 (T030), following `getting-started/install.md` and
`getting-started/first-run.md` word for word, with the stand-in Claude Code answering as in the
examples (`tools/docs/examples.py`: the same plan and checks):

- `uv tool install` from the repository installed `devloops`; `devloops --version` printed
  `devloops 0.2.0`.
- In a new folder (`mkdir app`, `requirements.md` copied from the page): `init`, `check`,
  `run --review-plan` (exit 10), `approve` and `status` exited as the page says, and each output
  matched the page's (after the examples' normalisation; `check` shows this machine's versions).
- Every file the page names exists: `.devloops/devloops.json`, `.claude/skills/`, `.gitignore`,
  the code in `backend/`, and `outputs/` with `final-report.md`, `plan-summary.md`,
  `open-questions.md`, `openapi.json` and one `milestone-NN-slug.md` per milestone.
- `devloops dashboard` served the workspace and answered 200.

Fixed on the way: the final report has a "Suggested answers accepted" section only when one was
accepted; the page said it always has.

## Independent review (T047)

Done on 2026-10-10 by seven separate reviewers, each reading its pages against their `sources`
and the code, and fixing each finding in place (statements it could not confirm, terms neither
explained nor linked, planned or removed behavior shown as current). Pages reviewed, all 30
hand-written ones plus the root `README.md`:

- `how-it-works/`: `index`, `run-lifecycle`, `steps`, `validation`, `trials-and-recovery`,
  `statuses`, `state-and-files`, `dashboard-data`
- `guides/`: `backend-loop`, `frontend-loop`, `dashboard`, `approval-and-questions`,
  `configuration`, `prompts`, `spec-kit`, `skills`, `security`, `upgrades`, `limitations`
- `index`, `getting-started/install`, `getting-started/first-run`, `glossary`, `reference/index`
- `contributing/`: `index`, `architecture`, `testing`, `specs-process`, `documentation`,
  `writing-style`

Errors fixed include: which tools a run checks before starting; that `--review-plan` holds for
the rest of a run; that a `stopped-on-input-error` loop cannot be resumed by restoring the
input; that the write guard blocks a write rather than failing the trial; the exit code of a bad
project setting (30); that `backend.*` settings are always replaced by the handoff; that the
`replan` approval value is never recorded; when a final report is written; and the example
`check` output showing a Claude Code version below the minimum.

Code issues the review found, left for a later change (not documentation):

- `validators/curl.py` stops a loop with the reason `validation-failed`, which the run-state
  schema's stop reasons do not list.
- `approval.action` lists `replan`, which nothing records.
- The `input-changed` message says to restore the file, but the stop cannot be resumed.
- A missing tool met while resuming outside `devloops run` (e.g. `retry --no-continue`) can end
  a loop as `stopped-on-input-error`.
- `backend.*` settings never take effect (the handoff overrides them); `runtime` is shared by
  both loops.
- The installed `.devloops/prompts/README.md` and the `status` line say an override applies
  from the next start; it applies from the next call.
- `outputs/openapi.json` is not written atomically.
- `checkcmd` links Claude Code's documentation at a different address than the site.
