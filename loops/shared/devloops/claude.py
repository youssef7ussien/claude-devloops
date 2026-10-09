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
import threading
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field

from . import progress as progress_mod
from . import prompts, schema, state

WRITE_TOOLS = ["Edit", "Write", "MultiEdit", "NotebookEdit"]
READ_ONLY_TOOLS = ["Read", "Glob", "Grep"]
READ_ONLY_DISALLOWED = WRITE_TOOLS + ["Bash"]

# Prompts larger than this go through stdin instead of argv (Linux caps one argument at 128 KiB).
MAX_ARGV_PROMPT_BYTES = 100_000
PIPE_DRAIN_SECONDS = 10  # after a call exits, how long its output may take to drain
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
            "required": ["question", "requirement_refs", "suggested_answer", "suggestion_reason"],
            "properties": {"question": {"type": "string"},
                           "requirement_refs": {"type": "array", "items": {"type": "string"}},
                           "suggested_answer": {"type": "string"},
                           "suggestion_reason": {"type": "string"}}}},
        "files_changed": {"type": "array", "items": {"type": "string"}},
    },
}

# Structured result of validate-ui: the model-supplied part of validation-result.schema.json.
# The network requests are not asked for: the driver reads them from the browser's own network
# log, in the call's tool results (validators/playwright.py).
VALIDATE_UI_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["criteria"],
    "properties": {"criteria": _VR["properties"]["criteria"]},
}

STEPS = {
    "plan": {"schema": "plan.schema.json", "writes": False, "tools": READ_ONLY_TOOLS},
    "replan": {"schema": "plan.schema.json", "writes": False, "tools": READ_ONLY_TOOLS},
    "implement": {"schema": IMPLEMENT_RESULT_SCHEMA, "writes": True, "tools": None},
    "fix": {"schema": IMPLEMENT_RESULT_SCHEMA, "writes": True, "tools": None},
    "author-checks": {"schema": "checks.schema.json", "writes": False, "tools": READ_ONLY_TOOLS},
    "validate-ui": {"schema": VALIDATE_UI_SCHEMA, "writes": False,
                    "tools": ["Read", "mcp__playwright__*"], "keep_stream": True,
                    "keep_tool_results": "mcp__playwright__"},
}
# Every call streams its events (`--output-format stream-json`), so a command can show what
# Claude is doing while it works (progress.py); `keep_stream` also saves the stream in the trial
# folder, as evidence of the browser session.

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
    # [{name, text, is_error}] in stream order, for the tools named by the step's
    # `keep_tool_results` prefix (validate-ui: the browser's); empty for other steps.
    tool_results: list = field(default_factory=list)
    mcp_servers: list = field(default_factory=list)  # stream-json init: [{name, status}]
    snapshot_before: dict = None
    snapshot_after: dict = None


