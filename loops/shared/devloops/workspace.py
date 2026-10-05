"""Workspaces: create or attach, identity, per-loop targets, and the run lock.

FR-035a–d, FR-049–051, FR-065. A workspace is `<project workspaces_dir>/<name>/` with
`workspace.json` (002 FR-012).
"""
import json
import os
import re
import socket
import tempfile

from . import state
from .kit import Kit
from .state import input_error

NAME_RE = re.compile(r"^[a-z0-9-]+$")
LOOPS = ("backend-dev", "frontend-dev")


def _is_within(path, root):
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def _overlaps(a, b):
    return _is_within(a, b) or _is_within(b, a)


def check_target(path, project, kit, workspace_path, other_targets=()):
    """Return the real path of a usable target, or raise `target-unwritable` (002 FR-014).

    A target must not overlap the kit, the project's `.devloops/`, the workspace, or another
    loop's target. Existence and writability are checked by `Workspace.set_target`.
    """
    if not path or not os.path.isabs(path):
        raise input_error("target-unwritable", f"target {path!r} must be an absolute path")
    target = os.path.realpath(path)
    for reserved in kit.reserved:
        if _overlaps(target, reserved):
            raise input_error("target-unwritable",
                              f"target {target} overlaps the reusable loop files ({reserved})")
    if project is not None and _overlaps(target, os.path.realpath(project.dir)):
        raise input_error("target-unwritable",
                          f"target {target} overlaps the project's devloops folder {project.dir}")
    if workspace_path and _overlaps(target, os.path.realpath(workspace_path)):
        raise input_error("target-unwritable",
                          f"target {target} overlaps the workspace {workspace_path}")
    for other, other_path in other_targets:
        if other_path and _overlaps(target, os.path.realpath(other_path)):
            raise input_error("target-unwritable",
                              f"target {target} overlaps the {other} target {other_path}")
    return target


class Workspace:
    def __init__(self, path, project, kit, data):
        self.path = path
        self.project = project
        self.kit = kit
        self.data = data

    @property
    def repo_root(self):
        """Deprecated alias of the project root, for callers not yet converted."""
        return self.project.root

    @property
    def name(self):
        return self.data["name"]

    @property
    def json_path(self):
        return os.path.join(self.path, "workspace.json")

    def loop_dir(self, loop):
        return os.path.join(self.path, loop)

    def save(self):
        state.write_json_atomic(self.json_path, self.data)

    def attach_requirements(self, requirements):
        """Record the requirements identity on first use; afterwards it must match (FR-051).

        `requirements` is `{path, sha256, mode, story_id}`. A different mode or story ID means the
        workspace belongs to another run (`workspace-mismatch`); different bytes are
        `input-changed`.
        """
        recorded = self.data.get("requirements")
        if not recorded:
            self.data["requirements"] = dict(requirements)
            self.save()
            return
        if (recorded.get("mode"), recorded.get("story_id")) != \
                (requirements.get("mode"), requirements.get("story_id")):
            raise input_error(
                "workspace-mismatch",
                f"workspace {self.name!r} was created for mode={recorded.get('mode')} "
                f"story_id={recorded.get('story_id')}, not mode={requirements.get('mode')} "
                f"story_id={requirements.get('story_id')}; use a new workspace")
        if recorded.get("sha256") != requirements.get("sha256"):
            raise input_error(
                "input-changed",
                f"requirements {requirements.get('path')} differ from the ones workspace "
                f"{self.name!r} was created with (sha256 {recorded.get('sha256')})",
                input="requirements")

    def set_target(self, loop, path):
        """Record `loop`'s target directory (FR-035a–d); stop with an input error if unusable."""
        if loop not in LOOPS:
            raise state.UsageError(f"unknown loop {loop!r}")
        targets = self.data.setdefault("targets", {})
        target = check_target(path, self.project, self.kit, self.path,
                              [(other, p) for other, p in targets.items() if other != loop])
        recorded = targets.get(loop)
        if recorded and os.path.realpath(recorded) != target:
            raise input_error("workspace-mismatch",
                              f"workspace {self.name!r} records {recorded} as the {loop} target, "
                              f"not {target}")
        try:
            os.makedirs(target, exist_ok=True)
        except OSError as e:
            raise input_error("target-unwritable",
                              f"target {target} cannot be created: {e.strerror or e}")
        if not os.access(target, os.W_OK | os.X_OK):
            raise input_error("target-unwritable", f"target {target} is not writable")
        if recorded != target:
            targets[loop] = target
            self.save()
        return target


