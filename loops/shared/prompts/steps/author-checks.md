# Step: author-checks

You have read-only tools. Do not write any file, and do not run anything. Turn the given
milestone's acceptance criteria into a frozen set of HTTP checks the driver will run itself with
`curl`. This happens once, before the milestone is implemented or fixed; the same checks are then
reused for every trial, so write them from the acceptance criteria and the current OpenAPI
document (both in the Context block), never from a claim about what the implementation does.

## What each check contains

- `id`: a short identifier, unique within this milestone (`C1`, `C2`, ...), made only of
  letters, digits, `_`, `.` and `-` (it names the check's evidence files).
- `criteria`: the acceptance criterion ID(s) this check is evidence for. **Every acceptance
  criterion of this milestone must be covered by at least one check** -- this is checked
  automatically, and a milestone with an uncovered criterion is rejected before implementation
  starts.
- `request`: `method`, `path` (relative to the runtime's `base_url`, starting with `/`), optional
  `headers`, and an optional JSON `body` (sent as `application/json` unless `headers` says
  otherwise). A `path` or a `body` string may reference a variable an earlier check in
  this same list captured, as `${var}`.
- `expect`: the required `status`, and optionally `body_contains` (substrings the raw response
  body must contain) and `json_equals` (a dotted JSON path in the response mapped to the exact
  value expected there, for example `"user.id"`). A numeric part indexes an array: `"0.name"` on
  a response that is an array, `"items.-1.id"` for the last item.
- `capture` (optional): variables to pull out of this check's response for a later check to use,
  as `{var: "dotted.path"}`, with the same path rules.

## Chaining checks

Order checks so that whatever a later check needs (for example the ID of a resource an earlier
check just created) is captured first. Each acceptance criterion phrased as "create X, then read
X back" is naturally two or more chained checks under the same criterion ID.

## Contract

Every check's `(method, path)` must exist as an operation in the current OpenAPI document; if the
document does not yet declare an operation this milestone's criteria need, that is the
implementation's job to add, not yours to check around. Only cover operations the milestone's
criteria actually call for.

The one exception is a check that shows something does **not** exist: a check that expects
`404` (an unknown path) or `405` (an unsupported method) on an undocumented `(method, path)` is
consistent with the document and is allowed. Such a check never counts as covering an operation.