class ClaudeRunner:
    """Runs the headless calls of one loop run.

    `run_state` is the live `run.json` dict; its `invocation_count` is incremented and written
    before every call.
    """

    def __init__(self, kit, loop, loop_dir, config, redactor, run_state, env=None,
                 project_root=None, progress=None):
        self.kit = kit
        self.project_root = project_root  # its .devloops/prompts/ overrides the kit (002 FR-030)
        self.loop = loop
        self.loop_dir = loop_dir
        self.config = config
        self.redactor = redactor
        self.run_state = run_state
        self.env = dict(os.environ if env is None else env)
        self.progress = progress  # a progress.Progress, told about each call and its tools

    # --- paths -----------------------------------------------------------------------------------

    @property
    def state_dir(self):
        return os.path.join(self.loop_dir, "state")

    def _rel(self, path):
        return os.path.relpath(path, self.loop_dir)

    # --- prompt ----------------------------------------------------------------------------------

    def compose_prompt(self, step, context):
        """The prompt of one call, and the source of each of its parts (002 FR-030, FR-031)."""
        parts, used = [f"<!-- step: {step} -->"], []
        for part in (prompts.common_part(), prompts.loop_part(self.loop), prompts.step_part(step)):
            source, text = prompts.resolve(self.kit, self.project_root, part)
            used.append(source)
            parts.append(text.strip())
        parts.append("## Context\n\n```json\n" + json.dumps(context, indent=2, ensure_ascii=False)
                     + "\n```")
        return "\n\n".join(parts) + "\n", used

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
        def hook(name):
            path = self.kit.path("shared", "hooks", name)
            return [{"type": "command",
                     "command": f"{shlex.quote(sys.executable)} {shlex.quote(path)}"}]
        return {"hooks": {"PreToolUse": [
            {"matcher": "|".join(WRITE_TOOLS), "hooks": hook("guard_writes.py")},
            # No killing by name or pattern: it can end this very call (exit 143).
            {"matcher": "Bash", "hooks": hook("guard_processes.py")},
        ]}}

    def model_for(self, step, last_trial=False):
        """The `--model` of a call: `models.fix_last_trial` for a milestone's last allowed fix
        trial, else `models.<step>`, else `model`; None lets Claude Code pick its default."""
        models = self.config.get("models") or {}
        if step == "fix" and last_trial and models.get("fix_last_trial"):
            return models["fix_last_trial"]
        return models.get(step) or self.config.get("model") or None

    def build_argv(self, step, prompt, session_id, settings_path, mcp_config_path=None,
                   add_dirs=(), model=None):
        spec = STEPS[step]
        tools = spec["tools"] if spec["tools"] is not None else list(self.config["implement_tools"])
        argv = [self.env.get("DEVLOOPS_CLAUDE_BIN") or "claude", "-p"]
        if prompt is not None:
            argv.append(prompt)
        argv += ["--session-id", session_id, "--output-format", "stream-json",
                 "--verbose"]  # required by -p with stream-json
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
        if model:
            argv += ["--model", model]
        if self.config.get("max_budget_usd_per_invocation") is not None:
            argv += ["--max-budget-usd", str(self.config["max_budget_usd_per_invocation"])]
        return argv

    # --- the call --------------------------------------------------------------------------------

    def call(self, step, context, target_dir, milestone_id=None, trial=None, trial_dir=None,
             mcp_config_path=None, snapshot=None, add_dirs=(), last_trial=False):
        """Run one step and return a `CallResult`.

        `snapshot`, if given, is a zero-argument function called just before the process starts
        and just after it exits, so the two snapshots bracket only Claude's own activity.
        `add_dirs` are directories Claude may read outside the target (the input files); the
        write guard still confines writes. `last_trial` marks a milestone's last allowed `fix`
        trial, which runs on `models.fix_last_trial` when that is set.
        """
        if step not in STEPS:
            raise ValueError(f"unknown step {step!r}")
        self.run_state["invocation_count"] = self.run_state.get("invocation_count", 0) + 1
        seq = self.run_state["invocation_count"]
        state.write_json_atomic(os.path.join(self.state_dir, "run.json"), self.run_state)

        prompt, prompt_sources = self.compose_prompt(step, context)
        prompt, prompt_redacted = self.redactor.redact(prompt)
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
        model = self.model_for(step, last_trial)
        argv = self.build_argv(step, None if via_stdin else prompt, session_id, settings_path,
                               mcp_config_path, add_dirs, model)
        env = dict(self.env)
        env["DEVLOOPS_ALLOWED_ROOTS"] = os.path.realpath(target_dir) if STEPS[step]["writes"] else ""

        out = CallResult(record={})
        out.snapshot_before = snapshot() if snapshot else None
        if self.progress:
            self.progress.call_started(self.loop, step, milestone_id, trial, model,
                                       progress_mod.log_path(self.loop_dir), target_dir)
        started_at, t0 = state.now_iso(), time.monotonic()
        try:
            stdout, stderr, returncode, timed_out, exited = self._run(
                argv, prompt if via_stdin else None, target_dir, env, self._on_stream_line)
            elapsed_ms = int((exited - t0) * 1000)  # not counting the cleanup after it
            ended_at = state.now_iso()
            out.snapshot_after = snapshot() if snapshot else None

            result, out.tool_uses, out.tool_results = _parse_stream(
                stdout, STEPS[step].get("keep_tool_results"))
            out.mcp_servers = _mcp_servers(stdout)
            if STEPS[step].get("keep_stream") and trial_dir:
                os.makedirs(trial_dir, exist_ok=True)
                with open(os.path.join(trial_dir, "stream.jsonl"), "w", encoding="utf-8") as f:
                    f.write(self.redactor.redact(stdout)[0])
            out.result = result
            self._classify(out, step, result, returncode, stderr, timed_out)
        except BaseException as e:
            # The call never got to its end: say why, so the status line stops too.
            if self.progress:
                self.progress.call_ended(step, time.monotonic() - t0, failure=(
                    "interrupted" if isinstance(e, KeyboardInterrupt)
                    else self.redactor.redact(f"{type(e).__name__}: {e}"[:300])[0]))
            raise
        if self.progress:
            cost = (result or {}).get("total_cost_usd")
            self.progress.call_ended(
                step, elapsed_ms / 1000, cost if isinstance(cost, (int, float)) else None,
                None if out.ok else self.redactor.redact(
                    f"{out.failure_reason}: {out.failure_detail or ''}"[:300])[0],
                sum(out.tool_uses.values()))

        record = self._record(seq, session_id, step, milestone_id, trial, prompt_path, started_at,
                              ended_at, elapsed_ms, result, timed_out, out.failure_class, model)
        conversation, conversation_redacted = self._copy_conversation(
            seq, step, record["session_id"], target_dir, timed_out)
        record.update(conversation, prompt_sources=prompt_sources)
        record, record_redacted = self.redactor.redact_obj(record)
        record["redacted"] = bool(prompt_redacted or record_redacted or conversation_redacted)
        state.append_jsonl(os.path.join(self.state_dir, "invocations.jsonl"), record)
        out.record = record
        return out

    def _copy_conversation(self, seq, step, session_id, cwd, timed_out):
        """Copy the call's Claude Code transcript, redacted, into `state/conversations/` (FR-042).

        Returns the invocation record's conversation fields and whether a secret was replaced.
        A transcript that cannot be found or read is recorded as unavailable; it never fails the
        call.
        """
        source = find_transcript(session_id, cwd, self.env)
        if source is None:
            return {"conversation": "unavailable",
                    "conversation_reason": "interrupted" if timed_out else "not-found"}, False
        try:
            with open(source, encoding="utf-8", errors="replace") as f:
                text = f.read()
            text, redacted = redact_transcript(text, self.redactor)
            path = os.path.join(self.state_dir, "conversations", f"{seq:04d}-{step}.jsonl")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            state.write_text_atomic(path, text)
        except OSError:
            return {"conversation": "unavailable", "conversation_reason": "unreadable"}, False
        return {"conversation": "copied", "conversation_path": self._rel(path)}, redacted

    def _on_stream_line(self, line):
        """Tell the progress reporter about each tool Claude uses, as the stream arrives."""
        if not self.progress or '"tool_use"' not in line:
            return
        try:
            event = json.loads(line)
        except ValueError:
            return
        # Redacted once decoded (a secret's JSON-escaped form may differ from the secret): the
        # tool's input is printed and logged.
        event, _ = self.redactor.redact_obj(event)
        if not isinstance(event, dict) or event.get("type") != "assistant":
            return
        for block in (event.get("message") or {}).get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                self.progress.tool_use(block.get("name") or "?", block.get("input"))

    def _run(self, argv, stdin_text, cwd, env, on_line=None):
        """Run the call; return `(stdout, stderr, returncode, timed_out, exited)`, `exited` being
        the `time.monotonic()` at which the call's process ended (before any cleanup).

        stdout is read line by line as it arrives, each line passed to `on_line`, so progress can
        follow the stream; stderr and stdin are served by their own threads so no pipe fills up.
        """
        proc = subprocess.Popen(argv, cwd=cwd, env=env, text=True, start_new_session=True,
                                stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out_lines, err = [], []

        def read_stdout():
            for line in proc.stdout:
                out_lines.append(line)
                if on_line:
                    try:
                        on_line(line)
                    except Exception:  # noqa: BLE001 - progress is a view; the call goes on
                        pass

        def read_stderr():
            err.append(proc.stderr.read())

        def write_stdin():
            try:
                proc.stdin.write(stdin_text)
                proc.stdin.close()
            except (OSError, ValueError):
                pass  # the process exited without reading it all; its result says why

        threads = [threading.Thread(target=read_stdout, daemon=True),
                   threading.Thread(target=read_stderr, daemon=True)]
        if stdin_text is not None:
            threads.append(threading.Thread(target=write_stdin, daemon=True))
        for t in threads:
            t.start()
        timed_out = False
        try:
            proc.wait(timeout=self.config["invocation_timeout_seconds"])
            exited = time.monotonic()
        except subprocess.TimeoutExpired:
            exited, timed_out = time.monotonic(), True
        except BaseException:
            _stop_group(proc)  # e.g. KeyboardInterrupt: never leave the call running
            _close_pipes(proc)
            raise
        # The call has ended (or timed out): stop it and whatever it left running in its process
        # group (a server started with `&`, a watcher), which would hold the port or the pipes.
        _stop_group(proc)
        for t in threads:
            # A process that left the group and holds the pipes must not hold up the run.
            t.join(timeout=PIPE_DRAIN_SECONDS)
        if not any(t.is_alive() for t in threads):
            _close_pipes(proc)
        return "".join(out_lines), "".join(err), proc.returncode, timed_out, exited

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
                ended_at, elapsed_ms, result, timed_out, failure_class, model=None):
        result = result or {}
        usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}
        return {
            "seq": seq,
            "session_id": result.get("session_id") or session_id,
            "loop": self.loop,
            "step": step,
            "model": model,
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


def claude_config_dir(env=None):
    """Where Claude Code keeps its history: `CLAUDE_CONFIG_DIR`, else `~/.claude`."""
    env = os.environ if env is None else env
    return env.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


def find_transcript(session_id, cwd, env=None):
    """The path of a session's transcript in Claude Code's history, or None (research P-9).

    Claude Code keeps it at `projects/<cwd with each non-alphanumeric character as '-'>/
    <session_id>.jsonl`; long paths are shortened there, so any project folder holding the
    session's file is accepted next.
    """
    if not session_id or os.sep in session_id or not re.fullmatch(r"[A-Za-z0-9-]+", session_id):
        return None
    projects = os.path.join(claude_config_dir(env), "projects")
    name = session_id + ".jsonl"
    for directory in dict.fromkeys(p for p in (cwd, cwd and os.path.realpath(cwd)) if p):
        path = os.path.join(projects, re.sub(r"[^A-Za-z0-9]", "-", directory), name)
        if os.path.isfile(path):
            return path
    try:
        folders = sorted(os.listdir(projects))
    except OSError:
        return None
    for folder in folders:
        path = os.path.join(projects, folder, name)
        if os.path.isfile(path):
            return path
    return None


def redact_transcript(text, redactor):
    """Redact a JSONL transcript line by line; return `(text, changed)`.

    Each line is redacted as text, which keeps it byte-for-byte otherwise. A line that is JSON is
    also redacted value by value, which catches a secret that JSON escaping changed; only then is
    the line re-serialized.
    """
    lines, changed = [], False
    # JSONL lines end at "\n" only: `splitlines` would also split inside a string holding U+2028.
    for line in text.split("\n"):
        body = line.rstrip("\r")
        new, line_changed = redactor.redact(body)
        try:
            obj = json.loads(new)
        except ValueError:
            obj = None
        if obj is not None:
            redacted, obj_changed = redactor.redact_obj(obj)
            if obj_changed:
                new, line_changed = json.dumps(redacted, ensure_ascii=False), True
        lines.append(new + line[len(body):])
        changed = changed or line_changed
    return "\n".join(lines), changed


def _stop_group(proc):
    """Stop the process group of `proc` (the call and what it started): SIGTERM, up to
    KILL_GRACE_SECONDS for it to go, then SIGKILL; `proc` itself is reaped."""
    pgid = proc.pid
    try:
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        proc.wait()
        return  # nothing left of the group
    deadline = time.monotonic() + KILL_GRACE_SECONDS
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            try:
                os.killpg(pgid, 0)
            except (ProcessLookupError, PermissionError):
                return  # the whole group is gone
        time.sleep(0.05)
    try:
        os.killpg(pgid, signal.SIGKILL)  # also children that ignored SIGTERM
    except (ProcessLookupError, PermissionError):
        pass
    proc.wait()


def _close_pipes(proc):
    for stream in (proc.stdin, proc.stdout, proc.stderr):
        try:
            if stream:
                stream.close()
        except (OSError, ValueError):
            pass


def _int_or_none(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _tail(text, limit=500):
    text = (text or "").strip()
    return text if len(text) <= limit else "..." + text[-limit:]


def _mcp_servers(stdout):
    """The `mcp_servers` list (`[{name, status}]`) of a stream-json log's init event, or []."""
    for line in (stdout or "").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("type") == "system" and \
                event.get("subtype") == "init":
            servers = event.get("mcp_servers")
            return [s for s in servers if isinstance(s, dict)] if isinstance(servers, list) else []
    return []


def _parse_stream(stdout, keep_results=None):
    """The final `result` event of a stream-json log, a count of `tool_use` events by name, and
    what each tool whose name starts with `keep_results` returned: `[{name, text, is_error}]`, in
    stream order (the text parts joined; none when `keep_results` is None)."""
    result, tool_uses, tool_results, names = None, Counter(), [], {}
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
                    if keep_results and (block.get("name") or "").startswith(keep_results):
                        names[block.get("id")] = block.get("name")
        elif event.get("type") == "user":
            for block in (event.get("message") or {}).get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_result" \
                        and block.get("tool_use_id") in names:
                    tool_results.append({"name": names[block["tool_use_id"]],
                                         "text": _tool_result_text(block.get("content")),
                                         "is_error": bool(block.get("is_error"))})
        elif event.get("type") == "result":
            result = event
    return result, tool_uses, tool_results


def _tool_result_text(content):
    """A `tool_result` block's content as text: a string, or its `text` parts joined."""
    if isinstance(content, str):
        return content
    return "\n".join(part.get("text") or "" for part in content or []
                     if isinstance(part, dict) and part.get("type") == "text")
