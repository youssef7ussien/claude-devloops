"""Effective configuration: defaults < workspace config.json < CLI flags."""
import copy
import json
import os

from . import schema, state

DEFAULTS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "config", "defaults.json")


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


def load_effective(defaults_path, workspace_config_path, cli_overrides):
    """Merge defaults < workspace `config.json` < CLI overrides, then validate (exit 2 on error)."""
    merged = _read_config_file(defaults_path)
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
                    workspace_config_path=None, redactor=None):
    """Return the effective config for this start and store it in `run_state["effective_config"]`.

    The first run freezes the full merge. Later starts reuse the frozen config (later edits to
    the defaults or workspace `config.json` do not apply); CLI overrides are still applied, stored,
    and recorded as a `config-override` event. The caller persists `run_state`.
    """
    frozen = run_state.get("effective_config")
    if not frozen:
        effective = load_effective(defaults_path, workspace_config_path, cli_overrides)
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
    return effective


def _lookup(config, dotted):
    value = config
    for part in dotted.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return value
