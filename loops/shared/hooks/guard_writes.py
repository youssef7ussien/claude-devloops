#!/usr/bin/env python3
"""PreToolUse guard for Edit, Write, MultiEdit, and NotebookEdit (FR-035b, FR-071, research R-11).

Claude Code passes the hook input as JSON on stdin (`session_id`, `transcript_path`, `cwd`,
`permission_mode`, `hook_event_name`, `tool_name`, `tool_input`, `tool_use_id`). The path is
`tool_input.file_path` (Edit, Write, MultiEdit) or `tool_input.notebook_path` (NotebookEdit).

The write is allowed (exit 0) only if the resolved path lies under one of the roots in
`DEVLOOPS_ALLOWED_ROOTS` (separated by `os.pathsep`). Otherwise the reason goes to stderr and the
hook exits 2, which makes Claude Code block the call. It fails closed: unreadable input, an unset
or empty root list, or a missing path all block.
"""
import json
import os
import sys


def is_within(path, root):
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def decide(payload, allowed_roots_value):
    """Return None to allow the write, or the reason to block it."""
    tool_input = payload.get("tool_input") or {}
    raw_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not raw_path:
        return f"devloops guard: no file path in {payload.get('tool_name')} input"
    cwd = payload.get("cwd") or os.getcwd()
    path = os.path.realpath(os.path.join(cwd, os.path.expanduser(raw_path)))
    roots = [os.path.realpath(r) for r in (allowed_roots_value or "").split(os.pathsep) if r]
    if not roots:
        return f"devloops guard: this step may not write files (blocked {path})"
    if any(is_within(path, root) for root in roots):
        return None
    return (f"devloops guard: {path} is outside the allowed directories "
            f"({', '.join(roots)}); write only inside the target directory")


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError as e:
        sys.stderr.write(f"devloops guard: unreadable hook input: {e}\n")
        return 2
    reason = decide(payload, os.environ.get("DEVLOOPS_ALLOWED_ROOTS"))
    if reason is None:
        return 0
    sys.stderr.write(reason + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
