# Data Model: Documentation Site

The "data" of this feature is files in the repository. See [research.md](./research.md) for why
each exists.

## Page (`docs/**/*.md`)

- **Hand-written page**: Markdown with front matter ([page-front-matter](./contracts/page-front-matter.md)):
  `title`, `description` (one sentence, used by search and link previews), `sources` (non-empty).
  Belongs to one navigation section. Follows the writing style (FR-014–FR-016): a term is explained
  where first used or linked to the glossary; a mention of a command, option, configuration key,
  step, status or exit code links to its reference entry.
- **Generated page** (`docs/reference/*.md`): produced by `tools/docs/gen_reference.py`; starts
  with front matter `generated: true` and a visible note "This page is generated from devloops'
  code; do not edit it." Never has `sources` (its source is the code). Contents:
  [reference-pages](./contracts/reference-pages.md).
- **Validation**: hand-written pages are checked by `test_docs` checks 3–5; every page by the
  strict build ([docs-tests](./contracts/docs-tests.md)).

## Reference entry

One row or heading in a generated page with a stable anchor that prose links to:
`#<command>` and `#<command>--<option>` (commands), `#<dotted.key>` with dots kept
(configuration), `#exit-<code>`, `#step-<name>`, `#<kind>-<status>` (statuses), `#<file-name>`
(state files). Anchors are set explicitly (`attr_list`), not derived from titles, so wording can
change without breaking links.

## Descriptions (`tools/docs/descriptions.json`)

Meanings the code does not hold, keyed by the value in the code
([descriptions](./contracts/descriptions.md)): exit codes, steps, each kind of status, stop-reason
codes, and the files a run writes. Rule: the set of keys of each group equals the set of
values in the code (`test_docs` check 2).

## Configuration description

The `description` of a key in `config.schema.json` / `project-config.schema.json` (and their spec
contract copies). Every key has one after this feature (R-6).

## Example (`docs-include/examples/<name>.txt`)

The output of one command of the sample run, or a file excerpt, written by
`tools/docs/examples.py` with temporary paths (`<project>`), times (`2026-01-01T00:00:00Z`) and
durations (`1s`) replaced. Included into pages with snippets (`--8<-- "examples/<name>.txt"`).
`workspace-files.txt` lists every file the sample run wrote, workspace-relative, sorted.

## Screenshot (`docs/assets/screenshots/<view>.png`)

One per dashboard view, from the sample run (R-10); referenced with alt text that says what the
view shows.

## Glossary entry

A heading in `docs/glossary.md` (anchor = the term, lower case) with a plain definition and a link
to where the term is explained in depth; the same term with a one-line definition in
`docs-include/abbreviations.md` (`*[term]: definition`) so it shows on hover everywhere.

## Manual map (`specs/006-docs-site/manual-map.md`)

A table: manual heading (file and line) → new page and section, or "dropped" with the reason.
Every heading of `loops/README.md` and `loops/orchestrator/README.md` has one row (SC-008).

## Status values (code)

`state.RUN_STATUSES`, `MILESTONE_STATUSES`, `TASK_STATUSES`, `TRIAL_STATUSES` (new constants,
R-5); loop statuses and stop-reason codes stay in `run-state.schema.json`'s enums. Each set is
drawn as a state diagram on `how-it-works/statuses.md`.
