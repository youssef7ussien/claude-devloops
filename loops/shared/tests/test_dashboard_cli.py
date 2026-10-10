"""`devloops dashboard`: serving in the foreground or as a daemon, stopping, and the flags it no
longer takes (specs/005-dashboard-redesign contracts/cli.md, research R-11)."""
import http.client
import json
import os
import signal
import socket
import stat
import subprocess
import sys
import unittest
from unittest import mock

import helpers  # noqa: F401 - puts the package on sys.path
from devloops import serve, workspace
from stub_loop import WS, StubLoopMixin, wait_for


class BrowserTest(unittest.TestCase):
    def test_devloops_no_browser_keeps_it_closed(self):
        with mock.patch.object(serve.webbrowser, "open") as opened:
            serve._open("http://127.0.0.1:1/", {"DEVLOOPS_NO_BROWSER": "1"})
            self.assertFalse(opened.called)
            serve._open("http://127.0.0.1:1/", {})
            wait_for(lambda: opened.called, what="the browser to open")
            opened.assert_called_with("http://127.0.0.1:1/")


class DashboardCommandTest(StubLoopMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.first_run(), 10, self.last_output)
        self.addCleanup(lambda: self.t.run_cli(["dashboard", "--stop"]))

    def dashboard(self, *args):
        code, out, err = self.t.run_cli(["dashboard", *args], timeout=60)
        self.last_output = out + err
        return code, out, err

    def answers(self, url):
        parts = url.split("/")
        host, port = parts[2].rsplit(":", 1)
        conn = http.client.HTTPConnection(host, int(port), timeout=10)
        try:
            conn.request("GET", f"/w/{WS}/version")
            return conn.getresponse().status
        finally:
            conn.close()

    # --- in the foreground ---------------------------------------------------------------------------

    def test_foreground_serving_and_a_second_command(self):
        proc = self.start_cli("dashboard", "--port", "0", "--json")
        started = json.loads(wait_for(proc.stdout.readline, what="the server's first line"))
        self.assertEqual((started["workspace"], started["token"], started["daemon"], started["pid"]),
                         (WS, False, False, proc.pid))
        url = started["serving"]
        self.assertRegex(url, rf"^http://127\.0\.0\.1:\d+/w/{WS}/$")
        self.assertEqual(serve.running(self.t.project(), self.t.env)["pid"], proc.pid)
        # Commands say where it is served.
        self.assertEqual(self.cli("approve", "--no-continue"), 0, self.last_output)
        self.assertIn(url, self.last_output)
        # A second `devloops dashboard` prints its address and returns.
        code, out, _ = self.dashboard("--workspace", WS)
        self.assertEqual(code, 0, self.last_output)
        self.assertIn(f"serving: {url}", out)
        self.assertIn(f"already running (pid {proc.pid})", out)
        # Stopped, it removes its record.
        proc.send_signal(signal.SIGTERM)
        self.assertEqual(proc.wait(timeout=30), 0)
        self.assertIsNone(serve.running(self.t.project(), self.t.env))
        self.assertFalse(os.path.exists(serve.record_path(self.t.project(), self.t.env)))

    def test_a_named_workspace_that_does_not_exist_is_an_error(self):
        default = self.t.project().default_workspace
        self.assertNotEqual(default, WS)
        code, _, err = self.dashboard("--workspace", default, "--no-open")
        self.assertEqual(code, 2, self.last_output)
        self.assertIn("does not exist", err)

    def test_usage_errors(self):
        removed = {"--serve": "--daemon", "--open": "--no-open", "--light": "serves",
                   "--out": "--export <path>"}
        for flag, hint in removed.items():
            code, _, err = self.dashboard(flag, *(["x.html"] if flag == "--out" else []))
            self.assertEqual(code, 2, flag)
            self.assertIn(f"{flag} was removed", err)
            self.assertIn(hint, err)
        for args in (["--stop", "--port", "1"], ["--stop", "--host", "0.0.0.0"],
                     ["--stop", "--no-open"], ["--export", "--no-token"],
                     ["--export", "--token", "abcdefgh"], ["--stop", "--daemon"],
                     ["--stop", "--export"], ["--token", "abcdefgh", "--no-token"],
                     ["--token", "short"], ["--token", "has;semicolons"]):
            self.assertEqual(self.dashboard(*args)[0], 2, args)

    # --- as a daemon -----------------------------------------------------------------------------------

    def test_daemon_start_reuse_and_stop(self):
        code, out, _ = self.dashboard("--daemon", "--port", "0", "--json")
        self.assertEqual(code, 0, self.last_output)
        started = json.loads(out)
        log = serve.log_path(self.t.project(), self.t.env)
        self.assertEqual((started["daemon"], started["log"], started["workspace"]), (True, log, WS))
        self.assertEqual(self.answers(started["serving"]), 200)
        record = serve.running(self.t.project(), self.t.env)
        self.assertEqual((record["pid"], record["daemon"], record["log"]),
                         (started["pid"], True, log))
        with open(log, encoding="utf-8") as f:
            self.assertIn(f"serving the dashboards of {self.t.root}", f.read())
        # A second --daemon reuses it.
        code, out, _ = self.dashboard("--daemon")
        self.assertEqual(code, 0, self.last_output)
        self.assertIn(f"serving: {started['serving']}", out)
        self.assertIn(f"log: {log}", out)
        # --stop stops it, then there is nothing to stop.
        code, out, _ = self.dashboard("--stop")
        self.assertEqual((code, out.strip()), (0, "stopped"), self.last_output)
        self.assertIsNone(serve.running(self.t.project(), self.t.env))
        self.assertFalse(os.path.exists(serve.record_path(self.t.project(), self.t.env)))
        code, out, _ = self.dashboard("--stop", "--json")
        self.assertEqual((code, json.loads(out)), (0, {"stopped": False}))

    def test_a_run_writes_no_dashboard_and_points_to_it(self):
        # SC-009, FR-008–FR-010: a completed run writes no page and no export; it names the
        # command that starts a server, and the URL only while one runs.
        self.assertEqual(self.cli("approve", "--json"), 0, self.last_output)
        result = json.loads(self.last_output)
        self.assertEqual(result["run"]["status"], "completed")
        for key in ("dashboard", "full_dashboard", "dashboard_url"):
            self.assertNotIn(key, result)
        self.assertFalse(os.path.exists(os.path.join(self.t.workspace_dir, "dashboard.html")))
        self.assertFalse(os.path.exists(os.path.join(self.t.workspace_dir, "exports")))
        code, out, err = self.t.run_cli(["run", "--workspace", WS])
        self.assertEqual(code, 0, out + err)
        self.assertTrue(out.rstrip().endswith(
            f"dashboard: devloops dashboard --daemon --workspace {WS}"), out)
        self.assertIsNone(serve.running(self.t.project(), self.t.env))  # none was started
        code, out, _ = self.dashboard("--daemon", "--port", "0", "--json")
        self.assertEqual(code, 0, self.last_output)
        url = json.loads(out)["serving"]
        self.assertEqual(self.cli("status", "--json"), 0, self.last_output)
        self.assertEqual(json.loads(self.last_output)["dashboard_url"], url)
        code, out, err = self.t.run_cli(["status", "--workspace", WS])
        self.assertEqual(code, 0, out + err)
        self.assertTrue(out.rstrip().endswith(f"dashboard: {url}"), out)

    def test_a_daemon_that_cannot_start(self):
        taken = socket.socket()
        taken.bind(("127.0.0.1", 0))
        taken.listen(1)
        self.addCleanup(taken.close)
        code, _, err = self.dashboard("--daemon", "--port", str(taken.getsockname()[1]))
        self.assertEqual(code, 1, self.last_output)
        self.assertIn("did not start", err)
        self.assertIn("cannot listen on 127.0.0.1", err)
        self.assertIsNone(serve.running(self.t.project(), self.t.env))

    def test_a_daemon_keeps_its_token_out_of_the_process_list(self):
        token = "tok-" + "x" * 12
        code, out, _ = self.dashboard("--daemon", "--port", "0", "--token", token, "--json")
        self.assertEqual(code, 0, self.last_output)
        started = json.loads(out)
        self.assertTrue(started["serving"].endswith(f"?token={token}"), started)
        self.assertTrue(started["token"])
        cmdline = f"/proc/{started['pid']}/cmdline"
        if os.path.exists(cmdline):
            with open(cmdline, "rb") as f:
                self.assertNotIn(token.encode(), f.read())
        log = serve.log_path(self.t.project(), self.t.env)
        self.assertEqual(stat.S_IMODE(os.stat(log).st_mode), 0o600)
        self.assertEqual(self.answers(started["serving"].split("?")[0]), 403)  # no cookie yet

    def test_a_daemon_for_a_workspace_outside_the_workspaces_folder(self):
        path = os.path.join(self.t.base, "elsewhere", "ws-b")
        workspace.open_workspace(path, self.t.project(), self.t.kit(), create=True)
        code, out, _ = self.dashboard("--daemon", "--port", "0", "--workspace", path, "--json")
        self.assertEqual(code, 0, self.last_output)
        self.assertTrue(json.loads(out)["serving"].endswith("/w/ws-b/"), out)

    def test_stop_spares_a_process_that_is_not_a_dashboard(self):
        other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(other.wait)
        self.addCleanup(other.kill)
        path = serve.record_path(self.t.project(), self.t.env)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:  # a record left by a crash, its pid reused
            json.dump({"pid": other.pid, "hostname": socket.gethostname()}, f)
        code, out, _ = self.dashboard("--stop")
        self.assertEqual((code, out.strip()), (0, "not running"))
        self.assertIsNone(other.poll())
        self.assertFalse(os.path.exists(path))

    def test_stop_keeps_the_record_of_a_server_on_another_host(self):
        path = serve.record_path(self.t.project(), self.t.env)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        rec = {"pid": os.getpid(), "hostname": "another-host.example"}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rec, f)
        code, out, _ = self.dashboard("--stop", "--json")
        self.assertEqual((code, json.loads(out)), (0, {"stopped": False,
                                                       "host": "another-host.example"}))
        with open(path, encoding="utf-8") as f:
            self.assertEqual(json.load(f), rec)

    def test_a_stale_record_is_removed_by_stop(self):
        path = serve.record_path(self.t.project(), self.t.env)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"pid": 2 ** 22 + 12345, "hostname": socket.gethostname()}, f)
        code, out, _ = self.dashboard("--stop")
        self.assertEqual((code, out.strip()), (0, "not running"))
        self.assertFalse(os.path.exists(path))


if __name__ == "__main__":
    unittest.main()
