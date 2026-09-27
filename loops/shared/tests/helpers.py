"""Test harness shared by the suite: temp repo roots, CLI runs, and fake-Claude scenarios."""
import json
import os
import shutil
import subprocess
import sys
import tempfile

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(TESTS_DIR)))
FIXTURES_DIR = os.path.join(TESTS_DIR, "fixtures")

_COPY_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc")


def run_cli(args, env=None, root=None, timeout=120, cwd=None):
    """Run `<root>/bin/devloops args...`; return (exit_code, stdout, stderr)."""
    root = root or REPO_ROOT
    proc = subprocess.run(
        [sys.executable, os.path.join(root, "bin", "devloops"), *args],
        env=env if env is not None else os.environ.copy(),
        cwd=cwd or root,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr


def write_scenario(scenario, env=None, directory=None):
    """Write a fake-Claude scenario file and point `DEVLOOPS_FAKE_SCENARIO` at it.

    `env` is the environment mapping to update (default: `os.environ`). Writing a new scenario
    resets the fake's per-step call counters.
    """
    env = os.environ if env is None else env
    if directory is None:
        directory = tempfile.mkdtemp(prefix="devloops-scenario-")
    path = os.path.join(directory, "scenario.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(scenario, f, indent=2)
    try:
        os.remove(path + ".calls")
    except FileNotFoundError:
        pass
    env["DEVLOOPS_FAKE_SCENARIO"] = path
    return path


class TempEnv:
    """A throwaway repository root for one test.

    Layout under `self.base`:
      repo/            copy (default) or symlinks of the real `loops/` and `bin/`, plus `workspaces/`
      target/          target directory for the loop under test (`self.target_dir`)
      frontend-target/ second target, for tests that run both loops (`self.frontend_target_dir`)
      fake/            fake-Claude scenario and call log

    `self.env` is a copy of `os.environ` wired to the fake Claude binary. Copying is the default
    so that tests which write into `loops/` or `bin/` (boundary audits) cannot touch the real repo.
    """

    def __init__(self, workspace="test-ws", symlink=False):
        self.workspace_name = workspace
        self.symlink = symlink

    def __enter__(self):
        self.base = os.path.realpath(tempfile.mkdtemp(prefix="devloops-test-"))
        self.root = os.path.join(self.base, "repo")
        os.makedirs(os.path.join(self.root, "workspaces"))
        for name in ("loops", "bin"):
            src = os.path.join(REPO_ROOT, name)
            dst = os.path.join(self.root, name)
            if self.symlink:
                os.symlink(src, dst)
            else:
                shutil.copytree(src, dst, symlinks=True, ignore=_COPY_IGNORE)
        self.target_dir = os.path.join(self.base, "target")
        self.frontend_target_dir = os.path.join(self.base, "frontend-target")
        self.fake_dir = os.path.join(self.base, "fake")
        for d in (self.target_dir, self.frontend_target_dir, self.fake_dir):
            os.makedirs(d)
        self.workspace_dir = os.path.join(self.root, "workspaces", self.workspace_name)
        self.fake_log = os.path.join(self.fake_dir, "calls.jsonl")

        self.env = os.environ.copy()
        self.env["DEVLOOPS_CLAUDE_BIN"] = os.path.join(
            self.root, "loops", "shared", "tests", "fake_claude.py"
        )
        self.env["DEVLOOPS_FAKE_LOG"] = self.fake_log
        self.env.pop("DEVLOOPS_FAKE_SCENARIO", None)
        self.env.pop("DEVLOOPS_ALLOWED_ROOTS", None)
        return self

    def __exit__(self, *exc):
        shutil.rmtree(self.base, ignore_errors=True)
        return False

    def write_scenario(self, scenario):
        return write_scenario(scenario, env=self.env, directory=self.fake_dir)

    def run_cli(self, args, timeout=120, extra_env=None):
        env = dict(self.env, **(extra_env or {}))
        return run_cli(args, env=env, root=self.root, timeout=timeout)

    def fake_calls(self):
        """The fake-Claude call log as a list of dicts (empty if no call was made)."""
        try:
            with open(self.fake_log, encoding="utf-8") as f:
                return [json.loads(line) for line in f if line.strip()]
        except FileNotFoundError:
            return []

    def write_file(self, relpath, content, base=None):
        """Write a text file under `base` (default: `self.base`) and return its absolute path."""
        path = os.path.join(base or self.base, relpath)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path
