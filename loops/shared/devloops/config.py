"""Effective configuration (002 research P-4), each layer overriding the one before:
packaged defaults < project `devloops.json` `config` < `devloops.local.json` `config` <
workspace `config.json` / `--config` < CLI flags.
"""
import copy
import hashlib
import json
import os
from urllib.parse import urlsplit

from . import schema, state
from .kit import Kit

DEFAULTS_PATH = Kit.resolve().path("shared", "config", "defaults.json")


class ConfigError(state.UsageError):
    """Invalid configuration (exit 2); `errors` lists every problem."""

    def __init__(self, errors, source="configuration"):
        self.errors = list(errors)
        super().__init__(f"invalid {source}:\n" + "\n".join(f"  - {e}" for e in self.errors))


def deep_merge(base, override):
    """Merge `override` into a copy of `base`. Objects merge recursively; anything else replaces."""
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _drop_unset(overrides):
    """CLI flags that were not given arrive as None; they must not override anything."""
    out = {}
    for key, value in (overrides or {}).items():
        if isinstance(value, dict):
            value = _drop_unset(value)
            if value:
                out[key] = value
        elif value is not None:
            out[key] = value
    return out


def _read_config_file(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except OSError as e:
        raise ConfigError([f"{path}: cannot be read: {e.strerror or e}"])
    except ValueError as e:
        raise ConfigError([f"{path}: not valid JSON: {e}"])
    if not isinstance(data, dict):
        raise ConfigError([f"{path}: must contain a JSON object"])
    return data


def _validated(config):
    errors = schema.validate(config, "config.schema.json")
    if errors:
        raise ConfigError(errors)
    return config


def file_sha256(path):
    """Hex sha256 of a file's bytes, or None when it is missing or unreadable."""
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


def load_effective(defaults_path, workspace_config_path, cli_overrides, project_layers=()):
    """Merge defaults < project layers < workspace `config.json` < CLI overrides, then validate
    (exit 2 on error). `project_layers` are the shared and local `config` blocks, in that order;
    they were validated with the project files."""
    merged = _read_config_file(defaults_path)
    for layer in project_layers:
        merged = deep_merge(merged, layer or {})
    if workspace_config_path is not None:
        merged = deep_merge(merged, _read_config_file(workspace_config_path))
    merged = deep_merge(merged, _drop_unset(cli_overrides))
    return _validated(merged)


def _changed_keys(before, after, prefix=""):
    keys = []
    for key in sorted(before.keys() | after.keys()):
        b, a = before.get(key), after.get(key)
        if isinstance(b, dict) and isinstance(a, dict):
            keys.extend(_changed_keys(b, a, f"{prefix}{key}."))
        elif b != a:
            keys.append(f"{prefix}{key}")
    return keys


def resolve_for_run(run_state, loop_dir, cli_overrides, defaults_path=DEFAULTS_PATH,
                    workspace_config_path=None, redactor=None, project_layers=()):
    """Return the effective config for this start and store it in `run_state["effective_config"]`.

    The first run freezes the full merge. Later starts reuse the frozen config (later edits to
    the defaults or workspace `config.json` do not apply); CLI overrides are still applied, stored,
    and recorded as a `config-override` event. The caller persists `run_state`.
    """
    frozen = run_state.get("effective_config")
    if not frozen:
        effective = load_effective(defaults_path, workspace_config_path, cli_overrides,
                                   project_layers)
        run_state["effective_config"] = effective
        return effective
    effective = _validated(deep_merge(frozen, _drop_unset(cli_overrides)))
    changed = _changed_keys(frozen, effective)
    if changed:
        state.record_event(loop_dir, "config-override",
                           "CLI override of " + ", ".join(
                               f"{k} = {json.dumps(_lookup(effective, k))}" for k in changed),
                           redactor=redactor)
        run_state["effective_config"] = effective
        run_state["config_cli_keys"] = sorted(set(run_state.get("config_cli_keys") or [])
                                              | set(changed))
    return effective


def _lookup(config, dotted):
    value = config
    for part in dotted.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return value


PLAYWRIGHT_MCP = ["npx", "@playwright/mcp@latest"]


def mcp_command(config):
    """The Playwright MCP server command (002 research P-15, FR-017).

    An explicit `playwright.mcp_command` list is used exactly as written (every frozen 001
    configuration has one). Otherwise it is derived: `npx @playwright/mcp@latest`, plus
    `--headless` unless `headless` is false, plus `--executable-path <p>` when one is set (a
    leading `~` is expanded: the command runs without a shell).
    """
    playwright = config.get("playwright") or {}
    if playwright.get("mcp_command") is not None:
        return list(playwright["mcp_command"])
    command = list(PLAYWRIGHT_MCP)
    if playwright.get("headless", True) is not False:
        command.append("--headless")
    if playwright.get("executable_path"):
        command += ["--executable-path", os.path.expanduser(playwright["executable_path"])]
    return command


def dotted_keys(overrides, prefix=""):
    """The dotted keys an override dict sets (unset `None` values left out)."""
    keys = []
    for key, value in _drop_unset(overrides).items():
        if isinstance(value, dict):
            keys.extend(dotted_keys(value, f"{prefix}{key}."))
        else:
            keys.append(f"{prefix}{key}")
    return keys


def config_sources(project, workspace_config_path):
    """sha256 (or None) of each configuration file a run reads (002 research P-5)."""
    return {"devloops.json": file_sha256(project.config_path),
            "devloops.local.json": file_sha256(project.local_config_path),
            "workspace": file_sha256(workspace_config_path) if workspace_config_path else None}


def drift(run_state, project, workspace_config_path, defaults_path=DEFAULTS_PATH):
    """The dotted keys whose value would differ if the run started now (FR-015); nothing is
    applied. Keys the command line set are left out, and so is a run recorded before 002 (no
    `config_sources`) or whose configuration files are byte-identical to the recorded ones."""
    recorded = run_state.get("config_sources")
    frozen = run_state.get("effective_config")
    if not recorded or not frozen or \
            config_sources(project, workspace_config_path) == recorded:
        return []
    try:
        now = load_effective(defaults_path, workspace_config_path, {},
                             project.run_config_layers())
    except state.DevloopsError:
        return []  # an invalid file is reported when it is next read; status stays read-only
    cli = set(run_state.get("config_cli_keys") or [])
    return [k for k in _changed_keys(frozen, now)
            if k not in cli and not any(k.startswith(c + ".") for c in cli)]


def backend_base_url(config):
    """The backend address frontend-dev validates against (FR-039, R-12), or None.

    `backend.base_url` if set; else, with a `backend.start_command`, the origin of
    `backend.ready_url`. None means no backend: backend-dependent criteria must fail.
    """
    backend = config.get("backend") or {}
    if backend.get("base_url"):
        return backend["base_url"]
    if backend.get("start_command") and backend.get("ready_url"):
        parts = urlsplit(backend["ready_url"])
        return f"{parts.scheme}://{parts.netloc}"
    return None
