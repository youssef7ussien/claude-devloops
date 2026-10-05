"""The `frontend-dev` validator: a restricted Playwright MCP call, checked by the driver.

Research R-10/R-12. The driver starts the backend (if configured) and the frontend, records the UI
URL (D-2), then runs one `validate-ui` call that may use only `Read` and the Playwright MCP tools.
Playwright runs inside Claude, so its evidence cannot be re-executed; instead the driver checks
what it can itself: every criterion has an entry with an observation and existing evidence
(`engine.compute_pass`), the stream shows real Playwright tool use and no denied tool, and every
backend request the page made matches an operation in the frozen API spec (FR-024). Without a
configured backend, any request that reaches for the API fails the contract, so a backend-
dependent criterion can never pass silently (FR-039).
"""
import contextlib
import os
from urllib.parse import urlsplit

from .. import config as config_mod
from .. import inputs, openapi, state
from ..claude import CallFailed
from ..runtime import Runtime, RuntimeStartFailed
from .unit_tests import run as run_unit_tests

PLAYWRIGHT_TOOL_PREFIX = "mcp__playwright__"


class ValidateUIError(CallFailed):
    """The `validate-ui` call itself failed; `reason` is the call's failure reason."""


# --- runtimes --------------------------------------------------------------------------------------

def _start_backend(stack, ctx, ready_timeout):
    """Start `backend.start_command` if configured; return the backend base URL, or None.

    A relative `backend.cwd` is resolved against the target directory. Without a start command,
    `backend.base_url` names a backend that is already running (the driver starts nothing).
    """
    backend = ctx.config.get("backend") or {}
    base_url = config_mod.backend_base_url(ctx.config)
    command = backend.get("start_command")
    if command:
        ready_url = backend.get("ready_url") or backend.get("base_url")
        if not ready_url:
            raise RuntimeStartFailed("backend.start_command is set but neither backend.ready_url "
                                     "nor backend.base_url says where the backend answers")
        cwd = os.path.join(ctx.target_dir, backend.get("cwd") or ".")
        stack.enter_context(Runtime(command, cwd, ready_url, ready_timeout,
                                    log_path=os.path.join(ctx.trial_dir, "backend.log")))
    return base_url


def _record_ui_url(ctx, ui_url):
    """The UI URL is the loop's output (D-2): in `run.json` and `outputs/ui-url.txt`."""
    ctx.run_state["ui_url"] = ui_url
    state.write_text_atomic(os.path.join(ctx.loop_dir, "outputs", "ui-url.txt"), ui_url + "\n")


# --- the validate-ui call --------------------------------------------------------------------------

def _write_mcp_config(ctx):
    command = config_mod.mcp_command(ctx.config)
    if not command:
        raise ValueError("playwright.mcp_command is empty")
    path = os.path.join(ctx.trial_dir, "mcp.json")
    state.write_json_atomic(path, {"mcpServers": {"playwright": {
        "command": command[0],
        "args": command[1:] + ["--output-dir", os.path.abspath(ctx.evidence_dir)],
    }}})
    return path


def _validate_ui(ctx, ui_url, backend_url, spec_path, mcp_path):
    milestone = ctx.milestone
    context = {
        "loop": ctx.loop, "step": "validate-ui", "trial": ctx.trial,
        "workspace": getattr(ctx.workspace, "name", None),
        "ui_url": ui_url,
        "backend": {"base_url": backend_url} if backend_url else None,
        "api_spec_path": spec_path,
        "trial_dir": ctx.trial_dir,
        "evidence_dir": ctx.evidence_dir,
        "milestone": {"id": milestone["id"], "title": milestone["title"], "goal": milestone["goal"],
                      "acceptance_criteria": milestone["acceptance_criteria"]},
    }
    out = ctx.runner.call("validate-ui", context, ctx.target_dir, milestone_id=milestone["id"],
                          trial=ctx.trial, trial_dir=ctx.trial_dir, mcp_config_path=mcp_path,
                          add_dirs=list(ctx.input_dirs or []) + [ctx.evidence_dir,
                                                                 os.path.dirname(spec_path)])
    if not out.ok:
        raise ValidateUIError(out.failure_reason, f"validate-ui failed: {out.failure_detail}",
                              out.failure_class)
    _check_mcp_started(ctx, out)
    return out


def _check_mcp_started(ctx, out):
    """A Playwright MCP server that did not start is a service error: the trial is voided, not
    failed (002 FR-017, spec edge case "visible browser without a display")."""
    server = next((s for s in out.mcp_servers if s.get("name") == "playwright"), None)
    used = any((name or "").startswith(PLAYWRIGHT_TOOL_PREFIX) for name in out.tool_uses)
    # Only a clear "failed" voids the trial. "pending" (still connecting at init) and any other
    # status are left to the normal checks, which fail the criteria if no browser tool ran.
    if server is None or server.get("status") != "failed" or used:
        return
    detail = f"the Playwright MCP server did not start (status {server.get('status')!r})"
    if (ctx.config.get("playwright") or {}).get("headless") is False:
        detail += "; no display available (playwright.headless is false)"
    raise ValidateUIError("service-unavailable", detail, "service")


def _tool_problems(out):
    """Why the call cannot count as a browser test, or [] (R-10 step 3)."""
    problems = []
    if not any((name or "").startswith(PLAYWRIGHT_TOOL_PREFIX) for name in out.tool_uses):
        problems.append("the validate-ui call made no Playwright tool call, so nothing was "
                        "tested in a browser")
    denied = sorted({d.get("tool_name") or "?" for d in
                     (out.result or {}).get("permission_denials") or []})
    if denied:
        problems.append("the validate-ui call attempted disallowed tool(s): " + ", ".join(denied))
    return problems


