"""The `backend-dev` validator: driver-executed curl checks against a frozen check set.

Research R-8. Evidence comes from real `curl` runs the driver performs itself, never from the
model's account of them (FR-032, SC-002). The checks are authored once by a separate, read-only
Claude call (`author-checks`) and then frozen to `state/milestones/<id>/checks.json`, so a `fix`
trial cannot weaken its own tests (FR-069). The contract check (FR-019) also requires, at every
publication, that every operation the target's OpenAPI document declares is exercised by a check
of this milestone or of an earlier achieved one -- so the published document never names an
endpoint nothing ever verified.
"""
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

def _substitute(value, variables):
    if not isinstance(value, str):
        return value

    def repl(match):
        name = match.group(1)
        if name not in variables:
            return match.group(0)
        v = variables[name]
        return v if isinstance(v, str) else json.dumps(v)
    return VAR_RE.sub(repl, value)


def _substitute_json(value, variables):
    if isinstance(value, str):
        return _substitute(value, variables)
    if isinstance(value, dict):
        return {k: _substitute_json(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_json(v, variables) for v in value]
    return value


def _dotted_get(obj, path):
    current = obj
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
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
    path = _substitute(check["request"]["path"], variables)
    if not path.startswith("/"):
        path = "/" + path  # "relative to base_url" either way; never glue it onto the port
    headers = {k: _substitute(v, variables)
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

    expect = check["expect"]
    if status != expect["status"]:
        failures.append(f"expected status {expect['status']}, got {status}")
    for token in expect.get("body_contains") or []:
        if token not in body_text:
            failures.append(f"body does not contain {token!r}")
    for path_expr, expected in (expect.get("json_equals") or {}).items():
        actual = _dotted_get(response_json, path_expr)
        if actual != expected:
            failures.append(f"{path_expr}: expected {expected!r}, got {actual!r}")

    for var, path_expr in (check.get("capture") or {}).items():
        variables[var] = _dotted_get(response_json, path_expr)

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


def _earlier_achieved_checks(loop_dir, run_state, exclude_milestone_id):
    pairs = []
    for mid, ms in (run_state.get("milestones") or {}).items():
        if mid == exclude_milestone_id or ms.get("status") != "achieved":
            continue
        doc = state.read_json(_checks_path(loop_dir, mid))
        for check in (doc or {}).get("checks", []):
            pairs.append((check["request"]["method"], check["request"]["path"]))
    return pairs


# A check expecting one of these statuses on an undocumented (method, path) shows the endpoint is
# absent, which agrees with the document; it is not an undocumented call (T076).
ABSENCE_STATUSES = (404, 405)


def _contract(spec, base_url, checks_used, other_checks):
    """`checks_used` is `[(method, path, expected_status)]` for this milestone's checks."""
    if spec is None:
        return {"passed": False,
               "unmatched_operations": ["no OpenAPI document at runtime.openapi_path"]}
    unmatched = []
    covered = set()
    for method, path, expected_status in checks_used:
        matched = openapi.match(spec, method, path, base_url)
        if matched is not None:
            covered.add(matched)
        elif expected_status not in ABSENCE_STATUSES:
            unmatched.append(f"{method} {path}")
    for method, path in other_checks:
        matched = openapi.match(spec, method, path, base_url)
        if matched is not None:
            covered.add(matched)
    for op in openapi.operations(spec):
        if op not in covered:
            unmatched.append(f"{op[0]} {op[1]}")
    seen, uniq = set(), []
    for u in unmatched:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return {"passed": not uniq, "unmatched_operations": uniq}


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
    other_checks = _earlier_achieved_checks(ctx.loop_dir, ctx.run_state, ctx.milestone["id"])
    contract = _contract(spec, runtime["base_url"], checks_used, other_checks)

    return {"kind": "curl", "checks": check_results, "criteria": criteria, "contract": contract,
           "unit_tests": unit_tests}


def on_achieved(ctx):
    """Publish the target's OpenAPI document as this workspace's verified artifact (FR-019)."""
    runtime = ctx.runtime
    spec_path = os.path.join(ctx.target_dir, runtime.get("openapi_path") or "")
    if not os.path.isfile(spec_path):
        return
    with open(spec_path, "rb") as f:
        content = f.read()
    dest = os.path.join(ctx.loop_dir, "outputs", "openapi.json")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        f.write(content)
    ctx.run_state["openapi_artifact"] = {
        "path": os.path.relpath(dest, ctx.loop_dir),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def on_complete(ctx):
    """A last safeguard (FR-019): the completed document must still name only verified operations.

    A failure here demotes the last milestone back to `failed` and stops the run instead of
    completing it; `Engine._complete` has no try/except around this call, so the `StopRun` we
    raise propagates all the way out to `Engine.run`, which records the stop the same way any
    other stop is recorded.
    """
    runtime = ctx.runtime
    spec = _load_spec(ctx.target_dir, runtime)
    if spec is None:
        return
    other_checks = _earlier_achieved_checks(ctx.loop_dir, ctx.run_state, exclude_milestone_id=None)
    covered = {m for m in (openapi.match(spec, method, path, runtime.get("base_url"))
                          for method, path in other_checks) if m is not None}
    unmatched = [f"{op[0]} {op[1]}" for op in openapi.operations(spec) if op not in covered]
    if not unmatched:
        return
    last_id = ctx.plan["milestones"][-1]["id"]
    ms = (ctx.run_state.get("milestones") or {}).get(last_id)
    if ms is not None:
        ms["status"] = "failed"
        for tid, tstatus in ms.get("tasks", {}).items():
            if tstatus == "achieved":
                ms["tasks"][tid] = "failed"
    raise state.StopRun("stopped-on-failure", "validation-failed",
                        "the completed OpenAPI document names operation(s) that no check ever "
                        "exercised (last safeguard): " + ", ".join(unmatched), milestone_id=last_id)