def resolve_path(name_or_path, project):
    """A bare name maps to `<project workspaces_dir>/<name>`; anything with a separator is a path
    (relative to the current directory)."""
    if os.sep in name_or_path or name_or_path.startswith("."):
        path = os.path.abspath(name_or_path)
    else:
        path = os.path.join(project.workspaces_dir, name_or_path)
    name = os.path.basename(os.path.normpath(path))
    if not NAME_RE.match(name):
        raise state.UsageError(f"workspace name {name!r} must match {NAME_RE.pattern}")
    return path, name


def open_workspace(name_or_path, project, kit=None, create=True):
    """Open a workspace, creating `workspace.json` on the first run (D-3).

    A workspace must not overlap the kit, nor lie in the project's `.devloops/` outside its
    workspaces directory.
    """
    kit = kit or Kit.resolve()
    path, name = resolve_path(name_or_path, project)
    real = os.path.realpath(path)
    for reserved in kit.reserved:
        if _overlaps(real, reserved):
            raise state.UsageError(f"workspace {path} must not be inside {reserved}")
    devloops_dir = os.path.realpath(project.dir)
    workspaces_dir = os.path.realpath(project.workspaces_dir)
    in_workspaces_dir = _is_within(real, workspaces_dir) and real != workspaces_dir
    if _overlaps(real, devloops_dir) and not in_workspaces_dir:
        raise state.UsageError(f"workspace {path} must not be inside {devloops_dir} (except in "
                               f"the workspaces folder {project.workspaces_dir})")
    data = state.read_json(os.path.join(path, "workspace.json"))
    if data is None:
        if not create:
            raise state.UsageError(f"workspace {path} does not exist")
        data = {"name": name, "created_at": state.now_iso(), "requirements": None,
                "targets": {}, "config_path": None}
        ws = Workspace(path, project, kit, data)
        ws.save()
        return ws
    if data.get("name") != name:
        raise input_error("workspace-mismatch",
                          f"{path}/workspace.json names workspace {data.get('name')!r}, not {name!r}")
    return Workspace(path, project, kit, data)


# --- Lock (FR-065) -------------------------------------------------------------------------------

def _lock_path(loop_dir):
    return os.path.join(loop_dir, "state", "lock")


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _try_create_lock(path, info):
    """Atomically create the lock with its content in place: write a temp file, then hard-link it.

    `os.link` fails if the lock already exists, so two drivers can never both succeed.
    """
    directory = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".lock.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(info, f)
            f.flush()
            os.fsync(f.fileno())
        os.link(tmp, path)
        return True
    except FileExistsError:
        return False
    finally:
        os.remove(tmp)


def acquire_lock(loop_dir, force_unlock=False):
    """Take `state/lock` as `{pid, host, started_at}`; raise `LockHeld` (exit 40) if held.

    A lock whose process is dead on this host is stale: it is reported (exit 40) unless
    `force_unlock` is set, which removes it and records a `lock-cleared` event. A lock held from
    another host cannot be checked and counts as live.
    """
    path = _lock_path(loop_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    info = {"pid": os.getpid(), "host": socket.gethostname(), "started_at": state.now_iso()}
    for _ in range(3):
        if _try_create_lock(path, info):
            return info
        held = state.read_json(path, default=None)
        if held is None:
            continue  # released between our attempt and the read
        pid, host, started = held.get("pid"), held.get("host"), held.get("started_at")
        live = host != info["host"] or (isinstance(pid, int) and _pid_alive(pid))
        if live:
            raise state.LockHeld(f"another driver is running on {loop_dir}: pid {pid} on {host}, "
                                 f"started {started}")
        if not force_unlock:
            raise state.LockHeld(f"stale lock on {loop_dir}: pid {pid} on {host} (started "
                                 f"{started}) is no longer running; re-run with --force-unlock")
        os.remove(path)
        state.record_event(loop_dir, "lock-cleared",
                           f"stale lock of pid {pid} on {host} (started {started}) removed by "
                           "--force-unlock")
        force_unlock = False
    raise state.LockHeld(f"could not acquire the lock on {loop_dir}")


def release_lock(loop_dir):
    """Remove the lock if this process holds it."""
    path = _lock_path(loop_dir)
    held = state.read_json(path, default=None)
    if held and held.get("pid") == os.getpid() and held.get("host") == socket.gethostname():
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


class locked:
    """`with locked(loop_dir, force_unlock):` holds the lock and always releases it."""

    def __init__(self, loop_dir, force_unlock=False):
        self.loop_dir = loop_dir
        self.force_unlock = force_unlock

    def __enter__(self):
        return acquire_lock(self.loop_dir, self.force_unlock)

    def __exit__(self, *exc):
        release_lock(self.loop_dir)
        return False
