"""Input checks and byte-level fingerprints (FR-009, FR-012, FR-013, FR-051a).

This module covers the PRD mode; story modes and the API spec are added later (T060, T044).
"""
import hashlib
import os

from .state import input_error

# The order in which inputs are compared; the first difference is reported.
FINGERPRINT_INPUTS = ("requirements", "api-spec", "answers")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_requirements(path):
    """Return the absolute path of a readable, non-blank requirements file; else `missing-input`."""
    if not path:
        raise input_error("missing-input", "no requirements file given (--requirements)",
                          input="requirements")
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise input_error("missing-input", f"requirements file {path} does not exist",
                          input="requirements")
    try:
        with open(path, "rb") as f:
            content = f.read()
    except OSError as e:
        raise input_error("missing-input",
                          f"requirements file {path} cannot be read: {e.strerror or e}",
                          input="requirements")
    if not content.strip():
        raise input_error("missing-input", f"requirements file {path} is empty",
                          input="requirements")
    return path


def _hash_or_none(path):
    if not path:
        return None
    try:
        return sha256_file(path)
    except OSError:
        return None


def recorded_fingerprints(run_state):
    """The fingerprints recorded in `run.json`. Answers count only once an approval recorded them."""
    inputs = run_state.get("inputs") or {}
    approval = run_state.get("approval") or {}
    return {
        "requirements": (inputs.get("requirements") or {}).get("sha256"),
        "api-spec": (inputs.get("api_spec") or {}).get("sha256"),
        "answers": approval.get("answers_sha256"),
    }


def current_fingerprints(run_state):
    """Hash the files at the recorded paths now; a missing file gives None (which differs)."""
    inputs = run_state.get("inputs") or {}
    approval = run_state.get("approval") or {}
    return {
        "requirements": _hash_or_none((inputs.get("requirements") or {}).get("path")),
        "api-spec": _hash_or_none((inputs.get("api_spec") or {}).get("path")),
        "answers": _hash_or_none(approval.get("answers_path")),
    }


def compare_fingerprints(run_state, current, skip=()):
    """Raise `stopped-on-input-error` / `input-changed` naming the first input that differs.

    Only inputs with a recorded fingerprint are compared, minus those in `skip`. This function
    writes nothing; the caller changes only `status` and `status_reason` (FR-051a).
    """
    recorded = recorded_fingerprints(run_state)
    for name in FINGERPRINT_INPUTS:
        if recorded[name] is None or name in skip:
            continue
        if current.get(name) != recorded[name]:
            raise input_error(
                "input-changed",
                f"the {name} input changed since it was recorded (sha256 {recorded[name]}, now "
                f"{current.get(name) or 'missing'}); restore it or start a new workspace",
                input=name)
