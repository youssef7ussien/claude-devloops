# Prompt overrides

devloops builds each Claude Code prompt from three packaged parts: the shared rules, the loop's
instructions, and the step's instructions. A file in this folder with one of the names below
replaces the matching packaged part for this project:

| File in `.devloops/prompts/` | Replaces |
|------------------------------|----------|
| `common.md` | the shared rules (`shared/prompts/common.md`) |
| `steps/<step>.md`, where `<step>` is `plan`, `replan`, `implement`, `fix`, `author-checks`, or `validate-ui` | that step's instructions (`shared/prompts/steps/<step>.md`) |
| `backend-dev/Loop-instructions.md`, `frontend-dev/Loop-instructions.md` | that loop's instructions (`<loop>/Loop-instructions.md`) |

To start one, copy the packaged file and edit the copy. From a source checkout the packaged files
are under `loops/`; when installed, they are in the `devloops_kit` package.

- **When they apply**: the parts are read again for every Claude Code call, so an override, or a
  change to one, is used from the next call, even by a run in progress.
- **Recorded**: every Claude Code call records which parts came from an override, with their
  fingerprints. A change between starts is recorded as an event, and `devloops status` reports it.
- **Other files**: any other file here is ignored. `devloops status` lists them (all but this
  README) under `warnings`, so a misspelled name is visible.

devloops never changes your override files, including on `devloops init --upgrade`.
