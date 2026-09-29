#!/usr/bin/env python3
"""Fake `claude` binary for the offline test suite (constitution VIII).

Point `DEVLOOPS_CLAUDE_BIN` at this file. It accepts the flags the driver passes to
`claude -p`, finds the step from the prompt's first line (`<!-- step: <name> -->`), and answers
from the scenario JSON named by `$DEVLOOPS_FAKE_SCENARIO`:

    {
      "steps": {
        "plan": {"structured_output": {...}},            # same answer on every call
        "implement": [                                   # answer per call number (1-based);
          {"exit_code": 1, "api_error_status": 429},     # the last entry repeats
          {"structured_output": {...},
           "writes": [{"path": "app.py", "content": "..."},
                      {"path": "/elsewhere/x", "content": "...", "tool": "Bash"}]}
        ]
      }
    }

Answer fields (all optional):
  structured_output   object returned as `structured_output`
  result              text returned as `result`
  writes              [{path, content, tool}]; path is relative to cwd or absolute. `tool` is
                      "Bash" (default: written directly, which only the boundary audit can see) or
                      "Edit"/"Write"/"MultiEdit"/"NotebookEdit" (the PreToolUse hooks from
                      `--settings` run first; exit 2 blocks the write and records a denial)
  tool_uses           tool names emitted as `tool_use` events (stream-json)
  api_error_status    number or null
  is_error            bool (default: false, or true when api_error_status is set)
  subtype             default "success", or "error_during_execution" when is_error
  sleep_seconds       sleep before answering (to exercise timeouts and interruption)
  exit_code           process exit code (default: 1 when is_error, else 0)
  no_result           true: print nothing on stdout (a failure before any result)
  stderr              text written to stderr
  usage               overrides for the four token counters (a counter may be null);
                      `null` omits `usage` entirely
  total_cost_usd, num_turns, duration_ms, permission_denials

Each call is appended to `$DEVLOOPS_FAKE_LOG` (JSONL) with its argv, step, call number, cwd,
session ID, pid, and prompt. Per-step call counters live next to the scenario in `<scenario>.calls`.
"""
import json
import os
import re
import subprocess
import sys
import time
import uuid

VERSION = "2.1.283 (Claude Code)"

VALUE_FLAGS = {
    "--session-id", "--output-format", "--input-format", "--json-schema", "--permission-mode",
    "--settings", "--model", "--max-budget-usd", "--append-system-prompt", "--system-prompt",
    "--fallback-model", "--resume", "-r",
}
# These take one or more values, up to the next argument that starts with "-".
VARIADIC_FLAGS = {
    "--allowedTools", "--allowed-tools", "--disallowedTools", "--disallowed-tools",
    "--mcp-config", "--add-dir",
}
BOOL_FLAGS = {
    "-p", "--print", "--strict-mcp-config", "--verbose", "--no-session-persistence",
    "--include-partial-messages", "-c", "--continue", "--dangerously-skip-permissions",
}
HOOKED_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
STEP_RE = re.compile(r"^\s*<!--\s*step:\s*([A-Za-z0-9_-]+)\s*-->")


def parse_args(argv):
    opts = {}
    positionals = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        name, eq, inline = arg.partition("=")
        if arg.startswith("--") and eq and (name in VALUE_FLAGS or name in VARIADIC_FLAGS):
            opts.setdefault(name, []).append(inline)
            i += 1
        elif arg in VALUE_FLAGS:
            if i + 1 >= len(argv):
                die(f"error: option '{arg}' argument missing")
            opts.setdefault(arg, []).append(argv[i + 1])
            i += 2
        elif arg in VARIADIC_FLAGS:
            values = []
            i += 1
            while i < len(argv) and not argv[i].startswith("-"):
                values.append(argv[i])
                i += 1
            if not values:
                die(f"error: option '{arg}' argument missing")
            opts.setdefault(arg, []).extend(values)
        elif arg in BOOL_FLAGS:
            opts[arg] = True
            i += 1
        elif arg.startswith("-") and arg != "-":
            die(f"error: unknown option '{arg}'")
        else:
            positionals.append(arg)
            i += 1
    return opts, positionals


