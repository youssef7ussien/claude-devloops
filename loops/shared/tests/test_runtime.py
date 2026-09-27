import os
import socket
import sys
import tempfile
import time
import unittest
import urllib.request

import helpers  # noqa: F401
from devloops import runtime


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class RuntimeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        with open(os.path.join(self.dir, "index.html"), "w") as f:
            f.write("hello")
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}/"
        self.command = f"{sys.executable} -m http.server {self.port} --bind 127.0.0.1"

    def tearDown(self):
        self.tmp.cleanup()

    def test_context_manager_starts_waits_and_stops(self):
        log = os.path.join(self.dir, "logs", "runtime.log")
        with runtime.Runtime(self.command, self.dir, self.url, 20, log_path=log) as proc:
            with urllib.request.urlopen(self.url + "index.html", timeout=5) as r:
                self.assertEqual(r.read(), b"hello")
        self.assertIsNotNone(proc.poll())
        with self.assertRaises(OSError):
            urllib.request.urlopen(self.url, timeout=2)
        self.assertTrue(os.path.exists(log))

    def test_a_4xx_ready_url_counts_as_ready(self):
        with runtime.Runtime(self.command, self.dir, self.url + "missing", 20):
            pass

    def test_process_that_exits_fails_fast(self):
        started = time.monotonic()
        with self.assertRaises(runtime.RuntimeStartFailed) as cm:
            with runtime.Runtime("exit 3", self.dir, self.url, 30):
                pass
        self.assertIn("exited with code 3", str(cm.exception))
        self.assertLess(time.monotonic() - started, 10)

    def test_ready_timeout(self):
        with self.assertRaises(runtime.RuntimeStartFailed) as cm:
            with runtime.Runtime("sleep 30", self.dir, self.url, 1):
                pass
        self.assertIn("not ready within 1s", str(cm.exception))

    def test_stop_kills_the_whole_group(self):
        # The shell starts a child that ignores SIGTERM; the group SIGKILL still ends it.
        proc = runtime.start("trap '' TERM; sleep 60 & wait", self.dir)
        time.sleep(0.3)
        started = time.monotonic()
        runtime.stop(proc, grace=1)
        self.assertIsNotNone(proc.poll())
        self.assertLess(time.monotonic() - started, 5)
        with self.assertRaises(ProcessLookupError):
            os.killpg(proc.pid, 0)

    def test_stop_none_is_a_no_op(self):
        runtime.stop(None)


if __name__ == "__main__":
    unittest.main()
