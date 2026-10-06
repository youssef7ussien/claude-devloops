"""Persistent state: atomic JSON writes, JSONL logs, events, and run outcomes.

`state/` is the authoritative record (data-model.md). Every write goes through
`write_json_atomic` or `append_jsonl` and happens before the action it records.
"""
import json
import os
import tempfile
from datetime import datetime, timezone

# Exit codes (contracts/cli.md).
EXIT_CODES = {
    "completed": 0,
    "awaiting-approval": 10,
    "stopped-on-failure": 20,
    "stopped-on-input-error": 30,
    "stopped-on-service-error": 50,
}
EXIT_USAGE = 2
EXIT_LOCK_HELD = 40

TERMINAL_STATUSES = {"completed", "stopped-on-failure", "stopped-on-input-error"}

# data-model.md, "Event".
EVENT_TYPES = {
    "run-started", "input-check", "config-override", "lock-cleared", "plan-stored", "paused",
    "approved", "trial-started", "trial-voided", "task-implemented", "validation-passed",
    "validation-failed", "needs-input", "retry-granted", "service-error", "boundary-violation",
    "milestone-achieved", "git-commit", "stopped", "completed",
}


class DevloopsError(Exception):
    """An error that ends the command with `exit_code`."""

    exit_code = 1

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class UsageError(DevloopsError):
    exit_code = EXIT_USAGE


class LockHeld(DevloopsError):
    exit_code = EXIT_LOCK_HELD


class StopRun(DevloopsError):
    """The run must stop with `status` and a `status_reason` (run-state.schema.json).

    `details` holds the optional reason fields: `milestone_id`, `input`, `tool`.
    """

    def __init__(self, status, code, message, **details):
        super().__init__(message)
        self.status = status
        self.code = code
        self.details = {k: v for k, v in details.items() if v is not None}
        self.exit_code = EXIT_CODES[status]

    def status_reason(self):
        return {"code": self.code, "message": self.message, **self.details}


def input_error(code, message, **details):
    return StopRun("stopped-on-input-error", code, message, **details)


def now_iso():
    """Current UTC time as ISO-8601 with millisecond precision and a `Z` suffix."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def write_json_atomic(path, obj):
    """Write `obj` as JSON: temp file in the same directory, fsync, then os.replace.

    A crash at any point leaves either the old file or the new one, never a partial file.
    """
    write_text_atomic(path, json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def write_text_atomic(path, text, mode=None):
    """Write `text` the same way as `write_json_atomic`.

    The file gets the temp file's mode (0600) unless `mode` is given.
    """
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix="." + os.path.basename(path) + ".",
                               suffix=".tmp")
    try:
        if mode is not None:
            os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except FileNotFoundError:
            pass
        raise
    _fsync_dir(directory)


def _fsync_dir(directory):
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def append_jsonl(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def read_jsonl(path):
    try:
        with open(path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
        return []


def record_event(loop_dir, type, message, milestone=None, trial=None, redactor=None):
    """Append one action item to `<loop_dir>/state/events.jsonl` and return it."""
    if type not in EVENT_TYPES:
        raise ValueError(f"unknown event type: {type!r}")
    if redactor is not None:
        message, _ = redactor.redact(message)
    event = {"at": now_iso(), "loop": os.path.basename(os.path.normpath(loop_dir)), "type": type,
             "message": message}
    if milestone is not None:
        event["milestone"] = milestone
    if trial is not None:
        event["trial"] = trial
    append_jsonl(os.path.join(loop_dir, "state", "events.jsonl"), event)
    return event
