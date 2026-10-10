# Contract: test_docs

`loops/shared/tests/test_docs.py`. Every failure names the page (file and line where it applies)
and the item.

| # | Check | Fails when |
|---|-------|------------|
| 1 | reference pages are current | `gen_reference.py --check` reports a differing page |
| 2 | descriptions match the code | a value in the code has no description, or a description has no value |
| 3 | front matter | a hand-written page lacks `title`/`description`/`sources`; a source path does not exist; a requirement ID is not in its spec |
| 4 | commands, keys and paths in pages | a `devloops …` line names an unknown command or option; an inline-code configuration key (dotted, or a top-level key name) is not in the schemas; a workspace path in inline code matches no file in `workspace-files.txt` (`<id>`, `<n>`, `<seq>`, `<loop>` are wildcards) |
| 5 | status diagrams | a status value of a kind is missing from that kind's diagram on `how-it-works/statuses.md` |
| 6 | examples are current | `examples.py --check` reports a differing example |
| 7 | site builds strictly | `zensical build --strict` exits non-zero (skipped when Zensical is not installed; always run in CI) |

Links and anchors (including links to reference entries) are checked by check 7.
