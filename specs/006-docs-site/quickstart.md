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
