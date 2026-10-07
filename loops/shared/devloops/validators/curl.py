"""The `backend-dev` validator: driver-executed curl checks against a frozen check set.

Research R-8. Evidence comes from real `curl` runs the driver performs itself, never from the
model's account of them (FR-032, SC-002). The checks are authored once by a separate, read-only
Claude call (`author-checks`) and then frozen to `state/milestones/<id>/checks.json`, so a `fix`
trial cannot weaken its own tests (FR-069). The contract check (FR-019) fails a trial whose checks
call an operation the target's OpenAPI document does not declare. The published
`outputs/openapi.json` names only the operations an achieved milestone's checks verified (a
success status, on the path really called); the others are left out and listed (D-14).
"""
import copy
import hashlib
import json
import os
import re
import shlex
import subprocess

from .. import openapi, state
from ..claude import CallFailed
from ..runtime import Runtime
from .unit_tests import run as run_unit_tests

VAR_RE = re.compile(r"\$\{([a-zA-Z0-9_]+)\}")
CHECK_TIMEOUT_SECONDS = 30  # per curl check; a hanging endpoint fails its check, not the run


CHECK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")  # used in evidence file names


class InvalidChecksError(CallFailed):
    """`author-checks` produced an output that breaks a rule beyond its schema (invalid-output).

    Schema-shape failures are already caught generically by `ClaudeRunner.call` (FR-069); this
    covers the semantic rules: check ids are unique and safe as file names, and every acceptance
    criterion is covered by at least one check.
    """

    def __init__(self, detail):
        super().__init__("invalid-output", detail)


# --- the checks file (author, freeze, or load) --------------------------------------------------

def _checks_path(loop_dir, milestone_id):
    return os.path.join(loop_dir, "state", "milestones", milestone_id, "checks.json")


def _load_spec(target_dir, runtime):
    """The target's current OpenAPI document, or `None` if it does not exist or does not parse."""
    rel = (runtime or {}).get("openapi_path")
    if not rel:
        return None
    path = os.path.join(target_dir, rel)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _author_checks(ctx):
    milestone = ctx.milestone
    context = {
        "loop": ctx.loop, "step": "author-checks",
        "workspace": getattr(ctx.workspace, "name", None),
        "target_dir": ctx.target_dir,
        "runtime": ctx.runtime,
        "milestone": {"id": milestone["id"], "title": milestone["title"], "goal": milestone["goal"],
                     "acceptance_criteria": milestone["acceptance_criteria"]},
        "openapi_document": _load_spec(ctx.target_dir, ctx.runtime),
    }
    out = ctx.runner.call("author-checks", context, ctx.target_dir, milestone_id=milestone["id"],
                          trial=ctx.trial, add_dirs=ctx.input_dirs)
    if not out.ok:  # keep the call's own reason: a timeout or a service failure is not our rule
        raise CallFailed(out.failure_reason, f"author-checks failed: {out.failure_detail}",
                         out.failure_class)
    checks_doc = out.structured_output
    ids = [check["id"] for check in checks_doc["checks"]]
    unsafe = [i for i in ids if not CHECK_ID_RE.match(i)]
    if unsafe:
        raise InvalidChecksError("check ids must be letters, digits, '_', '.' or '-' (they name "
                                 "evidence files); invalid: " + ", ".join(map(repr, unsafe)))
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise InvalidChecksError("check ids must be unique; repeated: " + ", ".join(duplicates))
    covered = {cid for check in checks_doc["checks"] for cid in check["criteria"]}
    missing = [c["id"] for c in milestone["acceptance_criteria"] if c["id"] not in covered]
    if missing:
        raise InvalidChecksError("the authored checks do not cover every acceptance criterion; "
                                 "missing " + ", ".join(missing))
    return checks_doc


