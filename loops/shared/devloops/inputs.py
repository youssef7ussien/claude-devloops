"""Input checks and byte-level fingerprints (FR-009, FR-012, FR-013, FR-051a).

The requirements mode is `prd` (the whole file), `story-file` (the file is one story), or
`prd-story` (one story, selected by ID, within a PRD; FR-010, D-6).
"""
import hashlib
import os
import re
import shutil

from . import openapi
from .state import UsageError, input_error

API_SPEC_COPY = "api-spec.json"  # under the loop's state/: the frozen copy validation uses

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


def story_selection(story_id=None, story_file=False):
    """Return `(mode, story_id)` for the story options; a usage error if they are unusable.

    An empty or blank `story_id` (for example from an unset shell variable) is refused rather
    than read as "no story", which would plan the whole PRD.
    """
    if story_id is not None and not story_id.strip():
        raise UsageError("--story-id is empty; pass the story's identifier")
    if story_id is not None and story_file:
        raise UsageError("--story-id and --story-file are mutually exclusive")
    if story_id is not None:
        return "prd-story", story_id
    return ("story-file" if story_file else "prd"), None


def _occurs_as_id(story_id, text):
    """Whether `story_id` occurs with no ID character touching it, so `US-1` is not found in
    `US-10`. Markdown and punctuation around it (`**US-1**`, `(US-1)`, `US-1:`) still match."""
    return re.search(rf"(?<![A-Za-z0-9_-]){re.escape(story_id)}(?![A-Za-z0-9_-])", text) \
        is not None


def requirements_input(path, story_id=None, story_file=False):
    """Check the requirements and return `{path, sha256, mode, story_id}` (FR-009, FR-010).

    With `story_id`, the ID must occur literally (case-sensitive) in the file text as a whole ID,
    or the result is `story-not-found` naming it (FR-010b). Understanding the story is left to
    the plan step.
    """
    mode, story_id = story_selection(story_id, story_file)
    path = check_requirements(path)
    if story_id is not None:
        with open(path, "rb") as f:
            text = f.read().decode("utf-8", errors="replace")
        if not _occurs_as_id(story_id, text):
            raise input_error("story-not-found", f"story {story_id!r} does not occur in the "
                              f"requirements file {path} (the match is literal, case-sensitive, "
                              "and of the whole ID)", input="requirements")
    return {"path": path, "sha256": sha256_file(path), "mode": mode, "story_id": story_id}


def check_api_spec(path, loop):
    """Return `{path, sha256}` for a parseable OpenAPI 3 document (FR-011, FR-013a).

    No path is `missing-input`; an unreadable file is `missing-input` and anything that is not an
    OpenAPI 3 JSON document is `invalid-api-spec` (both from `openapi.load_spec`).
    """
    if not path:
        raise input_error("missing-input", f"{loop} requires --api-spec (the backend's OpenAPI "
                          "document)", input="api-spec")
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise input_error("missing-input", f"API spec {path} does not exist", input="api-spec")
    openapi.load_spec(path)
    return {"path": path, "sha256": sha256_file(path)}


def freeze_api_spec(api_spec, state_dir):
    """Copy the recorded API spec to `state/api-spec.json` and return the copy's path.

    Call only after the fingerprints matched, so the copy is byte-identical to what was recorded.
    """
    dest = os.path.join(state_dir, API_SPEC_COPY)
    os.makedirs(state_dir, exist_ok=True)
    tmp = dest + ".tmp"
    shutil.copyfile(api_spec["path"], tmp)
    os.replace(tmp, dest)
    return dest


def _hash_or_none(path):
    if not path:
        return None
    try:
        return sha256_file(path)
    except OSError:
        return None


def recorded_answers_sha256(run_state):
    """The answers hash to compare: the latest grant's, else the approval's, else None (T055).

    A `retry` after a `needs-input` stop records the answered file with its grant, so that grant,
    not the older approval, is what later starts must match.
    """
    for grant in reversed(run_state.get("grants") or []):
        if grant.get("answers_sha256"):
            return grant["answers_sha256"]
    return (run_state.get("approval") or {}).get("answers_sha256")


def recorded_fingerprints(run_state):
    """The fingerprints recorded in `run.json`. Answers count only once an approval or grant
    recorded them."""
    inputs = run_state.get("inputs") or {}
    return {
        "requirements": (inputs.get("requirements") or {}).get("sha256"),
        "api-spec": (inputs.get("api_spec") or {}).get("sha256"),
        "answers": recorded_answers_sha256(run_state),
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