def _criteria(entries, problems):
    """The model's entries, each failed with the reasons when the call itself is unusable."""
    if not problems:
        return entries
    note = "; ".join(problems)
    return [dict(e, passed=False, observed=f"{note} (reported: {e.get('observed', '')})")
            for e in entries]


# --- the API contract (FR-024) ---------------------------------------------------------------------

# What the page loads from its own server to render itself; anything else it asks that server
# for is an API call, typically through a dev-server proxy (FR-024).
STATIC_EXTENSIONS = {
    ".html", ".htm", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".css", ".map", ".json5",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".avif", ".ico", ".bmp",
    ".woff", ".woff2", ".ttf", ".otf", ".eot", ".mp4", ".webm", ".mp3", ".wav", ".txt",
    ".webmanifest", ".wasm",
}


def _is_under(url, base_url):
    base = base_url.rstrip("/")
    return url == base or url.startswith(base + "/") or url.startswith(base + "?")


def _is_page_or_asset(method, url, ui_url):
    """A UI-origin GET/HEAD of the UI root or of a static file: the app loading itself."""
    if method not in ("GET", "HEAD"):
        return False
    path = urlsplit(url).path.rstrip("/")
    if path == urlsplit(ui_url).path.rstrip("/"):
        return True
    return os.path.splitext(path)[1].lower() in STATIC_EXTENSIONS


def _spec_base_path(spec):
    """The path of the spec's first `servers` URL (e.g. `/api`), or "" if it has none."""
    servers = spec.get("servers") or []
    url = servers[0].get("url") if servers and isinstance(servers[0], dict) else None
    return urlsplit(url).path.rstrip("/") if isinstance(url, str) else ""


def _match_via_ui(spec, method, url, ui_url):
    """Match a proxied call, with or without the spec's server base path (`/api/items`)."""
    matched = openapi.match(spec, method, url, ui_url)
    base = _spec_base_path(spec)
    if matched is None and base:
        matched = openapi.match(spec, method, url, ui_url.rstrip("/") + base)
    return matched


NO_BACKEND = "no backend is configured; set backend.base_url or backend.start_command"


def _contract(spec, network_requests, backend_url, ui_url):
    """Check each backend request against the spec.

    - Under the UI URL, page and asset loads are skipped; every other request is an API call
      through the UI's own server (a proxy) and must match the spec.
    - Under the backend URL, every request must match the spec.
    - Other origins (CDNs, fonts) are not the backend and are skipped.
    Without a backend, an API call nothing could have answered fails (FR-039): a proxied call
    that matches the spec or writes, or a request elsewhere that matches the spec.
    """
    unmatched = []
    for req in network_requests:
        method, url = req["method"].upper(), req["url"]
        if ui_url and _is_under(url, ui_url):
            if _is_page_or_asset(method, url, ui_url):
                continue
            matched = _match_via_ui(spec, method, url, ui_url)
            if backend_url and matched is None:
                unmatched.append(f"{method} {url}")
            elif not backend_url and (matched is not None or method not in ("GET", "HEAD")):
                unmatched.append(f"{method} {url} ({NO_BACKEND})")
        elif backend_url:
            if _is_under(url, backend_url) and openapi.match(spec, method, url, backend_url) is None:
                unmatched.append(f"{method} {url}")
        elif openapi.match(spec, method, url) is not None:
            unmatched.append(f"{method} {url} ({NO_BACKEND})")
    uniq = list(dict.fromkeys(unmatched))
    return {"passed": not uniq, "unmatched_operations": uniq}


def _spec_path(ctx):
    frozen = os.path.join(ctx.loop_dir, "state", inputs.API_SPEC_COPY)
    return frozen if os.path.exists(frozen) or not ctx.api_spec_path else ctx.api_spec_path


# --- the adapter interface ------------------------------------------------------------------------

def validate(ctx):
    runtime = ctx.runtime
    ready_timeout = (ctx.config.get("runtime") or {}).get("ready_timeout_seconds", 120)
    spec_path = _spec_path(ctx)
    spec = openapi.load_spec(spec_path)
    os.makedirs(ctx.evidence_dir, exist_ok=True)
    mcp_path = _write_mcp_config(ctx)
    ui_url = runtime["base_url"]

    with contextlib.ExitStack() as stack:  # always stops both runtimes, in reverse order
        backend_url = _start_backend(stack, ctx, ready_timeout)
        stack.enter_context(Runtime(runtime["start_command"],
                                    os.path.join(ctx.target_dir, runtime.get("cwd") or "."),
                                    runtime["ready_url"], ready_timeout,
                                    log_path=os.path.join(ctx.trial_dir, "runtime.log")))
        _record_ui_url(ctx, ui_url)
        out = _validate_ui(ctx, ui_url, backend_url, spec_path, mcp_path)
        unit_tests = run_unit_tests(ctx.config, (ctx.plan or {}).get("runtime"), ctx.target_dir,
                                    ctx.trial_dir, redactor=ctx.redactor)

    network_requests = out.structured_output["network_requests"]
    return {
        "kind": "playwright", "ui_url": ui_url,
        "criteria": _criteria(out.structured_output["criteria"], _tool_problems(out)),
        "network_requests": network_requests,
        "contract": _contract(spec, network_requests, backend_url, ui_url),
        "unit_tests": unit_tests,
    }
