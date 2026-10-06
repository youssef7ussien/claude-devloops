"""`devloops check`: is this environment ready for the loops? (002 FR-018, FR-019, research P-14)

Each item is `{name, status, detail, fix, needed_for}`, with `status` one of `ready`, `missing`,
or `warning`. Inside a project the checks follow its effective configuration (defaults, then
`devloops.json`, then `devloops.local.json`); outside one, the packaged defaults. Nothing is
written. A run's own preflight (001 FR-013b) is separate and unchanged.
"""
import os
import shutil
import subprocess
import sys

from . import config as config_mod
from .preflight import MIN_CLAUDE_VERSION, VERSION_TIMEOUT_SECONDS, claude_bin, parse_version

BACKEND, FRONTEND, ALL = "backend-dev", "frontend-dev", "all"
BROWSER_NAMES = ("google-chrome", "google-chrome-stable", "chrome")
BROWSER_PATHS = ("/opt/google/chrome/chrome",
                 "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
MIN_PYTHON = (3, 10)


def _item(name, status, detail, fix=None, needed_for=(ALL,)):
    return {"name": name, "status": status, "detail": detail,
            "fix": fix if status != "ready" else None, "needed_for": list(needed_for)}


def _which(cmd, env):
    if os.sep in cmd:
        return cmd if os.path.isfile(cmd) and os.access(cmd, os.X_OK) else None
    return shutil.which(cmd, path=env.get("PATH", os.defpath))


def _version_output(argv, env):
    """The first line of `argv`'s output, or None when it cannot run or fails."""
    try:
        proc = subprocess.run(argv, env=env, capture_output=True, text=True,
                              timeout=VERSION_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    lines = (proc.stdout or proc.stderr or "").strip().splitlines()
    return lines[0] if lines else ""


def _python():
    version = sys.version_info[:3]
    text = ".".join(map(str, version))
    if version[:2] >= MIN_PYTHON:
        return _item("python", "ready", text)
    return _item("python", "missing", f"{text} is older than 3.10", "install Python 3.10 or newer")


def _claude(env):
    claude = claude_bin(env)
    path = _which(claude, env)
    output = _version_output([path, "--version"], env) if path else None
    if output is None:
        return _item("claude", "missing", f"'{claude} --version' failed",
                     "install Claude Code (https://docs.claude.com/claude-code)")
    version = parse_version(output)
    minimum = ".".join(map(str, MIN_CLAUDE_VERSION))
    if version is None or version < MIN_CLAUDE_VERSION:
        found = ".".join(map(str, version)) if version else repr(output)
        return _item("claude", "missing", f"{found} is older than {minimum}",
                     f"update Claude Code to {minimum} or newer (claude update)")
    return _item("claude", "ready", ".".join(map(str, version)))


def _curl(env):
    path = _which("curl", env)
    output = _version_output([path, "--version"], env) if path else None
    if output is None:
        return _item("curl", "missing", "'curl --version' failed", "install curl",
                     needed_for=(BACKEND,))
    version = parse_version(output)
    return _item("curl", "ready", ".".join(map(str, version)) if version else output,
                 needed_for=(BACKEND,))


def _playwright_mcp(cfg, env):
    command = (config_mod.mcp_command(cfg) or [None])[0]
    if command and _which(command, env):
        return _item("playwright-mcp", "ready", command, needed_for=(FRONTEND,))
    return _item("playwright-mcp", "missing", f"{command!r} is not on PATH",
                 "install Node.js (it provides npx), or set playwright.mcp_command",
                 needed_for=(FRONTEND,))


def _explicit_mcp(playwright):
    """The explicit `playwright.mcp_command`, or None: when set, it is used exactly as written and
    `headless` and `executable_path` are ignored (config.mcp_command)."""
    command = (playwright or {}).get("mcp_command")
    return list(command) if command is not None else None


def _visible(playwright):
    """Whether these playwright settings open a visible browser window."""
    explicit = _explicit_mcp(playwright)
    if explicit is not None:
        return "--headless" not in explicit
    return (playwright or {}).get("headless", True) is False


def _browser(cfg, env, browser_paths):
    if _explicit_mcp(cfg.get("playwright")) is not None:
        return _item("browser", "ready",
                     "not checked: playwright.mcp_command is set and chooses the browser",
                     needed_for=(FRONTEND,))
    configured = (cfg.get("playwright") or {}).get("executable_path")
    fix = "npx playwright install chrome, or set playwright.executable_path"
    if configured:
        path = os.path.expanduser(configured)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return _item("browser", "ready", path, needed_for=(FRONTEND,))
        return _item("browser", "missing",
                     f"playwright.executable_path {configured} is not an executable file",
                     "fix playwright.executable_path, or remove it to use Chrome",
                     needed_for=(FRONTEND,))
    for name in BROWSER_NAMES:
        found = _which(name, env)
        if found:
            return _item("browser", "ready", found, needed_for=(FRONTEND,))
    for path in browser_paths:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return _item("browser", "ready", path, needed_for=(FRONTEND,))
    return _item("browser", "missing", "no Chrome-channel browser found", fix,
                 needed_for=(FRONTEND,))


def _git(cfg, env):
    needed = bool((cfg.get("git") or {}).get("commit_per_milestone"))
    path = _which("git", env)
    if path:
        return _item("git", "ready", path)
    if not needed:
        return _item("git", "ready", "not on PATH; not needed (git.commit_per_milestone is off)")
    return _item("git", "missing", "not on PATH, and git.commit_per_milestone is on",
                 "install git, or set git.commit_per_milestone to false")


def _display(cfg, env, platform):
    if not _visible(cfg.get("playwright")) or not platform.startswith("linux") or \
            env.get("DISPLAY") or env.get("WAYLAND_DISPLAY"):
        return None
    return _item("display", "warning", "visible browser configured but no display",
                 "set playwright.headless to true, or run under xvfb-run",
                 needed_for=(FRONTEND,))


def _shared_visible_browser(project):
    if project is None:
        return None
    shared = (project.shared_config.get("config") or {}).get("playwright") or {}
    if not shared or not _visible(shared):
        return None
    return _item("shared-visible-browser", "warning",
                 "the shared devloops.json opens a visible browser (playwright settings)",
                 "move it to .devloops/devloops.local.json, so it applies to you only",
                 needed_for=(FRONTEND,))


def effective_config(project, kit):
    """The configuration the checks follow: the project's layers over the packaged defaults."""
    layers = project.run_config_layers() if project is not None else ()
    return config_mod.load_effective(kit.path("shared", "config", "defaults.json"), None, {},
                                     project_layers=layers)


def run_checks(project, kit, env=None, platform=None, browser_paths=BROWSER_PATHS):
    """`{ready, project, items}`: `ready` is false when any item is `missing`."""
    env = dict(os.environ if env is None else env)
    platform = platform or sys.platform
    cfg = effective_config(project, kit)
    items = [_python(), _claude(env), _curl(env), _playwright_mcp(cfg, env),
             _browser(cfg, env, browser_paths), _git(cfg, env), _display(cfg, env, platform),
             _shared_visible_browser(project)]
    items = [i for i in items if i is not None]
    return {"ready": not any(i["status"] == "missing" for i in items),
            "project": project.root if project is not None else None, "items": items}


def print_result(result, out):
    """The text report (contracts/cli.md): one line per item, and its fix under it."""
    for item in result["items"]:
        print(f"  {item['status']:<8} {item['name']:<15} {item['detail']}", file=out)
        if item["fix"]:
            print(f"  {'':<8} fix: {item['fix']}", file=out)
    if result["project"] is None:
        print("  (no project found: checked against the packaged defaults)", file=out)
