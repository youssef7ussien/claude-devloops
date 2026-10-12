"""Required-tool checks before planning and on every start (FR-013b, research R-22)."""
import json
import os
import re
import shutil
import subprocess

from .config import mcp_command
from .project import DIRNAME, LOCAL_NAME
from .state import input_error

VERSION_TIMEOUT_SECONDS = 30
# The oldest Claude Code the loops are known to work with (002 A-5, research P-14).
MIN_CLAUDE_VERSION = (2, 1, 283)


def parse_version(text):
    """The first `X.Y.Z` in `text` as a tuple of ints, or None."""
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(part) for part in match.groups()) if match else None


def claude_bin(env=None):
    env = os.environ if env is None else env
    return env.get("DEVLOOPS_CLAUDE_BIN") or "claude"


# The browser the Playwright MCP server starts by default: the Chrome channel.
BROWSER_NAMES = ("google-chrome", "google-chrome-stable", "chrome")
_MAC_CHROME = "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
BROWSER_PATHS = ("/opt/google/chrome/chrome", "/" + _MAC_CHROME,
                 os.path.join(os.path.expanduser("~"), _MAC_CHROME))  # installed for one user
# Chromium is not that channel, but works when named in playwright.executable_path.
CHROMIUM_NAMES = ("chromium", "chromium-browser")
CHROMIUM_PATHS = ("/snap/bin/chromium", "/Applications/Chromium.app/Contents/MacOS/Chromium")
CHROME_FIX = "run `npx playwright install chrome`, or set playwright.executable_path"


def _executable(path):
    return os.path.isfile(path) and os.access(path, os.X_OK)


def _first(names, paths, env):
    for name in names:
        found = shutil.which(name, path=env.get("PATH", os.defpath))
        if found:
            return found
    return next((p for p in paths if _executable(p)), None)


def find_chromium(env=None, paths=CHROMIUM_PATHS):
    """An installed Chromium, or None."""
    return _first(CHROMIUM_NAMES, paths, dict(os.environ if env is None else env))


def chromium_fix(path):
    """How to use the Chromium at `path`: the line for the developer's own local file."""
    line = json.dumps({"config": {"playwright": {"executable_path": path}}})
    return f"add {line} to {os.path.join(DIRNAME, LOCAL_NAME)}"


def browser_status(config, env=None, browser_paths=BROWSER_PATHS, chromium_paths=CHROMIUM_PATHS):
    """`(status, detail, fix)` of the browser the frontend loop validates in, `status` one of
    `ready`, `missing`, `not-checked` (an explicit `playwright.mcp_command` chooses its own)."""
    env = dict(os.environ if env is None else env)
    playwright = config.get("playwright") or {}
    if playwright.get("mcp_command") is not None:
        return ("not-checked", "playwright.mcp_command is set and chooses the browser", None)
    configured = playwright.get("executable_path")
    if configured:
        path = os.path.expanduser(configured)
        if _executable(path):
            return ("ready", path, None)
        return ("missing", f"playwright.executable_path {configured} is not an executable file",
                "fix playwright.executable_path, or remove it to use Chrome")
    found = _first(BROWSER_NAMES, browser_paths, env)
    if found:
        return ("ready", found, None)
    chromium = find_chromium(env, chromium_paths)
    if chromium:
        return ("missing", f"no Chrome-channel browser found; Chromium is at {chromium}",
                chromium_fix(chromium))
    return ("missing", "no Chrome-channel browser found", CHROME_FIX)


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


def check_tools(loop_def, config, env=None, browser_paths=BROWSER_PATHS,
                chromium_paths=CHROMIUM_PATHS):
    """Raise `stopped-on-input-error` / `missing-tool`, naming the first missing tool.

    Always checks the Claude Code CLI, whether or not `"claude"` is listed in `required_tools`
    (listing it is a no-op, so `loop.json` can name it for documentation). `required_tools` may
    also add `"curl"` or `"playwright-mcp"` (the first element of `playwright.mcp_command` must
    be on PATH, and the browser it starts must be installed: `browser_status`); any other name
    must be an executable on PATH.
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
            command = (mcp_command(config) or [None])[0]
            if not command or not shutil.which(command, path=env.get("PATH", os.defpath)):
                raise input_error("missing-tool",
                                  f"Playwright MCP server not available: {command!r} is not on "
                                  "PATH (config playwright.mcp_command, or npx for the default)", tool="playwright-mcp")
            status, detail, fix = browser_status(config, env, browser_paths, chromium_paths)
            if status == "missing":  # the browser it validates in (spec 002 FR-018a)
                raise input_error("missing-tool", f"browser not available: {detail}; to fix, {fix}",
                                  tool="browser")
        elif not shutil.which(tool, path=env.get("PATH", os.defpath)):
            raise input_error("missing-tool", f"required tool {tool!r} is not on PATH", tool=tool)
