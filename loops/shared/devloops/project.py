"""The project: a directory with `.devloops/devloops.json` (002 FR-008, research P-3, P-4).

`.devloops/devloops.json` (shared, committed) and `.devloops/devloops.local.json` (personal,
git-ignored) share one schema (`project-config.schema.json`); the local file is deep-merged over
the shared one. Relative paths in either file resolve against the project root, the parent of
`.devloops/`. Nothing here requires a path to exist.
"""
import json
import os

from . import schema, state
from .state import DevloopsError

DIRNAME = ".devloops"
CONFIG_NAME = "devloops.json"
LOCAL_NAME = "devloops.local.json"
MANIFEST_NAME = "manifest.json"
DEFAULT_WORKSPACE = "main"
DEFAULT_WORKSPACES_DIR = os.path.join(DIRNAME, "workspaces")
DEFAULT_DASHBOARDS_DIR = os.path.join(DIRNAME, "dashboards")
LOOPS = ("backend-dev", "frontend-dev")


class ProjectConfigError(DevloopsError):
    """An invalid project or local configuration (FR-016): an input error, exit 30."""

    exit_code = state.EXIT_CODES["stopped-on-input-error"]

    def __init__(self, path, errors):
        self.path = path
        self.errors = list(errors)
        super().__init__(f"invalid project configuration {path}:\n"
                         + "\n".join(f"  - {e}" for e in self.errors))


def no_project_message(start):
    return f'no devloops project found from {start}; run "devloops init"'


def find(start=None, env=None):
    """The nearest project at or above `start` (default: the current directory).

    `DEVLOOPS_PROJECT` in `env` (default: `os.environ`) names the root and skips the search.
    Raises `state.UsageError` (exit 2) when there is none.
    """
    env = os.environ if env is None else env
    start = os.path.abspath(start or os.getcwd())
    override = env.get("DEVLOOPS_PROJECT")
    if override:
        root = os.path.abspath(override)
        if not os.path.isfile(os.path.join(root, DIRNAME, CONFIG_NAME)):
            raise state.UsageError(f"DEVLOOPS_PROJECT={override}: no {DIRNAME}/{CONFIG_NAME} "
                                   f'there; run "devloops init"')
        return Project(root)
    directory = start
    while True:
        if os.path.isfile(os.path.join(directory, DIRNAME, CONFIG_NAME)):
            return Project(directory)
        parent = os.path.dirname(directory)
        if parent == directory:
            raise state.UsageError(no_project_message(start))
        directory = parent


def read_config_file(path, required):
    """Read and validate one project configuration file; `{}` when absent and not required."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        if required:
            raise ProjectConfigError(path, ["the file does not exist"])
        return {}
    except OSError as e:
        raise ProjectConfigError(path, [f"cannot be read: {e.strerror or e}"])
    except ValueError as e:
        raise ProjectConfigError(path, [f"not valid JSON: {e}"])
    errors = validate(data)
    if errors:
        raise ProjectConfigError(path, errors)
    return data


def validate(data):
    """Schema errors plus the rules the stdlib validator cannot express (no `oneOf`)."""
    errors = schema.validate(data, "project-config.schema.json")
    if errors or not isinstance(data, dict):
        return errors
    req = data.get("requirements")
    if isinstance(req, dict):
        forms = [k for k in ("path", "speckit_feature") if k in req]
        if len(forms) != 1:
            errors.append("$.requirements: must have exactly one of path, speckit_feature "
                          f"(found {', '.join(forms) or 'neither'})")
        if "story_file" in req and "path" not in req:
            errors.append("$.requirements.story_file: allowed only with requirements.path")
    return errors


def _merge(base, override):
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict) and key != "requirements":
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value  # `requirements` is replaced whole: its forms are exclusive
    return merged


class Project:
    def __init__(self, root):
        self.root = os.path.realpath(root)
        self._shared = self._local = None

    def __repr__(self):
        return f"Project({self.root!r})"

    # --- files ------------------------------------------------------------------------------

    @property
    def dir(self):
        return os.path.join(self.root, DIRNAME)

    @property
    def config_path(self):
        return os.path.join(self.dir, CONFIG_NAME)

    @property
    def local_config_path(self):
        return os.path.join(self.dir, LOCAL_NAME)

    @property
    def manifest_path(self):
        return os.path.join(self.dir, MANIFEST_NAME)

    @property
    def shared_config(self):
        if self._shared is None:
            self._shared = read_config_file(self.config_path, required=True)
        return self._shared

    @property
    def local_config(self):
        if self._local is None:
            self._local = read_config_file(self.local_config_path, required=False)
        return self._local

    @property
    def merged(self):
        """The local file deep-merged over the shared one."""
        return _merge(self.shared_config, self.local_config)

    def manifest(self):
        """The parsed `manifest.json`, or None when absent or unreadable."""
        data = state.read_json(self.manifest_path, default=None) \
            if os.path.exists(self.manifest_path) else None
        return data if isinstance(data, dict) else None

    # --- values -----------------------------------------------------------------------------

    @property
    def default_workspace(self):
        return self.merged.get("workspace") or DEFAULT_WORKSPACE

    @property
    def workspaces_dir(self):
        return self.resolve(self.merged.get("workspaces_dir") or DEFAULT_WORKSPACES_DIR)

    @property
    def dashboards_dir(self):
        return self.resolve(self.merged.get("dashboards_dir") or DEFAULT_DASHBOARDS_DIR)

    @property
    def targets(self):
        """`{loop: absolute path or None}` from the configuration."""
        configured = self.merged.get("targets") or {}
        return {loop: self.resolve(configured[loop]) if configured.get(loop) else None
                for loop in LOOPS}

    @property
    def requirements(self):
        """The configured requirements (`{path, story_file?}` or `{speckit_feature}`), or None.

        A `path` is made absolute; `speckit_feature` is returned as written (`"active"` or a
        project-relative folder).
        """
        req = self.merged.get("requirements")
        if not req:
            return None
        req = dict(req)
        if req.get("path"):
            req["path"] = self.resolve(req["path"])
        return req

    def run_config_layers(self):
        """Run configuration layers 2 and 3 (research P-4): shared `config`, then local `config`."""
        return [self.shared_config.get("config") or {}, self.local_config.get("config") or {}]

    def config_sources(self):
        """`{path: sha256 or None}` of the two project configuration files (drift, research P-5)."""
        from .config import file_sha256
        return {path: file_sha256(path) for path in (self.config_path, self.local_config_path)}

    # --- paths ------------------------------------------------------------------------------

    def resolve(self, path):
        """An absolute path: relative paths resolve against the project root."""
        path = os.path.expanduser(path)
        return os.path.normpath(path if os.path.isabs(path) else os.path.join(self.root, path))

    def contains(self, path):
        path = os.path.realpath(path)
        return path == self.root or path.startswith(self.root.rstrip(os.sep) + os.sep)

    def relative_or_absolute(self, path):
        """Project-relative for a path inside the project (FR-013), else absolute."""
        absolute = os.path.realpath(self.resolve(path))
        if self.contains(absolute):
            return os.path.relpath(absolute, self.root)
        return absolute
