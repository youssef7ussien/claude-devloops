# Contract: Generated Reference Pages

`python3 tools/docs/gen_reference.py` writes these files and nothing else; `--check` exits 1 and
names each file that differs (used by `test_docs` check 1). Output is deterministic: the same code
gives the same bytes.

| Page | Holds | From |
|------|-------|------|
| `docs/reference/commands.md` | each command: its one-line help, usage, options (name, argument, default, help), which options exclude each other; global options; removed options and what replaced them | `cli.build_parser()`, `cli.REMOVED_DASHBOARD_FLAGS` |
| `docs/reference/configuration.md` | where configuration comes from and the merge order; each key of the run configuration and of the project file: dotted name, type, allowed values, default, description | `config.schema.json`, `project-config.schema.json`, `config.py` docstring |
| `docs/reference/exit-codes.md` | each exit code: number, name, meaning, what to do | `state.EXIT_CODES`, `EXIT_USAGE`, `EXIT_LOCK_HELD`, the error classes; `descriptions.json` |
| `docs/reference/steps.md` | each step in driver order: what it does, whether it may write, its tools, its output | `claude.STEPS`; `descriptions.json` |
| `docs/reference/statuses.md` | each kind of status (run, loop, milestone, task, trial, approval) and each stop-reason code, with meanings | the constants and schema enums (data-model); `descriptions.json` |
| `docs/reference/state-files.md` | each file a run writes, where, and what it records; the fields of the files that have a schema | `docs-include/examples/workspace-files.txt`, the schemas, `descriptions.json` |

Every entry has an explicit anchor (data-model, Reference entry). Each page starts with
`generated: true` front matter and the "do not edit" note. Options hidden from `--help`
(`argparse.SUPPRESS`) are left out.
