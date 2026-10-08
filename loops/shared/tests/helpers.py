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
SHARED_DIR = os.path.dirname(TESTS_DIR)
FAKE_CLAUDE = os.path.join(TESTS_DIR, "fake_claude.py")

# Tests import the package directly: `import helpers` first, then `from devloops import ...`.
if SHARED_DIR not in sys.path:
    sys.path.insert(0, SHARED_DIR)

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


_FRONTEND_ENGINE = """
import json, os, sys
sys.path.insert(0, os.path.join(os.getcwd(), "loops", "shared"))
from devloops import engine, project, workspace
from devloops.state import DevloopsError
a = json.loads(sys.argv[1])
proj = project.find(os.getcwd(), os.environ)
try:
    ws = workspace.open_workspace(a["workspace"], proj)
    eng = engine.Engine("frontend-dev", ws, engine.Options(
        requirements=a["requirements"], target=a["target"], api_spec=a["api_spec"],
        config_path=a["config"]), project=proj, env=os.environ)
    code = getattr(eng, a["action"])() if a["action"] != "run" else eng.run()
    if eng.message:
        print(eng.message)
except DevloopsError as e:
    print(f"devloops: {e.message}", file=sys.stderr)
    code = e.exit_code
sys.exit(code)
"""


def run_frontend_engine(t, *, workspace, requirements=None, target=None, api_spec=None,
                        config=None, extra_env=None, action="run", timeout=120):
    """Run frontend-dev alone through `engine.Engine`, in a subprocess of the TempEnv `t`
    (003 research R-11): the CLI runs it only after backend-dev, but the loop stays runnable
    alone once its inputs exist (Principle VI). `action` is `run`, `approve`, or `replan`.
    Return `(exit_code, stdout, stderr)` like `run_cli`; stdout has the engine's message."""
    payload = json.dumps({"workspace": workspace, "requirements": requirements,
                          "target": target, "api_spec": api_spec, "config": config,
                          "action": action})
    proc = subprocess.run([sys.executable, "-c", _FRONTEND_ENGINE, payload],
                          env=dict(t.env, **(extra_env or {})), cwd=t.root,
                          capture_output=True, text=True, timeout=timeout)
    return proc.returncode, proc.stdout, proc.stderr


class TempEnv:
    """A throwaway repository root for one test.

    Layout under `self.base`:
      repo/            copy (default) or symlinks of the real `loops/` and `bin/`, plus `workspaces/`
      target/          target directory for the loop under test (`self.target_dir`)
      frontend-target/ second target, for tests that run both loops (`self.frontend_target_dir`)
      fake/            fake-Claude scenario and call log
      claude-config/   `CLAUDE_CONFIG_DIR`, where the fake Claude writes transcripts
      runtime/         `XDG_RUNTIME_DIR`, where a dashboard server records itself

`repo/` is also a devloops project: `.devloops/devloops.json` keeps workspaces at
`repo/workspaces/`, as in this repository (002 research P-17), and sets `questions: ask`.

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
        self.make_project(self.root, {"workspaces_dir": "workspaces"})
        self.workspace_dir = os.path.join(self.root, "workspaces", self.workspace_name)
        self.fake_log = os.path.join(self.fake_dir, "calls.jsonl")

        self.env = os.environ.copy()
        self.env["DEVLOOPS_CLAUDE_BIN"] = os.path.join(
            self.root, "loops", "shared", "tests", "fake_claude.py"
        )
        self.env["DEVLOOPS_FAKE_LOG"] = self.fake_log
        self.env.pop("DEVLOOPS_FAKE_SCENARIO", None)
        self.env.pop("DEVLOOPS_ALLOWED_ROOTS", None)
        self.env.pop("DEVLOOPS_PROJECT", None)
        self.env["CLAUDE_CONFIG_DIR"] = os.path.join(self.base, "claude-config")
        # Where a dashboard server records itself (serve.record_path): this test's own.
        self.env["XDG_RUNTIME_DIR"] = os.path.join(self.base, "runtime")
        return self

    def __exit__(self, *exc):
        shutil.rmtree(self.base, ignore_errors=True)
        return False

    def write_scenario(self, scenario):
        return write_scenario(scenario, env=self.env, directory=self.fake_dir)

    def run_cli(self, args, timeout=120, extra_env=None, cwd=None):
        env = dict(self.env, **(extra_env or {}))
        return run_cli(args, env=env, root=self.root, timeout=timeout, cwd=cwd)

    def make_project(self, path, config=None):
        """Make `path` a devloops project: write `.devloops/devloops.json` (schema_version 1,
        plus `config`'s keys). Return the file's path.

        Most tests drive the plan pause, so the run configuration sets `questions: ask` unless
        `config` gives `questions` (tests of the default pass `accept-suggested`)."""
        data = dict({"schema_version": 1}, **(config or {}))
        data["config"] = dict({"questions": "ask"}, **(data.get("config") or {}))
        file = os.path.join(path, ".devloops", "devloops.json")
        os.makedirs(os.path.dirname(file), exist_ok=True)
        with open(file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return file

    def kit(self):
        """The kit of this temp checkout (`repo/loops`, reserving `repo/loops` and `repo/bin`)."""
        from devloops import kit
        return kit.Kit.from_checkout(self.root)

    def project(self):
        from devloops import project
        return project.Project(self.root)

    @staticmethod
    def read_json(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)

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
