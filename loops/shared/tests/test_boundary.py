import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import helpers  # noqa: F401
from devloops import boundary


def git(cwd, *args):
    subprocess.run(["git", "-C", cwd, *args], check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


def write(path, content="x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


class BoundaryTest(unittest.TestCase):
    """A loop repository (a git repo) with the workspace inside it, and an outside target."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = os.path.realpath(self.tmp.name)
        self.repo = os.path.join(base, "repo")
        self.loop_dir = os.path.join(self.repo, "workspaces", "ws", "backend-dev")
        self.target = os.path.join(base, "target")
        write(os.path.join(self.repo, "loops", "shared", "a.py"))
        write(os.path.join(self.repo, "bin", "devloops"))
        write(os.path.join(self.loop_dir, "state", "run.json"), "{}")
        write(os.path.join(self.repo, "README.md"))
        write(os.path.join(self.repo, ".gitignore"), "__pycache__/\n")  # as in the real repo
        os.makedirs(self.target)
        self.has_git = shutil.which("git") is not None
        if self.has_git:
            git(self.repo, "init", "-q")
            git(self.repo, "add", "-A")
            git(self.repo, "commit", "-q", "-m", "init")

    def tearDown(self):
        self.tmp.cleanup()

    def snap(self, targets=None):
        return boundary.snapshot(self.repo, self.loop_dir, targets or [self.target])

    def audit(self, change, allowed_extra=(), targets=None):
        before = self.snap(targets)
        change()
        return boundary.diff(before, self.snap(targets), [self.target], allowed_extra)

    def test_changes_in_the_target_are_allowed(self):
        self.assertEqual(self.audit(lambda: write(os.path.join(self.target, "app.py"))), [])

    def test_manifest_catches_loops_bin_and_state(self):
        paths = [os.path.join(self.repo, "loops", "shared", "a.py"),
                 os.path.join(self.repo, "bin", "new"),
                 os.path.join(self.loop_dir, "state", "run.json")]

        def change():
            for p in paths:
                write(p, "changed")
        self.assertEqual(self.audit(change), sorted(paths))

    def test_deleted_file_is_reported(self):
        path = os.path.join(self.repo, "loops", "shared", "a.py")
        self.assertEqual(self.audit(lambda: os.remove(path)), [path])

    def test_pycache_is_ignored(self):
        self.assertEqual(self.audit(lambda: write(os.path.join(
            self.repo, "loops", "shared", "__pycache__", "a.cpython.pyc"))), [])

    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_git_catches_writes_elsewhere_in_the_repo(self):
        readme = os.path.join(self.repo, "README.md")
        new = os.path.join(self.repo, "other-ws", "x.txt")

        def change():
            write(readme, "edited")
            write(new)
        self.assertEqual(self.audit(change), sorted([readme, new]))

    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_second_edit_of_a_dirty_file_is_seen(self):
        readme = os.path.join(self.repo, "README.md")
        write(readme, "dirty before the call")
        self.assertEqual(self.audit(lambda: write(readme, "edited again")), [readme])

    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_target_inside_a_git_repo(self):
        app_repo = os.path.join(os.path.dirname(self.target), "app")
        target = os.path.join(app_repo, "backend")
        write(os.path.join(app_repo, "shared.txt"))
        os.makedirs(target)
        git(app_repo, "init", "-q")
        git(app_repo, "add", "-A")
        git(app_repo, "commit", "-q", "-m", "init")
        before = self.snap([target])
        self.assertIn(app_repo, before["git"])
        write(os.path.join(target, "ok.py"))
        write(os.path.join(app_repo, "shared.txt"), "changed")
        after = self.snap([target])
        self.assertEqual(boundary.diff(before, after, [target]),
                         [os.path.join(app_repo, "shared.txt")])

    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_allowed_extra_relative_and_absolute(self):
        cache = os.path.join(self.repo, ".cache", "tool", "c.bin")
        abs_extra = os.path.join(self.repo, "tmp-extra")

        def change():
            write(cache)
            write(os.path.join(abs_extra, "f"))
        self.assertEqual(self.audit(change, allowed_extra=[".cache", abs_extra]), [])

    def test_outside_audited_repos_is_out_of_scope(self):
        elsewhere = os.path.join(os.path.dirname(self.target), "not-audited", "f")
        self.assertEqual(self.audit(lambda: write(elsewhere)), [])

    def test_git_unavailable_is_recorded(self):
        with mock.patch("devloops.boundary.shutil.which", return_value=None):
            snap = self.snap()
        self.assertTrue(snap["git_unavailable"])
        self.assertEqual(snap["git"], {})
        self.assertIn(os.path.join(self.repo, "loops", "shared", "a.py"), snap["manifest"])

    def test_nothing_is_reverted(self):
        path = os.path.join(self.repo, "loops", "shared", "a.py")
        self.audit(lambda: write(path, "changed"))
        with open(path) as f:
            self.assertEqual(f.read(), "changed")


if __name__ == "__main__":
    unittest.main()
