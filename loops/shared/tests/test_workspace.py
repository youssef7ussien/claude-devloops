import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest

import helpers  # noqa: F401
from devloops import state, workspace


class WorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = os.path.realpath(self.tmp.name)
        self.repo = os.path.join(self.base, "repo")
        for d in ("loops", "bin", "workspaces"):
            os.makedirs(os.path.join(self.repo, d))

    def tearDown(self):
        self.tmp.cleanup()

    def open(self, name="app-1"):
        return workspace.open_workspace(name, self.repo)

    # --- create and attach ---

    def test_bare_name_creates_workspace_json(self):
        ws = self.open()
        self.assertEqual(ws.path, os.path.join(self.repo, "workspaces", "app-1"))
        data = state.read_json(ws.json_path)
        self.assertEqual(set(data), {"name", "created_at", "requirements", "targets", "config_path"})
        self.assertEqual(data["name"], "app-1")

    def test_reopen_keeps_identity(self):
        created = self.open().data["created_at"]
        self.assertEqual(self.open().data["created_at"], created)

    def test_path_form(self):
        ws = workspace.open_workspace(os.path.join(self.base, "elsewhere", "ws-b"), self.repo)
        self.assertEqual(ws.name, "ws-b")

    def test_invalid_name(self):
        for bad in ("App", "a_b", "a b"):
            with self.subTest(name=bad), self.assertRaises(state.UsageError):
                self.open(bad)

    def test_workspace_inside_loops_is_refused(self):
        with self.assertRaises(state.UsageError):
            workspace.open_workspace(os.path.join(self.repo, "loops", "ws"), self.repo)

    def test_requirements_identity(self):
        ws = self.open()
        req = {"path": "/p.md", "sha256": "a" * 64, "mode": "prd", "story_id": None}
        ws.attach_requirements(req)
        ws = self.open()
        ws.attach_requirements(dict(req, path="/moved.md"))  # same bytes, other path: fine
        with self.assertRaises(state.StopRun) as cm:
            ws.attach_requirements(dict(req, sha256="b" * 64))
        self.assertEqual((cm.exception.code, cm.exception.details), ("input-changed",
                                                                      {"input": "requirements"}))
        with self.assertRaises(state.StopRun) as cm:
            ws.attach_requirements(dict(req, mode="prd-story", story_id="US-1"))
        self.assertEqual(cm.exception.code, "workspace-mismatch")

    # --- targets ---

    def test_set_target_creates_and_records(self):
        ws = self.open()
        target = os.path.join(self.base, "apps", "backend")
        self.assertEqual(ws.set_target("backend-dev", target), target)
        self.assertTrue(os.path.isdir(target))
        self.assertEqual(state.read_json(ws.json_path)["targets"], {"backend-dev": target})

    def assert_target_error(self, ws, loop, path, code="target-unwritable"):
        with self.assertRaises(state.StopRun) as cm:
            ws.set_target(loop, path)
        self.assertEqual(cm.exception.status, "stopped-on-input-error")
        self.assertEqual(cm.exception.code, code)

    def test_target_must_be_absolute(self):
        self.assert_target_error(self.open(), "backend-dev", "relative/dir")

    def test_target_must_not_overlap_loops_bin_or_workspace(self):
        ws = self.open()
        self.assert_target_error(ws, "backend-dev", os.path.join(self.repo, "loops", "x"))
        self.assert_target_error(ws, "backend-dev", os.path.join(self.repo, "bin"))
        self.assert_target_error(ws, "backend-dev", self.repo)  # contains loops/
        self.assert_target_error(ws, "backend-dev", os.path.join(ws.path, "code"))

    def test_target_inside_repo_but_outside_loops_is_allowed(self):
        target = os.path.join(self.repo, "apps", "api")
        self.assertEqual(self.open().set_target("backend-dev", target), target)

    def test_targets_of_the_two_loops_must_not_overlap(self):
        ws = self.open()
        backend = os.path.join(self.base, "app")
        ws.set_target("backend-dev", backend)
        self.assert_target_error(ws, "frontend-dev", backend)
        self.assert_target_error(ws, "frontend-dev", os.path.join(backend, "web"))
        self.assert_target_error(ws, "frontend-dev", self.base)
        ws.set_target("frontend-dev", os.path.join(self.base, "web"))

    def test_different_target_on_attach_is_a_mismatch(self):
        ws = self.open()
        ws.set_target("backend-dev", os.path.join(self.base, "one"))
        ws.set_target("backend-dev", os.path.join(self.base, "one"))  # same again: fine
        self.assert_target_error(self.open(), "backend-dev", os.path.join(self.base, "two"),
                                 code="workspace-mismatch")

    @unittest.skipIf(os.geteuid() == 0, "root can write anywhere")
    def test_unwritable_target(self):
        locked = os.path.join(self.base, "ro")
        os.makedirs(locked)
        os.chmod(locked, 0o500)
        try:
            self.assert_target_error(self.open(), "backend-dev", os.path.join(locked, "sub"))
            self.assert_target_error(self.open(), "backend-dev", locked)
        finally:
            os.chmod(locked, 0o700)

    # --- lock ---

    def lock_file(self, ws):
        return os.path.join(ws.loop_dir("backend-dev"), "state", "lock")

    def test_lock_acquire_and_release(self):
        loop_dir = self.open().loop_dir("backend-dev")
        info = workspace.acquire_lock(loop_dir)
        self.assertEqual(info["pid"], os.getpid())
        self.assertEqual(state.read_json(os.path.join(loop_dir, "state", "lock"))["pid"],
                         os.getpid())
        workspace.release_lock(loop_dir)
        self.assertFalse(os.path.exists(os.path.join(loop_dir, "state", "lock")))

    def test_live_lock_exits_40_and_names_the_holder(self):
        loop_dir = self.open().loop_dir("backend-dev")
        with workspace.locked(loop_dir):
            with self.assertRaises(state.LockHeld) as cm:
                workspace.acquire_lock(loop_dir)
            self.assertEqual(cm.exception.exit_code, 40)
            self.assertIn(f"pid {os.getpid()}", cm.exception.message)
            self.assertIn("started", cm.exception.message)
        self.assertFalse(os.path.exists(os.path.join(loop_dir, "state", "lock")))

    def dead_pid(self):
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        proc.wait()
        return proc.pid

    def write_lock(self, loop_dir, pid, host=None):
        os.makedirs(os.path.join(loop_dir, "state"), exist_ok=True)
        with open(os.path.join(loop_dir, "state", "lock"), "w") as f:
            json.dump({"pid": pid, "host": host or socket.gethostname(),
                       "started_at": "2026-09-27T00:00:00.000Z"}, f)

    def test_stale_lock_is_reported(self):
        loop_dir = self.open().loop_dir("backend-dev")
        self.write_lock(loop_dir, self.dead_pid())
        with self.assertRaises(state.LockHeld) as cm:
            workspace.acquire_lock(loop_dir)
        self.assertIn("stale lock", cm.exception.message)
        self.assertEqual(cm.exception.exit_code, 40)

    def test_force_unlock_clears_a_stale_lock_and_records_an_event(self):
        loop_dir = self.open().loop_dir("backend-dev")
        pid = self.dead_pid()
        self.write_lock(loop_dir, pid)
        info = workspace.acquire_lock(loop_dir, force_unlock=True)
        self.assertEqual(info["pid"], os.getpid())
        events = state.read_jsonl(os.path.join(loop_dir, "state", "events.jsonl"))
        self.assertEqual([e["type"] for e in events], ["lock-cleared"])
        self.assertIn(str(pid), events[0]["message"])
        workspace.release_lock(loop_dir)

    def test_force_unlock_never_clears_a_live_lock(self):
        loop_dir = self.open().loop_dir("backend-dev")
        self.write_lock(loop_dir, os.getppid())
        with self.assertRaises(state.LockHeld):
            workspace.acquire_lock(loop_dir, force_unlock=True)

    def test_lock_from_another_host_counts_as_live(self):
        loop_dir = self.open().loop_dir("backend-dev")
        self.write_lock(loop_dir, self.dead_pid(), host="some-other-host")
        with self.assertRaises(state.LockHeld) as cm:
            workspace.acquire_lock(loop_dir, force_unlock=True)
        self.assertNotIn("stale", cm.exception.message)

    def test_release_leaves_a_foreign_lock_alone(self):
        loop_dir = self.open().loop_dir("backend-dev")
        self.write_lock(loop_dir, os.getppid())
        workspace.release_lock(loop_dir)
        self.assertTrue(os.path.exists(os.path.join(loop_dir, "state", "lock")))


if __name__ == "__main__":
    unittest.main()