def die(message, code=1):
    sys.stderr.write(message + "\n")
    sys.exit(code)


def one(opts, *names):
    for name in names:
        if name in opts:
            return opts[name][-1]
    return None


def load_json_arg(value):
    """`--settings`/`--mcp-config` take a file path or inline JSON."""
    if value is None:
        return None
    text = value.strip()
    if not text.startswith("{"):
        with open(value, encoding="utf-8") as f:
            text = f.read()
    return json.loads(text)


def next_call_number(scenario_path, step):
    counter_path = scenario_path + ".calls"
    try:
        with open(counter_path, encoding="utf-8") as f:
            counts = json.load(f)
    except (OSError, ValueError):
        counts = {}
    counts[step] = counts.get(step, 0) + 1
    tmp = counter_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(counts, f)
    os.replace(tmp, counter_path)
    return counts[step]


def pick_answer(scenario, step, call):
    answers = scenario.get("steps", {}).get(step)
    if answers is None:
        return None
    if isinstance(answers, list):
        if not answers:
            return None
        return answers[min(call, len(answers)) - 1]
    return answers


def run_pre_tool_hooks(settings, tool_name, tool_input, session_id, cwd, permission_mode):
    """Return (allowed, reason), running hooks the way Claude Code does (exit 2 blocks)."""
    groups = ((settings or {}).get("hooks") or {}).get("PreToolUse") or []
    payload = json.dumps({
        "session_id": session_id,
        "transcript_path": "",
        "cwd": cwd,
        "permission_mode": permission_mode,
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_use_id": "toolu_" + uuid.uuid4().hex[:24],
    })
    for group in groups:
        matcher = group.get("matcher") or ""
        if matcher and matcher != "*" and not re.fullmatch(matcher, tool_name):
            continue
        for hook in group.get("hooks") or []:
            if hook.get("type") != "command":
                continue
            proc = subprocess.run(
                hook["command"], shell=True, input=payload, capture_output=True, text=True, cwd=cwd,
            )
            if proc.returncode == 2:
                return False, proc.stderr.strip()
    return True, ""


def apply_writes(writes, settings, session_id, cwd, permission_mode):
    denials = []
    for w in writes or []:
        tool = w.get("tool", "Bash")
        path = w["path"] if os.path.isabs(w["path"]) else os.path.join(cwd, w["path"])
        if tool in HOOKED_TOOLS:
            key = "notebook_path" if tool == "NotebookEdit" else "file_path"
            tool_input = {key: path, "content": w.get("content", "")}
            allowed, reason = run_pre_tool_hooks(
                settings, tool, tool_input, session_id, cwd, permission_mode,
            )
            if not allowed:
                denials.append({"tool_name": tool, "tool_use_id": "", "tool_input": tool_input,
                                "reason": reason})
                continue
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(w.get("content", ""))
    return denials


def build_result(answer, session_id, denials):
    api_error_status = answer.get("api_error_status")
    is_error = answer.get("is_error", api_error_status is not None)
    usage = {
        "input_tokens": 1200,
        "output_tokens": 300,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 800,
    }
    result = {
        "type": "result",
        "subtype": answer.get("subtype", "error_during_execution" if is_error else "success"),
        "is_error": is_error,
        "api_error_status": api_error_status,
        "duration_ms": answer.get("duration_ms", 1000),
        "num_turns": answer.get("num_turns", 2),
        "result": answer.get("result", "" if is_error else "done"),
        "session_id": session_id,
        "total_cost_usd": answer.get("total_cost_usd", 0.01),
        "permission_denials": list(answer.get("permission_denials", [])) + denials,
    }
    if "usage" not in answer:
        result["usage"] = usage
    elif answer["usage"] is not None:
        usage.update(answer["usage"])
        result["usage"] = usage
    if "structured_output" in answer:
        result["structured_output"] = answer["structured_output"]
    return result


