"""Headless Claude Code calls (contracts/claude-invocation.md).

One call per step: compose the prompt, build the argv for the step, run it in its own process
group under a timeout, parse the result, classify any failure (research R-19), and append a
redacted invocation record (invocation-record.schema.json).
"""
import copy
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field

from . import schema, state

WRITE_TOOLS = ["Edit", "Write", "MultiEdit", "NotebookEdit"]
READ_ONLY_TOOLS = ["Read", "Glob", "Grep"]
READ_ONLY_DISALLOWED = WRITE_TOOLS + ["Bash"]

# Prompts larger than this go through stdin instead of argv (Linux caps one argument at 128 KiB).
MAX_ARGV_PROMPT_BYTES = 100_000
KILL_GRACE_SECONDS = 5

_VR = schema.load("validation-result.schema.json")

# Structured result of implement and fix (claude-invocation.md, Steps table).
IMPLEMENT_RESULT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["tasks", "assumptions", "needs_input", "files_changed"],
    "properties": {
        "tasks": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["task_id", "status", "note"],
            "properties": {
                "task_id": {"type": "string"},
                "status": {"enum": ["implemented", "not-implemented"]},
                "note": {"type": "string"},
            }}},
        "assumptions": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["text", "affects"],
            "properties": {"text": {"type": "string"},
                           "affects": {"type": "array", "items": {"type": "string"}}}}},
        "needs_input": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["question", "requirement_refs"],
            "properties": {"question": {"type": "string"},
                           "requirement_refs": {"type": "array", "items": {"type": "string"}}}}},
        "files_changed": {"type": "array", "items": {"type": "string"}},
    },
}

# Structured result of validate-ui: the model-supplied parts of validation-result.schema.json.
VALIDATE_UI_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["criteria", "network_requests"],
    "properties": {
        "criteria": _VR["properties"]["criteria"],
        "network_requests": _VR["properties"]["network_requests"],
    },
}

STEPS = {
    "plan": {"schema": "plan.schema.json", "writes": False, "tools": READ_ONLY_TOOLS},
    "replan": {"schema": "plan.schema.json", "writes": False, "tools": READ_ONLY_TOOLS},
    "implement": {"schema": IMPLEMENT_RESULT_SCHEMA, "writes": True, "tools": None},
    "fix": {"schema": IMPLEMENT_RESULT_SCHEMA, "writes": True, "tools": None},
    "author-checks": {"schema": "checks.schema.json", "writes": False, "tools": READ_ONLY_TOOLS},
    "validate-ui": {"schema": VALIDATE_UI_SCHEMA, "writes": False,
                    "tools": ["Read", "mcp__playwright__*"], "stream": True},
}

# Service-failure classification (research R-19). Checked only when the process exited non-zero
# without producing a result. Order matters: the first matching reason wins.
SERVICE_STDERR_PATTERNS = [
    ("auth-failed", re.compile(
        r"invalid api key|authentication[_ ](error|failed)|not logged in|please run /login|"
        r"oauth token (has )?expired|invalid[_ ]x-api-key|api error:?\s*40[13]\b",
        re.IGNORECASE)),
    ("rate-limited", re.compile(r"rate[_ ]limit(ed)?\b|too many requests|api error:?\s*429\b",
                                re.IGNORECASE)),
    ("service-unavailable", re.compile(
        r"ECONNREFUSED|ECONNRESET|ENOTFOUND|ETIMEDOUT|EAI_AGAIN|ENETUNREACH|EHOSTUNREACH|"
        r"getaddrinfo|socket hang up|network (is )?unreachable|connection (error|refused|reset)|"
        r"unable to connect to api|overloaded_error|service unavailable|api error:?\s*5\d\d\b",
        re.IGNORECASE)),
]


def classify_api_status(status):
    """Map an `api_error_status` to a void reason, or None if it is not a service failure."""
    if status in (401, 403):
        return "auth-failed"
    if status == 429:
        return "rate-limited"
    if isinstance(status, int) and 500 <= status <= 599:
        return "service-unavailable"
    return None


