# Step: fix

A previous trial of this milestone failed validation. Fix the implementation in the target
directory so that the milestone passes.

## Use the failure evidence

- The Context block has `previous_failure`: the trial number, the failure reason, a summary of
  what failed, and the paths of that trial's `validation.json` and `evidence/` directory. Read
  them before changing anything.
- Work out the cause from the evidence, then make the smallest change that fixes it. Do not
  rewrite working parts.
- The acceptance criteria and the validation checks are fixed. Change the implementation to meet
  them; never try to weaken or work around the checks.
- If the reason is `boundary-violation`, a previous change wrote outside the target directory.
  Keep every change inside the target.
- If `developer_guidance` is present, the developer granted extra trials with that guidance.
  Follow it.

## Scope

- The Context block lists only the tasks that are not achieved yet. Earlier achieved milestones
  must keep working.
- Keep the plan's runtime commands working.

## Structured result

Return the same result as the `implement` step: `tasks` (`task_id`, `status`, `note`),
`assumptions` (`{text, affects}`), `needs_input` (`{question, requirement_refs, suggested_answer,
suggestion_reason}`; anything that would add, remove, or contradict a requirement goes here; as
in `implement`, still finish the milestone, building on your suggested answer), and
`files_changed`.
