# Step: replan

The developer reviewed your previous plan and answered its open questions. Plan again.

- The Context block gives the path of the answers file and its content, and the path of the
  previous plan. Read both.
- Treat every answer as authoritative. Apply it to the stack, runtime, milestones, tasks, and
  acceptance criteria it affects.
- Keep what the answers do not affect. Do not reorganize the plan without a reason.
- Drop questions that are now answered. Ask new questions only if the answers raise them.
- You have read-only tools. Do not write any file.

Return a complete plan in the same structured format and under the same rules as the `plan` step:

- a requirements inventory using the source document's own identifiers;
- the stack with its source (existing code, then requirements or configuration, then a proposal)
  and any conflicts, each with an open question;
- the runtime commands;
- milestones in dependency order, each with tasks and observable acceptance criteria, every one
  citing requirement references from the inventory;
- open questions and explicit assumptions.
