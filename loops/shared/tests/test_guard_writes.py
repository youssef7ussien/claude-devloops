import json
import os
import subprocess
import sys
import tempfile
import unittest

import helpers

GUARD = os.path.join(helpers.SHARED_DIR, "hooks", "guard_writes.py")


class GuardWritesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = os.path.realpath(self.tmp.name)
        self.target = os.path.join(self.base, "target")
        os.makedirs(self.target)

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, tool_input, tool_name="Write", roots=None, cwd=None, raw=None):
        payload = raw if raw is not None else json.dumps({
            "session_id": "s", "transcript_path": "", "cwd": cwd or self.target,
            "permission_mode": "acceptEdits", "hook_event_name": "PreToolUse",
            "tool_name": tool_name, "tool_input": tool_input, "tool_use_id": "t"})
        env = dict(os.environ)
        env.pop("DEVLOOPS_ALLOWED_ROOTS", None)
        if roots is not None:
            env["DEVLOOPS_ALLOWED_ROOTS"] = roots
        proc = subprocess.run([sys.executable, GUARD], input=payload, capture_output=True,
                              text=True, env=env)
        return proc.returncode, proc.stderr

    def test_write_inside_target_is_allowed(self):
        for tool, key in (("Write", "file_path"), ("Edit", "file_path"),
                          ("MultiEdit", "file_path"), ("NotebookEdit", "notebook_path")):
            with self.subTest(tool=tool):
                code, _ = self.run_hook({key: os.path.join(self.target, "src", "a.py")}, tool,
                                        roots=self.target)
                self.assertEqual(code, 0)

    def test_relative_paths_resolve_against_cwd(self):
        self.assertEqual(self.run_hook({"file_path": "a.py"}, roots=self.target)[0], 0)
        code, err = self.run_hook({"file_path": "../escape.py"}, roots=self.target)
        self.assertEqual(code, 2)
        self.assertIn("outside the allowed directories", err)

    def test_write_outside_target_is_blocked(self):
        code, err = self.run_hook({"file_path": os.path.join(self.base, "loops", "x.py")},
                                  roots=self.target)
        self.assertEqual(code, 2)
        self.assertIn(os.path.join(self.base, "loops", "x.py"), err)

    def test_sibling_with_common_prefix_is_blocked(self):
        code, _ = self.run_hook({"file_path": self.target + "-other/a.py"}, roots=self.target)
        self.assertEqual(code, 2)

    def test_symlink_escape_is_blocked(self):
        outside = os.path.join(self.base, "outside")
        os.makedirs(outside)
        os.symlink(outside, os.path.join(self.target, "link"))
        code, _ = self.run_hook({"file_path": os.path.join(self.target, "link", "a.py")},
                                roots=self.target)
        self.assertEqual(code, 2)

    def test_multiple_roots(self):
        other = os.path.join(self.base, "evidence")
        roots = os.pathsep.join([self.target, other])
        self.assertEqual(self.run_hook({"file_path": os.path.join(other, "s.png")}, roots=roots)[0], 0)

    def test_fails_closed(self):
        path = {"file_path": os.path.join(self.target, "a.py")}
        self.assertEqual(self.run_hook(path, roots="")[0], 2)      # read-only step
        self.assertEqual(self.run_hook(path, roots=None)[0], 2)    # variable unset
        self.assertEqual(self.run_hook({}, roots=self.target)[0], 2)  # no path
        self.assertEqual(self.run_hook(None, roots=self.target, raw="not json")[0], 2)


if __name__ == "__main__":
    unittest.main()
