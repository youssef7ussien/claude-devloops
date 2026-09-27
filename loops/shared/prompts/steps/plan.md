# Step: plan

Read the requirements named in the Context block, and any existing code in the target directory.
You have read-only tools. Do not write any file. Return a plan as structured output.

## What the plan contains

- **requirements_inventory**: every requirement or story the plan covers, using the source
  document's own identifiers as `ref`, with a one-line summary.
- **stack**: the technology to use, chosen in this priority order, with `source` set accordingly:
  1. `existing-code`: the target already has code; keep its stack.
  2. `requirements` or `configuration`: the requirements or the loop configuration name a stack.
  3. `proposed`: neither of the above; propose a simple, common stack and say why in `summary`.

  If these sources disagree (for example the requirements name a stack that differs from the
  existing code), list each disagreement in `conflicts` and ask about it in `open_questions`.
- **runtime**: the commands the driver will run: optional `install_command`, `start_command`,
  `cwd` (relative to the target), `base_url`, `ready_url` (a URL that answers once the app is
  ready), and optional `unit_test_command`. Follow the loop instructions for any other field.
- **milestones**: an ordered list. Each milestone has an ID (`M01`, `M02`, ...), a title, a goal,
  `depends_on` (earlier milestone IDs only), tasks (`M01-T01`, ...), and acceptance criteria
  (`M01-AC1`, ...). List milestones in dependency order.
  - Keep milestones small enough to implement and validate in one pass.
  - Every task and criterion cites at least one `requirement_refs` entry from the inventory.
  - Acceptance criteria describe **observable behavior** that can be checked from outside the
    code. "It compiles", "it starts", or "the code exists" are never acceptance criteria.
- **open_questions**: questions whose answers would change the plan (`OQ1`, `OQ2`, ...), each with
  context and the milestone IDs it affects. The developer answers them before implementation.
- **assumptions**: every assumption the plan relies on, stated explicitly, with its source.

## Previous attempt

If the Context block contains `previous_attempt`, your last plan was rejected. Fix every listed
problem and return a complete plan again.