def _load_or_author_checks(ctx):
    """The milestone's frozen checks, authoring and freezing them first if none exist yet.

    Keyed on the file, not the trial number: a trial whose authoring failed (or was interrupted)
    leaves nothing frozen, and the next trial authors again instead of loading nothing.
    """
    path = _checks_path(ctx.loop_dir, ctx.milestone["id"])
    checks_doc = state.read_json(path)
    if checks_doc is None:
        checks_doc = _author_checks(ctx)
        state.write_json_atomic(path, checks_doc)
    return checks_doc


# --- one curl check ------------------------------------------------------------------------------

def _as_text(value):
    """A captured value as text: a string as itself, anything else as compact JSON (`true`,
    `null`, `["a","b"]`)."""
    return value if isinstance(value, str) else json.dumps(value, separators=(",", ":"))


def _substitute(value, variables, typed=True):
    """`value` with each captured `${var}` filled in. With `typed`, a string that is exactly one
    `${var}` becomes the captured value itself, keeping its JSON type (`"${id}"` is `1` when `id`
    captured `1`); otherwise, and inside a longer string, the value is spliced in as text. A
    variable nothing captured is left as it is (`_missing_variables` reports it)."""
    if not isinstance(value, str):
        return value
    whole = VAR_RE.fullmatch(value)
    if typed and whole and whole.group(1) in variables:
        return variables[whole.group(1)]

    def repl(match):
        name = match.group(1)
        return _as_text(variables[name]) if name in variables else match.group(0)
    return VAR_RE.sub(repl, value)


