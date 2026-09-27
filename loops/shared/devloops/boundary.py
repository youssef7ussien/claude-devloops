"""Write-boundary audit around each Claude call (FR-035b, research R-11 and R-23).

A snapshot holds a sha256 manifest of `loops/`, `bin/`, and the loop's `state/` directory, plus
the `git status` of every git repository that contains the loop repository, a target, or the
workspace (with the content hash of each dirty file, so a second edit to an already-dirty file is
seen). `diff` reports changed paths outside the allowed roots. Nothing is ever reverted.

Out of scope by design (R-23): anything outside the audited repositories, such as tool caches
under the home directory and system temporary directories, and files git ignores.
"""
import hashlib
import os
import shutil
import subprocess


def _sha256(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def _manifest(roots):
    manifest = {}
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for name in filenames:
                if name.endswith(".pyc"):
                    continue
                path = os.path.join(dirpath, name)
                manifest[path] = "link:" + os.readlink(path) if os.path.islink(path) else _sha256(path)
    return manifest


def _existing_dir(path):
    path = os.path.abspath(path)
    while not os.path.isdir(path):
        parent = os.path.dirname(path)
        if parent == path:
            return None
        path = parent
    return path


def _git_toplevel(directory):
    start = _existing_dir(directory)
    if start is None:
        return None
    proc = subprocess.run(["git", "-C", start, "rev-parse", "--show-toplevel"],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        return None
    return os.path.realpath(proc.stdout.strip())


def _git_status(toplevel):
    proc = subprocess.run(
        ["git", "-C", toplevel, "status", "--porcelain=v1", "-z", "--untracked-files=all",
         "--no-renames"],
        capture_output=True,
    )
    entries = {}
    if proc.returncode != 0:
        return entries
    for record in proc.stdout.decode("utf-8", "surrogateescape").split("\0"):
        if len(record) < 4:
            continue
        status, rel = record[:2], record[3:]
        path = os.path.join(toplevel, rel)
        entries[path] = {"status": status, "sha256": _sha256(path) if os.path.isfile(path) else None}
    return entries


def snapshot(repo_root, workspace_loop_dir, targets):
    repo_root = os.path.realpath(repo_root)
    workspace_loop_dir = os.path.realpath(workspace_loop_dir)
    snap = {
        "manifest": _manifest([os.path.join(repo_root, "loops"), os.path.join(repo_root, "bin"),
                               os.path.join(workspace_loop_dir, "state")]),
        "git": {},
        "git_unavailable": shutil.which("git") is None,
    }
    if snap["git_unavailable"]:
        return snap
    tops = set()
    for directory in [repo_root, workspace_loop_dir, *targets]:
        top = _git_toplevel(directory)
        if top:
            tops.add(top)
    for top in sorted(tops):
        snap["git"][top] = _git_status(top)
    return snap


def _is_within(path, root):
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def diff(before, after, allowed_roots, allowed_extra=()):
    """Return the sorted changed paths that lie outside `allowed_roots` and `allowed_extra`.

    `allowed_extra` entries are absolute, or relative to the root of each audited git repository.
    """
    roots = [os.path.realpath(r) for r in allowed_roots if r]
    extra_abs = [os.path.realpath(e) for e in allowed_extra if os.path.isabs(e)]
    extra_rel = [e for e in allowed_extra if e and not os.path.isabs(e)]

    def allowed(path, repo_top=None):
        if any(_is_within(path, r) for r in roots + extra_abs):
            return True
        if repo_top and any(_is_within(path, os.path.join(repo_top, e)) for e in extra_rel):
            return True
        return False

    changed = set()
    m_before, m_after = before.get("manifest", {}), after.get("manifest", {})
    for path in m_before.keys() | m_after.keys():
        if m_before.get(path) != m_after.get(path) and not allowed(path):
            changed.add(path)
    g_before, g_after = before.get("git", {}), after.get("git", {})
    for top in g_before.keys() | g_after.keys():
        s_before, s_after = g_before.get(top, {}), g_after.get(top, {})
        for path in s_before.keys() | s_after.keys():
            if s_before.get(path) != s_after.get(path) and not allowed(path, top):
                changed.add(path)
    return sorted(changed)
