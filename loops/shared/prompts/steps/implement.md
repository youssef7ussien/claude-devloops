# Step: implement

Implement the milestone given in the Context block, in the target directory.

- The Context block lists only the tasks that are not achieved yet, the milestone's acceptance
  criteria, the stack and runtime from the approved plan, and the approved answers.
- Implement every listed task so that each acceptance criterion holds when the driver starts the
  application with the plan's runtime commands and checks it from outside.
- Keep the runtime commands working: the driver runs them exactly as the plan declares them.
- Earlier achieved milestones must keep working. Do not break or rewrite them.
- You may run commands (build, install, tests) to check your work, but the driver's validation
  is what counts.

## Structured result

- `tasks`: one entry per listed task: `task_id`, `status` (`implemented` or `not-implemented`),
  and a short `note`.
- `assumptions`: every ambiguity you resolved yourself, as `{text, affects}` where `affects` lists
  task or criterion IDs. Each one is shown to the developer for review.
- `needs_input`: questions you cannot resolve without adding, removing, or contradicting a
  requirement, as `{question, requirement_refs, suggested_answer, suggestion_reason}`. Anything
  that would change the requirements goes here, never into `assumptions`. A non-empty list stops
  the milestone until the developer answers. `suggested_answer` is the answer you would choose,
  concrete enough to use as written (the developer may accept it unchanged), and
  `suggestion_reason` says why; leave `suggested_answer` empty only when no answer can reasonably
  be recommended.
- `files_changed`: the paths you created or modified, relative to the target directory.
