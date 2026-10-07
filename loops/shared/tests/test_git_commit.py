"""Optional `git.commit_per_milestone` (T073; spec A-6): off by default, target paths only."""
import os
import subprocess
import sys
import unittest

from stub_loop import StubLoopMixin


class GitCommitTest(StubLoopMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        # An isolated git identity and config, so the developer's global settings (signing,
        # hooks) cannot affect the test.
        gitconfig = self.t.write_file("gitconfig", "[user]\n\tname = Test\n\temail = t@example.com\n"
                                                   "[init]\n\tdefaultBranch = main\n")
        self.git_env = {"GIT_CONFIG_GLOBAL": gitconfig, "GIT_CONFIG_NOSYSTEM": "1"}
        # The repository holds more than the target: an unrelated, already-staged file.
        self.repo = os.path.join(self.t.base, "app-repo")
        self.target = os.path.join(self.repo, "backend")
        os.makedirs(self.target)
        self.git("init", "-q")
        self.t.write_file("notes.txt", "unrelated work in progress\n", base=self.repo)
        self.git("add", "notes.txt")

    def git(self, *args):
        proc = subprocess.run(["git", "-C", self.repo, *args], capture_output=True, text=True,
                              env=dict(os.environ, **self.git_env))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout

    def run_to_completion(self, *config_args, target=None):
        env = self.git_env
        self.assertEqual(self.cli("run", "backend-dev", "--requirements", self.prd, "--target",
                                  target or self.target, *config_args, env=env), 10,
                         self.last_output)
        self.assertEqual(self.cli("approve", "--no-continue",
                                  "backend-dev", env=env), 0, self.last_output)
        self.assertEqual(self.cli("run", "backend-dev", env=env), 0, self.last_output)

    def commits(self):
        out = subprocess.run(["git", "-C", self.repo, "log", "--format=%s", "--reverse"],
                             capture_output=True, text=True, env=dict(os.environ, **self.git_env))
        return out.stdout.split("\n")[:-1] if out.returncode == 0 else []

    def enabled(self):
        return self.config_file({"git": {"commit_per_milestone": True}})

    def test_each_achieved_milestone_commits_only_the_target(self):
        self.run_to_completion("--config", self.enabled())
        self.assertEqual(self.commits(), ["feat(backend-dev): complete M01 List items",
                                          "feat(backend-dev): complete M02 Create items"])
        for rev in ("HEAD~1", "HEAD"):
            files = self.git("show", "--name-only", "--format=", rev).split()
            self.assertEqual(files, ["backend/app.py"], rev)
        # The unrelated staged file is still staged, and was never committed.
        self.assertEqual(self.git("diff", "--cached", "--name-only").split(), ["notes.txt"])
        events = self.events("git-commit")
        self.assertEqual([e["milestone"] for e in events], ["M01", "M02"])
        self.assertIn("feat(backend-dev): complete M01 List items", events[0]["message"])

    def test_off_by_default(self):
        self.run_to_completion()
        self.assertEqual(self.commits(), [])
        self.assertEqual(self.events("git-commit"), [])
        self.assertEqual(sorted(self.git("status", "--porcelain").splitlines()),
                         ["?? backend/", "A  notes.txt"])

    def test_a_target_outside_git_is_skipped_and_the_run_still_completes(self):
        self.run_to_completion("--config", self.enabled(), target=self.t.target_dir)
        self.assertEqual(self.run_state()["status"], "completed")
        messages = [e["message"] for e in self.events("git-commit")]
        self.assertEqual(len(messages), 2)
        self.assertTrue(all("not in a git repository" in m for m in messages), messages)

    def test_a_failed_commit_is_recorded_without_failing_the_milestone(self):
        hooks = os.path.join(self.repo, ".git", "hooks")
        self.t.write_file("pre-commit", "#!/bin/sh\necho refused by hook >&2\nexit 1\n",
                          base=hooks)
        os.chmod(os.path.join(hooks, "pre-commit"), 0o755)
        self.run_to_completion("--config", self.enabled())
        self.assertEqual(self.run_state()["status"], "completed")
        self.assertEqual(self.commits(), [])
        messages = [e["message"] for e in self.events("git-commit")]
        self.assertTrue(messages and all("refused by hook" in m for m in messages), messages)

    def test_git_that_cannot_be_run_is_recorded_without_failing_the_run(self):
        # PATH has python3 (for the fake Claude's shebang) but no git.
        bin_dir = os.path.join(self.t.base, "bin-without-git")
        os.makedirs(bin_dir)
        os.symlink(sys.executable, os.path.join(bin_dir, "python3"))
        self.git_env = dict(self.git_env, PATH=bin_dir)
        self.run_to_completion("--config", self.enabled())
        self.assertEqual(self.run_state()["status"], "completed")
        messages = [e["message"] for e in self.events("git-commit")]
        self.assertEqual(len(messages), 2)
        self.assertTrue(all(m.startswith("failed: git could not be run") for m in messages),
                        messages)


if __name__ == "__main__":
    unittest.main()
