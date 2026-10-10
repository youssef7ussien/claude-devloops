# Contract: tools/docs/descriptions.json

```json
{
  "exit_codes": { "0": {"name": "completed", "meaning": "…", "next": "…"}, "10": {} },
  "steps": { "plan": "…", "replan": "…", "implement": "…", "fix": "…", "author-checks": "…", "validate-ui": "…" },
  "statuses": {
    "run": { "running": "…", "paused": "…", "stopped": "…", "completed": "…" },
    "loop": { "planning": "…" },
    "milestone": {}, "task": {}, "trial": {}, "approval": {}
  },
  "stop_reasons": { "<status_reason.code>": "…" },
  "files": { "<loop>/state/run.log": "…", "run/state.json": "…" }
}
```

Rules (`test_docs` check 2): for each group, the keys equal the values in the code exactly
(missing → "add a description for X"; extra → "X no longer exists"). Texts follow the writing
style: plain, one or two sentences, no undefined terms.

`files` has one entry per file the sample run writes (`docs-include/examples/workspace-files.txt`),
under its general name (`<loop>/state/milestones/<id>/trials/<n>/trial.json`): what the file
records. For the files with a schema, the reference page also lists the schema's fields.
