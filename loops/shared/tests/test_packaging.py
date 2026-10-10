"""The installed package (002 FR-001, FR-002; research P-1, P-2). Builds a wheel with `uv` and
installs it into a temporary virtual environment, so it runs only when `uv` is on PATH and
DEVLOOPS_TEST_PACKAGING=1. The build uses a temporary copy of the checkout, which stays clean."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile

import helpers
from devloops import __version__

UV = shutil.which("uv")
ENABLED = UV is not None and os.environ.get("DEVLOOPS_TEST_PACKAGING") == "1"


@unittest.skipUnless(ENABLED, "needs uv on PATH and DEVLOOPS_TEST_PACKAGING=1")
class PackagingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = os.path.realpath(cls.tmp.name)
        source = os.path.join(base, "source")
        os.makedirs(source)
        shutil.copy(os.path.join(helpers.REPO_ROOT, "pyproject.toml"), source)
        shutil.copytree(os.path.join(helpers.REPO_ROOT, "loops"), os.path.join(source, "loops"),
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        dist = os.path.join(base, "dist")
        cls.run_ok([UV, "build", "--wheel", "--out-dir", dist, source])
        [wheel] = [n for n in os.listdir(dist) if n.endswith(".whl")]
        cls.wheel = os.path.join(dist, wheel)
        venv = os.path.join(base, "venv")
        cls.run_ok([UV, "venv", "--quiet", venv])
        cls.run_ok([UV, "pip", "install", "--quiet", "--python",
                    os.path.join(venv, "bin", "python"), cls.wheel])
        cls.devloops = os.path.join(venv, "bin", "devloops")
        cls.base = base

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @staticmethod
    def run_ok(argv, **kwargs):
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=600, **kwargs)
        if proc.returncode != 0:
            raise AssertionError(f"{argv} exited {proc.returncode}:\n{proc.stdout}{proc.stderr}")
        return proc

    def test_the_wheel_holds_the_kit_and_no_tests(self):
        with zipfile.ZipFile(self.wheel) as z:
            names = z.namelist()
        for asset in ("devloops_kit/shared/skills/devloops-run/SKILL.md",
                      "devloops_kit/shared/prompts/common.md",
                      "devloops_kit/shared/hooks/guard_writes.py",
                      "devloops_kit/shared/project/prompts/README.md",
                      "devloops_kit/backend-dev/loop.json",
                      "devloops/cli.py",
                      "devloops/assets/app/scripts.txt",
                      "devloops/assets/app/index.html",
                      "devloops/assets/app/core.js",
                      "devloops/assets/app/vendor/prism-config.js",
                      "devloops/assets/app/vendor/prism/prism-core.min.js",
                      "devloops/assets/app/vendor/prism/LICENSE"):
            self.assertIn(asset, names)
        self.assertFalse([n for n in names if "/tests/" in n or n.startswith("tests/")])
        self.assertFalse([n for n in names if n.startswith("devloops/assets/dashboard.")])

    def test_the_installed_command(self):
        out = self.run_ok([self.devloops, "--version"]).stdout
        self.assertEqual(out.strip(), f"devloops {__version__}")
        self.assertEqual(__version__, "0.2.0")
        project = os.path.join(self.base, "app")
        os.makedirs(project)
        env = {k: v for k, v in os.environ.items() if not k.startswith("DEVLOOPS_")}
        self.run_ok([self.devloops, "init", "--no-prompt"], cwd=project, env=env)
        with open(os.path.join(project, ".claude", "skills", "devloops-run", "SKILL.md")) as f:
            skill = f.read()
        self.assertIn("allowed-tools: Bash(devloops *)", skill)
        self.assertIn("devloops run $ARGUMENTS --json", skill)
        self.assertNotIn("bin/devloops", skill)
        with open(os.path.join(project, ".devloops", "manifest.json")) as f:
            manifest = json.load(f)
        self.assertEqual((manifest["kit_mode"], manifest["command"]), ("installed", "devloops"))


if __name__ == "__main__":
    unittest.main()