def _substitute_json(value, variables):
    if isinstance(value, str):
        return _substitute(value, variables)
    if isinstance(value, dict):
        return {k: _substitute_json(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_json(v, variables) for v in value]
    return value


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def _missing_variables(check, variables):
    """The `${var}`s a check uses, in the places that are substituted, that no earlier check
    captured."""
    request, expect = check["request"], check["expect"]
    places = [request.get("path"), request.get("headers"), request.get("body"),
              expect.get("body_contains"), expect.get("json_equals")]
    return sorted({name for text in _strings(places) for name in VAR_RE.findall(text)
                   if name not in variables})


_ABSENT = object()


def _dotted_get(obj, path, default=None):
    """The value at a dotted path, or `default`. A part steps into an object by key, or into an
    array by index (`0.name` on a top-level array, `items.-1` for the last item)."""
    current = obj
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and re.fullmatch(r"-?[0-9]+", part) \
                and -len(current) <= int(part) < len(current):
            current = current[int(part)]
        else:
            return default
    return current


def _read_text(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:  # binary bodies are fine too
            return f.read()
    except OSError:
        return ""


def _try_json(text):
    try:
        return json.loads(text) if text else None
    except ValueError:
        return None


def _run_check(check, base_url, variables, evidence_dir, redactor):
    """Run one check with `curl`; return `(result_dict, method, resolved_path)`.

    `result_dict` matches the `checks[]` item of `validation-result.schema.json`. Evidence
    (headers, body, and the redacted command line) is saved under `evidence_dir` regardless of
    whether the check passes.
    """
    cid = check["id"]
    method = check["request"]["method"]
    path = _substitute(check["request"]["path"], variables, typed=False)
    if not path.startswith("/"):
        path = "/" + path  # "relative to base_url" either way; never glue it onto the port
    headers = {k: _substitute(v, variables, typed=False)
              for k, v in (check["request"].get("headers") or {}).items()}
    body = _substitute_json(check["request"].get("body"), variables)
    if body is not None and not any(k.lower() == "content-type" for k in headers):
        headers["Content-Type"] = "application/json"  # curl would otherwise send form-urlencoded

    os.makedirs(evidence_dir, exist_ok=True)
    headers_file = os.path.join(evidence_dir, f"{cid}.headers")
    body_file = os.path.join(evidence_dir, f"{cid}.body")

    # `-X HEAD` makes curl wait for a body that never comes; `--head` is the real HEAD request.
    method_args = ["--head"] if method == "HEAD" else ["-X", method]
    argv = ["curl", "-sS", "--max-time", str(CHECK_TIMEOUT_SECONDS), *method_args,
            base_url.rstrip("/") + path]
    for key, value in headers.items():
        argv += ["-H", f"{key}: {value}"]
    command_line = " ".join(shlex.quote(a) for a in argv)
    if body is not None:
        request_body_file = os.path.join(evidence_dir, f"{cid}.request-body.json")
        with open(request_body_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(body))
        argv += ["--data-binary", f"@{request_body_file}"]
        command_line += f" --data-binary {shlex.quote(json.dumps(body))}"
    argv += ["-D", headers_file, "-o", body_file, "-w", "%{http_code}"]

    missing = _missing_variables(check, variables)
    if missing:
        # A variable an earlier check did not capture (usually because that check failed) would
        # be sent as the literal `${var}`, with whatever side effects that has on the server; the
        # request is not sent, and the failure points at its cause.
        failures = [f"uses ${{{name}}}, which no earlier check captured (did the check that "
                    f"should capture it fail?); not sent" for name in missing]
        for path_ in (headers_file, body_file):
            open(path_, "w", encoding="utf-8").close()
        status, body_text, response_json = 0, "", None
    else:
        failures = []
        try:
            # `--max-time` is the real limit; this is a backstop in case curl itself hangs.
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  timeout=CHECK_TIMEOUT_SECONDS + 10)
            status = int((proc.stdout or "").strip() or 0)
            if proc.returncode != 0:
                failures.append(f"curl exited {proc.returncode}: {(proc.stderr or '').strip()}")
        except subprocess.TimeoutExpired:
            status = 0
            failures.append(f"curl did not finish within {CHECK_TIMEOUT_SECONDS + 10}s")
        body_text = _read_text(body_file)
        response_json = _try_json(body_text)

        expect = _substitute_json(check["expect"], variables)
        if status != expect["status"]:
            failures.append(f"expected status {expect['status']}, got {status}")
        for token in expect.get("body_contains") or []:
            # A captured number, object or array: compact or with the usual spaces, as servers
            # write either.
            forms = [_as_text(token)] + ([] if isinstance(token, str) else [json.dumps(token)])
            if not any(form in body_text for form in forms):
                failures.append(f"body does not contain {forms[0]!r}")
        for path_expr, expected in (expect.get("json_equals") or {}).items():
            actual = _dotted_get(response_json, path_expr)
            if actual != expected:
                failures.append(f"{path_expr}: expected {expected!r}, got {actual!r}")

    # Only a path that exists captures; a JSON `null` there is a captured value.
    for var, path_expr in (check.get("capture") or {}).items():
        value = _dotted_get(response_json, path_expr, _ABSENT)
        if value is _ABSENT:
            variables.pop(var, None)
        else:
            variables[var] = value
    # Captured values now appear in the failure text, so it is redacted like the command line.
    failures = [redactor.redact(f)[0] for f in failures]

    redacted_command, _ = redactor.redact(command_line)
    with open(os.path.join(evidence_dir, f"{cid}.command"), "w", encoding="utf-8") as f:
        f.write(redacted_command + "\n")

    result = {
        "check_id": cid, "passed": not failures, "command": redacted_command,
        "response": {"status": status, "headers_path": f"evidence/{cid}.headers",
                    "body_path": f"evidence/{cid}.body"},
        "failures": failures,
    }
    return result, method, path


# --- criteria and the contract -------------------------------------------------------------------

def _criteria(acceptance_criteria, checks, results_by_id):
    entries = []
    for c in acceptance_criteria:
        cid = c["id"]
        relevant = [results_by_id[chk["id"]] for chk in checks if cid in chk["criteria"]]
        if not relevant:
            entries.append({"criterion_id": cid, "passed": False,
                            "observed": "no check covers this criterion", "evidence": []})
            continue
        passed = all(r["passed"] for r in relevant)
        observed = "; ".join(r["check_id"] + (" passed" if r["passed"] else " failed: "
                            + "; ".join(r["failures"])) for r in relevant)
        evidence = []
        for r in relevant:
            evidence += [r["response"]["body_path"], r["response"]["headers_path"]]
        entries.append({"criterion_id": cid, "passed": passed, "observed": observed,
                        "evidence": evidence})
    return entries


def _achieved_coverage(loop_dir, run_state, exclude_milestone_id=None):
    """`(operations, requests)` verified by the achieved milestones other than the excluded one.

    `operations` are the `(METHOD, template)` pairs each one's passing trial recorded in its
    `validation.json` (`contract.covered_operations`, matched from the paths its checks really
    called). A milestone achieved before that was recorded gives its checks' raw
    `(method, path)` in `requests` instead, matched against the document by the caller.
    """
    operations, requests = set(), []
    for mid, ms in (run_state.get("milestones") or {}).items():
        if mid == exclude_milestone_id or ms.get("status") != "achieved":
            continue
        passed = [t["n"] for t in ms.get("trials") or [] if t.get("status") == "passed"]
        doc = state.read_json(os.path.join(loop_dir, "state", "milestones", mid, "trials",
                                           str(passed[-1]), "validation.json")) if passed else None
        recorded = ((doc or {}).get("contract") or {}).get("covered_operations")
        if recorded is not None:
            operations |= {tuple(op.split(" ", 1)) for op in recorded}
            continue
        checks = state.read_json(_checks_path(loop_dir, mid))
        requests += [(c["request"]["method"], c["request"]["path"])
                     for c in (checks or {}).get("checks", [])]
    return operations, requests


def _covered(spec, base_url, operations, requests):
    """The declared operations among `operations`, plus those `requests` call."""
    declared = openapi.operations(spec)
    found = {op for op in operations if op in declared}
    return found | {m for m in (openapi.match(spec, method, path, base_url)
                                for method, path in requests) if m is not None}


# A check expecting one of these statuses on an undocumented (method, path) shows the endpoint is
# absent, which agrees with the document; it is not an undocumented call (T076).
ABSENCE_STATUSES = (404, 405)


def _contract(spec, base_url, checks_used, earlier):
    """`checks_used` is `[(method, path, expected_status)]` for this milestone's checks, with
    the paths they really called; `earlier` is `_achieved_coverage` of the other milestones.

    The contract fails when a check calls an operation the document does not declare
    (`unmatched_operations`), or when there is no document. A check expecting 404 or 405 neither
    fails it on an undocumented path (it shows the path is absent) nor verifies a documented
    operation (its success path was never called). A declared operation no achieved check has
    verified is in `unverified_operations`: it does not fail the trial, and it is left out of the
    published `outputs/openapi.json` (see `_publish`). `covered_operations` records what this
    milestone's checks verified, for later milestones and for publishing.
    """
    if spec is None:
        return {"passed": False,
                "unmatched_operations": ["no OpenAPI document at runtime.openapi_path"],
                "unverified_operations": [], "covered_operations": []}
    unmatched, mine = [], set()
    for method, path, expected_status in checks_used:
        matched = openapi.match(spec, method, path, base_url)
        if matched is None:
            if expected_status not in ABSENCE_STATUSES:
                unmatched.append(f"{method} {path}")
        elif expected_status not in ABSENCE_STATUSES:
            mine.add(matched)
    covered = mine | _covered(spec, base_url, *earlier)
    return {"passed": not unmatched, "unmatched_operations": list(dict.fromkeys(unmatched)),
            "unverified_operations": _names(openapi.operations(spec) - covered),
            "covered_operations": _names(mine)}


def _names(operations):
    return sorted(f"{m} {p}" for m, p in operations)


UNVERIFIED_KEY = "x-devloops-unverified-operations"


def verified_document(spec, covered):
    """`(document, omitted)`: `spec` without the declared operations not in `covered`, and those
    operations as `"METHOD /path"`. A path whose operations were all removed goes too; a path
    item that is only a `$ref` (no inline operation) is kept as it is. The document names the
    omitted operations under `x-devloops-unverified-operations`, so the frontend knows they exist
    but must not be relied on."""
    omitted = _names(openapi.operations(spec) - covered)
    doc = copy.deepcopy(spec)
    for template, item in list((doc.get("paths") or {}).items()):
        if not isinstance(item, dict):
            continue
        ops = [m for m in openapi.HTTP_METHODS if m in item]
        for method in ops:
            if (method.upper(), template) not in covered:
                del item[method]
        if ops and not any(m in item for m in openapi.HTTP_METHODS):
            del doc["paths"][template]
    doc.pop(UNVERIFIED_KEY, None)
    if omitted:
        doc[UNVERIFIED_KEY] = omitted
    return doc, omitted


# --- the adapter interface ------------------------------------------------------------------------

def prepare(ctx):
    """Author and freeze the checks before the trial's implement/fix call (FR-069)."""
    _load_or_author_checks(ctx)


def validate(ctx):
    checks_doc = _load_or_author_checks(ctx)
    runtime = ctx.runtime
    cwd = os.path.join(ctx.target_dir, runtime.get("cwd") or ".")
    ready_timeout = (ctx.config.get("runtime") or {}).get("ready_timeout_seconds", 120)
    log_path = os.path.join(ctx.trial_dir, "runtime.log")

    variables = {}
    check_results = []
    checks_used = []
    with Runtime(runtime["start_command"], cwd, runtime["ready_url"], ready_timeout,
                log_path=log_path):
        for check in checks_doc["checks"]:
            result, method, path = _run_check(check, runtime["base_url"], variables,
                                              ctx.evidence_dir, ctx.redactor)
            check_results.append(result)
            checks_used.append((method, path, check["expect"]["status"]))
        unit_tests = run_unit_tests(ctx.config, (ctx.plan or {}).get("runtime"), ctx.target_dir,
                                    ctx.trial_dir, redactor=ctx.redactor)

    results_by_id = {r["check_id"]: r for r in check_results}
    criteria = _criteria(ctx.milestone["acceptance_criteria"], checks_doc["checks"], results_by_id)
    spec = _load_spec(ctx.target_dir, runtime)
    earlier = _achieved_coverage(ctx.loop_dir, ctx.run_state, ctx.milestone["id"])
    contract = _contract(spec, runtime["base_url"], checks_used, earlier)

    return {"kind": "curl", "checks": check_results, "criteria": criteria, "contract": contract,
           "unit_tests": unit_tests}


def _publish(ctx):
    """Publish the target's OpenAPI document as this workspace's verified artifact (FR-019):
    only the operations a check of an achieved milestone has called. The others are listed in
    `openapi_artifact.omitted_operations`; a later milestone whose checks call one publishes it.

    Each achieved milestone publishes from every achieved milestone's verified operations, so the
    last one leaves the final document. It runs right after the milestone was validated against
    the same document, so the document loads. If it no longer does, the milestone is failed
    again and the run stops, rather than leave an older artifact in place (`retry` validates and
    publishes it again).
    """
    runtime = ctx.runtime
    spec = _load_spec(ctx.target_dir, runtime)
    if spec is None:
        mid = ctx.milestone["id"]
        ms = ctx.run_state["milestones"][mid]
        ms["status"] = "failed"
        ms["tasks"] = {tid: "failed" for tid in ms.get("tasks", {})}
        raise state.StopRun("stopped-on-failure", "validation-failed",
                            f"the OpenAPI document at {runtime.get('openapi_path')} no longer "
                            f"loads after {mid} passed, so nothing was published; fix it, then "
                            f"`devloops retry` {mid}", milestone_id=mid)
    covered = _covered(spec, runtime.get("base_url"), *_achieved_coverage(ctx.loop_dir,
                                                                          ctx.run_state))
    doc, omitted = verified_document(spec, covered)
    content = (json.dumps(doc, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    dest = os.path.join(ctx.loop_dir, "outputs", "openapi.json")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        f.write(content)
    ctx.run_state["openapi_artifact"] = {
        "path": os.path.relpath(dest, ctx.loop_dir),
        "sha256": hashlib.sha256(content).hexdigest(),
        "omitted_operations": omitted,
    }


on_achieved = _publish
