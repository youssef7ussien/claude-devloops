# Task: frontend-dev (workspace `{{workspace}}`)

Build the frontend described by the requirements below, milestone by milestone, until every
milestone's acceptance criteria pass in a real browser. See `Loop-instructions.md` in this
directory for the full rules; this file only records the current run's inputs and outputs.

## Inputs

- **Requirements**: `{{requirements_path}}` (sha256 `{{requirements_sha256}}`)
- **Mode**: `{{mode}}`; story: `{{story_id}}`
- **Target directory** (the only place you may write): `{{target_dir}}`
- **API spec** (the backend contract; call only the operations it declares): `{{api_spec_path}}`

## Effective configuration

{{effective_config}}

## Outputs

- `outputs/milestone-<NN>-<slug>.md`: one per milestone, with its tasks and acceptance criteria.
- `outputs/plan-summary.md`: the chosen stack and the milestone list.
- `outputs/ui-url.txt`: the URL the frontend is served at, recorded when it is first validated.
- `outputs/open-questions.md`: anything you could not resolve from the requirements.
- `progress.md` and `outputs/final-report.md`: run status and outcome, rendered by the driver.

You do not write any of these files yourself (except through the `implement`/`fix` steps' own
target-directory changes, which the driver's own rendering never touches); the driver renders them
from state after every trial.