def emit_stream(result, tool_uses, session_id, cwd, opts):
    def out(event):
        sys.stdout.write(json.dumps(event) + "\n")

    out({"type": "system", "subtype": "init", "session_id": session_id, "cwd": cwd,
         "model": one(opts, "--model") or "fake", "tools": [],
         "permissionMode": one(opts, "--permission-mode") or "default"})
    for name in tool_uses or []:
        tool_use_id = "toolu_" + uuid.uuid4().hex[:24]
        out({"type": "assistant", "session_id": session_id, "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": tool_use_id, "name": name, "input": {}}],
        }})
        out({"type": "user", "session_id": session_id, "message": {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": tool_use_id, "content": "ok"}],
        }})
    out(result)


def main(argv):
    if argv and argv[0] in ("--version", "-v"):
        print(VERSION)
        return 0

    opts, positionals = parse_args(argv)
    if not (opts.get("-p") or opts.get("--print")):
        die("fake_claude: only headless mode (-p) is supported")
    prompt = positionals[0] if positionals else sys.stdin.read()
    session_id = one(opts, "--session-id") or str(uuid.uuid4())
    output_format = one(opts, "--output-format") or "text"
    permission_mode = one(opts, "--permission-mode") or "default"
    cwd = os.getcwd()

    first_line = prompt.splitlines()[0] if prompt else ""
    match = STEP_RE.match(first_line)
    step = match.group(1) if match else None

    scenario_path = os.environ.get("DEVLOOPS_FAKE_SCENARIO")
    scenario = {}
    call = None
    if scenario_path:
        with open(scenario_path, encoding="utf-8") as f:
            scenario = json.load(f)
        if step:
            call = next_call_number(scenario_path, step)

    log_path = os.environ.get("DEVLOOPS_FAKE_LOG")
    if log_path:
        entry = {
            "argv": argv, "step": step, "call": call, "cwd": cwd, "session_id": session_id,
            "pid": os.getpid(),
            "prompt": prompt, "allowed_roots": os.environ.get("DEVLOOPS_ALLOWED_ROOTS"),
            "time": time.time(),
        }
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
            f.flush()
            os.fsync(f.fileno())

    answer = pick_answer(scenario, step, call) if step else None
    json_schema = one(opts, "--json-schema")
    if json_schema and "$schema" in json.loads(json_schema):
        # Like the real CLI (2.1.x), which cannot resolve a draft 2020-12 `$schema` URI.
        answer = {"is_error": True, "exit_code": 1, "no_result": True,
                  "stderr": "Error: --json-schema is not a valid JSON Schema: no schema with key "
                            f"or ref \"{json.loads(json_schema)['$schema']}\""}
    if answer is None:
        answer = {"is_error": True, "exit_code": 1,
                  "result": f"fake_claude: no scenario answer for step {step!r} (call {call})"}

    if answer.get("sleep_seconds"):
        time.sleep(answer["sleep_seconds"])

    settings = load_json_arg(one(opts, "--settings"))
    denials = apply_writes(answer.get("writes"), settings, session_id, cwd, permission_mode)

    if answer.get("stderr"):
        sys.stderr.write(answer["stderr"] + "\n")

    result = build_result(answer, session_id, denials)
    if not answer.get("no_result"):
        if output_format == "stream-json":
            emit_stream(result, answer.get("tool_uses"), session_id, cwd, opts)
        elif output_format == "json":
            sys.stdout.write(json.dumps(result) + "\n")
        else:
            sys.stdout.write(str(result["result"]) + "\n")
    sys.stdout.flush()

    return answer.get("exit_code", 1 if result["is_error"] else 0)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
