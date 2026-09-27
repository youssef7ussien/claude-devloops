"""Required-tool checks before planning and on every start (FR-013b, research R-22)."""
import os
import shutil
import subprocess

from .state import input_error

VERSION_TIMEOUT_SECONDS = 30


def claude_bin(env=None):
    env = os.environ if env is None else env
    return env.get("DEVLOOPS_CLAUDE_BIN") or "claude"


def _runs(argv, env):
    try:
        proc = subprocess.run(argv, env=env, capture_output=True, timeout=VERSION_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def _resolve(cmd, env):
    """Resolve a bare command name on the environment's PATH; keep explicit paths as they are."""
    if os.sep in cmd:
        return cmd
    return shutil.which(cmd, path=env.get("PATH", os.defpath)) or cmd


def check_tools(loop_def, config, env=None):
    """Raise `stopped-on-input-error` / `missing-tool`, naming the first missing tool.

    Always checks the Claude Code CLI, whether or not `"claude"` is listed in `required_tools`
    (listing it is a no-op, so `loop.json` can name it for documentation). `required_tools` may
    also add `"curl"` or `"playwright-mcp"` (the first element of `playwright.mcp_command` must
    be on PATH); any other name must be an executable on PATH.
    """
    env = dict(os.environ if env is None else env)
    claude = claude_bin(env)
    if not _runs([_resolve(claude, env), "--version"], env):
        raise input_error("missing-tool",
                          f"Claude Code CLI not available: '{claude} --version' failed",
                          tool="claude")
    for tool in loop_def.get("required_tools", []):
        if tool == "claude":
            continue  # already checked above, honoring DEVLOOPS_CLAUDE_BIN
        if tool == "curl":
            if not _runs([_resolve("curl", env), "--version"], env):
                raise input_error("missing-tool", "curl not available: 'curl --version' failed",
                                  tool="curl")
        elif tool == "playwright-mcp":
            command = ((config.get("playwright") or {}).get("mcp_command") or [None])[0]
            if not command or not shutil.which(command, path=env.get("PATH", os.defpath)):
                raise input_error("missing-tool",
                                  f"Playwright MCP server not available: {command!r} is not on "
                                  "PATH (config playwright.mcp_command)", tool="playwright-mcp")
        elif not shutil.which(tool, path=env.get("PATH", os.defpath)):
            raise input_error("missing-tool", f"required tool {tool!r} is not on PATH", tool=tool)