def classify_stderr(stderr):
    for reason, pattern in SERVICE_STDERR_PATTERNS:
        if pattern.search(stderr or ""):
            return reason
    return None


class CallFailed(Exception):
    """A validator's own Claude call failed (or its output broke a rule); the trial fails with
    `reason` (e.g. `timeout`, `invalid-output`, a void reason) instead of a generic driver error.
    `failure_class` is kept for the service-error path (T052)."""

    def __init__(self, reason, detail, failure_class="work"):
        super().__init__(f"{reason}: {detail}")
        self.reason, self.detail, self.failure_class = reason, detail, failure_class


@dataclass
class CallResult:
    record: dict
    result: dict = None             # the parsed `result` object, or None
    structured_output: object = None
    ok: bool = False                # the output can be used (post-conditions 1 and 2)
    failure_class: str = "none"     # none | work | service
    failure_reason: str = None      # timeout | claude-error | invalid-output | a void reason
    failure_detail: str = ""
    tool_uses: Counter = field(default_factory=Counter)
    snapshot_before: dict = None
    snapshot_after: dict = None


class ClaudeRunner:
    """Runs the headless calls of one loop run.

    `run_state` is the live `run.json` dict; its `invocation_count` is incremented and written
    before every call.
    """

    def __init__(self, kit, loop, loop_dir, config, redactor, run_state, env=None):
        self.kit = kit
        self.loop = loop
        self.loop_dir = loop_dir
        self.config = config
        self.redactor = redactor
        self.run_state = run_state
        self.env = dict(os.environ if env is None else env)

    # --- paths -----------------------------------------------------------------------------------

    @property
    def state_dir(self):
        return os.path.join(self.loop_dir, "state")

    def _rel(self, path):
        return os.path.relpath(path, self.loop_dir)

    # --- prompt ----------------------------------------------------------------------------------

    def compose_prompt(self, step, context):
        parts = [f"<!-- step: {step} -->"]
        for path in (self.kit.path("shared", "prompts", "common.md"),
                     self.kit.path(self.loop, "Loop-instructions.md"),
                     self.kit.path("shared", "prompts", "steps", f"{step}.md")):
            with open(path, encoding="utf-8") as f:
                parts.append(f.read().strip())
        parts.append("## Context\n\n```json\n" + json.dumps(context, indent=2, ensure_ascii=False)
                     + "\n```")
        return "\n\n".join(parts) + "\n"

    # --- argv ------------------------------------------------------------------------------------

    def step_schema(self, step):
        spec = STEPS[step]["schema"]
        return schema.load(spec) if isinstance(spec, str) else spec

    def cli_schema(self, step):
        """The step schema as `--json-schema` takes it: without `$schema` and `$id`.

        Claude Code rejects the draft 2020-12 `$schema` URI our schema files declare ("no schema
        with key or ref"). The schemas use no draft-specific keywords, so dropping the markers
        changes nothing; the driver still validates the result against the full schema.
        """
        return {k: v for k, v in self.step_schema(step).items() if k not in ("$schema", "$id")}

    def settings(self):
        guard = self.kit.path("shared", "hooks", "guard_writes.py")
        return {"hooks": {"PreToolUse": [{
            "matcher": "|".join(WRITE_TOOLS),
            "hooks": [{"type": "command",
                       "command": f"{shlex.quote(sys.executable)} {shlex.quote(guard)}"}],
        }]}}

    def build_argv(self, step, prompt, session_id, settings_path, mcp_config_path=None,
                   add_dirs=()):
        spec = STEPS[step]
        stream = spec.get("stream", False)
        tools = spec["tools"] if spec["tools"] is not None else list(self.config["implement_tools"])
        argv = [self.env.get("DEVLOOPS_CLAUDE_BIN") or "claude", "-p"]
        if prompt is not None:
            argv.append(prompt)
        argv += ["--session-id", session_id,
                 "--output-format", "stream-json" if stream else "json"]
        if stream:
            argv.append("--verbose")  # required by -p with stream-json
        argv += ["--json-schema", json.dumps(self.cli_schema(step), separators=(",", ":")),
                 "--allowedTools", *tools]
        if spec["writes"]:
            argv += ["--permission-mode", "acceptEdits"]
        else:
            argv += ["--disallowedTools", *READ_ONLY_DISALLOWED]
        if add_dirs:
            argv += ["--add-dir", *add_dirs]  # read access to inputs outside the target
        argv += ["--settings", settings_path, "--strict-mcp-config"]
        if mcp_config_path:
            argv += ["--mcp-config", mcp_config_path]
        if self.config.get("model"):
            argv += ["--model", self.config["model"]]
        if self.config.get("max_budget_usd_per_invocation") is not None:
            argv += ["--max-budget-usd", str(self.config["max_budget_usd_per_invocation"])]
        return argv

    # --- the call --------------------------------------------------------------------------------

    def call(self, step, context, target_dir, milestone_id=None, trial=None, trial_dir=None,
             mcp_config_path=None, snapshot=None, add_dirs=()):
        """Run one step and return a `CallResult`.

        `snapshot`, if given, is a zero-argument function called just before the process starts
        and just after it exits, so the two snapshots bracket only Claude's own activity.
        `add_dirs` are directories Claude may read outside the target (the input files); the
        write guard still confines writes.
        """
        if step not in STEPS:
            raise ValueError(f"unknown step {step!r}")
        self.run_state["invocation_count"] = self.run_state.get("invocation_count", 0) + 1
        seq = self.run_state["invocation_count"]
        state.write_json_atomic(os.path.join(self.state_dir, "run.json"), self.run_state)

        prompt, prompt_redacted = self.redactor.redact(self.compose_prompt(step, context))
        prompts_dir = os.path.join(self.state_dir, "prompts")
        base = os.path.join(prompts_dir, f"{seq:04d}-{step}")
        prompt_path = base + ".md"
        settings_path = base + ".settings.json"
        os.makedirs(prompts_dir, exist_ok=True)
        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write(prompt)
        state.write_json_atomic(settings_path, self.settings())

        session_id = str(uuid.uuid4())
        via_stdin = len(prompt.encode("utf-8")) > MAX_ARGV_PROMPT_BYTES
        add_dirs = sorted({os.path.realpath(d) for d in add_dirs if d and os.path.isdir(d)})
        argv = self.build_argv(step, None if via_stdin else prompt, session_id, settings_path,
                               mcp_config_path, add_dirs)
        env = dict(self.env)
        env["DEVLOOPS_ALLOWED_ROOTS"] = os.path.realpath(target_dir) if STEPS[step]["writes"] else ""

        out = CallResult(record={})
        out.snapshot_before = snapshot() if snapshot else None
        started_at, t0 = state.now_iso(), time.monotonic()
        stdout, stderr, returncode, timed_out = self._run(argv, prompt if via_stdin else None,
                                                          target_dir, env)
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        ended_at = state.now_iso()
        out.snapshot_after = snapshot() if snapshot else None

        stream = STEPS[step].get("stream", False)
        result, out.tool_uses = _parse_stream(stdout) if stream else (_parse_json(stdout), Counter())
        if stream and trial_dir:
            os.makedirs(trial_dir, exist_ok=True)
            with open(os.path.join(trial_dir, "stream.jsonl"), "w", encoding="utf-8") as f:
                f.write(self.redactor.redact(stdout)[0])
        out.result = result
        self._classify(out, step, result, returncode, stderr, timed_out)

        record = self._record(seq, session_id, step, milestone_id, trial, prompt_path, started_at,
                              ended_at, elapsed_ms, result, timed_out, out.failure_class)
        record, record_redacted = self.redactor.redact_obj(record)
        record["redacted"] = bool(prompt_redacted or record_redacted)
        state.append_jsonl(os.path.join(self.state_dir, "invocations.jsonl"), record)
        out.record = record
        return out

    def _run(self, argv, stdin_text, cwd, env):
        proc = subprocess.Popen(argv, cwd=cwd, env=env, text=True, start_new_session=True,
                                stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        timeout = self.config["invocation_timeout_seconds"]
        try:
            stdout, stderr = proc.communicate(stdin_text, timeout=timeout)
            return stdout, stderr, proc.returncode, False
        except subprocess.TimeoutExpired:
            _kill_group(proc)
            stdout, stderr = proc.communicate()
            return stdout or "", stderr or "", proc.returncode, True
        except BaseException:
            _kill_group(proc)  # e.g. KeyboardInterrupt: never leave the call running
            raise

    def _classify(self, out, step, result, returncode, stderr, timed_out):
        if timed_out:
            out.failure_class, out.failure_reason = "work", "timeout"
            out.failure_detail = (f"no result within invocation_timeout_seconds="
                                  f"{self.config['invocation_timeout_seconds']}")
            return
        api_status = (result or {}).get("api_error_status")
        void = classify_api_status(api_status)
        if void is None and result is None and returncode != 0:
            void = classify_stderr(stderr)
        if void:
            out.failure_class, out.failure_reason = "service", void
            out.failure_detail = (f"api_error_status={api_status}" if api_status is not None
                                  else _tail(stderr))
            return
        if result is None or returncode != 0 or result.get("is_error") or \
                result.get("subtype") != "success":
            out.failure_class, out.failure_reason = "work", "claude-error"
            if result is None:
                out.failure_detail = f"exit code {returncode}, no result: {_tail(stderr)}"
            else:
                out.failure_detail = (f"exit code {returncode}, subtype={result.get('subtype')}, "
                                      f"is_error={result.get('is_error')}: "
                                      f"{_tail(str(result.get('result', '')))}")
            return
        structured = result.get("structured_output")
        errors = (["$: no structured_output"] if structured is None
                  else schema.check(structured, self.step_schema(step)))
        if errors:
            out.failure_class, out.failure_reason = "work", "invalid-output"
            out.failure_detail = "; ".join(errors[:20])
            return
        out.structured_output = copy.deepcopy(structured)
        out.ok = True

    def _record(self, seq, session_id, step, milestone_id, trial, prompt_path, started_at,
                ended_at, elapsed_ms, result, timed_out, failure_class):
        result = result or {}
        usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}
        return {
            "seq": seq,
            "session_id": result.get("session_id") or session_id,
            "loop": self.loop,
            "step": step,
            "milestone_id": milestone_id,
            "trial": trial,
            "prompt_path": self._rel(prompt_path),
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_ms": _int_or_none(result.get("duration_ms", elapsed_ms)),
            "num_turns": _int_or_none(result.get("num_turns")),
            "tokens": {
                "input": _int_or_none(usage.get("input_tokens")),
                "output": _int_or_none(usage.get("output_tokens")),
                "cache_creation": _int_or_none(usage.get("cache_creation_input_tokens")),
                "cache_read": _int_or_none(usage.get("cache_read_input_tokens")),
            },
            "cost_usd": result.get("total_cost_usd") if isinstance(
                result.get("total_cost_usd"), (int, float)) else None,
            "is_error": bool(result.get("is_error", True)) if result else True,
            "subtype": result.get("subtype"),
            "permission_denials": list(result.get("permission_denials") or []),
            "timed_out": timed_out,
            "api_error_status": _int_or_none(result.get("api_error_status")),
            "failure_class": failure_class,
        }


def _kill_group(proc):
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    try:
        proc.wait(timeout=KILL_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)  # also reaps children that ignored SIGTERM
    except (ProcessLookupError, PermissionError):
        pass


def _int_or_none(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _tail(text, limit=500):
    text = (text or "").strip()
    return text if len(text) <= limit else "..." + text[-limit:]


def _parse_json(stdout):
    """The `--output-format json` result object, or None."""
    text = (stdout or "").strip()
    if not text:
        return None
    for candidate in (text, text.splitlines()[-1]):
        try:
            obj = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def _parse_stream(stdout):
    """The final `result` event of a stream-json log, and a count of `tool_use` events by name."""
    result, tool_uses = None, Counter()
    for line in (stdout or "").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "assistant":
            for block in (event.get("message") or {}).get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_uses[block.get("name")] += 1
        elif event.get("type") == "result":
            result = event
    return result, tool_uses
