"""Start, wait for, and stop the application under test (plan: Runtime control)."""
import os
import signal
import subprocess
import time
import urllib.error
import urllib.request

STOP_GRACE_SECONDS = 10
POLL_INTERVAL_SECONDS = 0.25


class RuntimeStartFailed(Exception):
    """The runtime did not become ready; a trial fails with reason `runtime-start-failed`."""


def start(command, cwd, env=None, log_path=None):
    """Start `command` through the shell in its own process group; output goes to `log_path`."""
    if log_path:
        os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
        out = open(log_path, "ab")
    else:
        out = subprocess.DEVNULL
    try:
        return subprocess.Popen(command, shell=True, cwd=cwd, env=env, start_new_session=True,
                                stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT)
    except OSError as e:
        raise RuntimeStartFailed(f"cannot start {command!r} in {cwd}: {e.strerror or e}")
    finally:
        if log_path:
            out.close()


def wait_ready(ready_url, timeout, proc=None):
    """Poll `ready_url` until it answers with a status below 500, or raise `RuntimeStartFailed`."""
    deadline = time.monotonic() + timeout
    last_error = "no response"
    while True:
        if proc is not None and proc.poll() is not None:
            raise RuntimeStartFailed(f"the runtime exited with code {proc.returncode} before "
                                     f"{ready_url} was ready")
        try:
            with urllib.request.urlopen(ready_url, timeout=2) as response:
                if response.status < 500:
                    return
                last_error = f"HTTP {response.status}"
        except urllib.error.HTTPError as e:
            e.close()
            if e.code < 500:
                return
            last_error = f"HTTP {e.code}"
        except (urllib.error.URLError, OSError, ValueError) as e:
            last_error = str(getattr(e, "reason", e))
        if time.monotonic() >= deadline:
            raise RuntimeStartFailed(f"{ready_url} was not ready within {timeout}s ({last_error})")
        time.sleep(POLL_INTERVAL_SECONDS)


def stop(proc, grace=STOP_GRACE_SECONDS):
    """SIGTERM the process group, wait up to `grace` seconds, then SIGKILL it."""
    if proc is None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        proc.poll()
        return
    try:
        proc.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)  # children that outlived the leader
    except (ProcessLookupError, PermissionError):
        pass
    try:
        proc.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        pass


class Runtime:
    """`with Runtime(...) as proc:` starts the app, waits until it is ready, and always stops it."""

    def __init__(self, command, cwd, ready_url, timeout, env=None, log_path=None):
        self.command, self.cwd, self.ready_url, self.timeout = command, cwd, ready_url, timeout
        self.env, self.log_path = env, log_path
        self.proc = None

    def __enter__(self):
        self.proc = start(self.command, self.cwd, self.env, self.log_path)
        try:
            wait_ready(self.ready_url, self.timeout, self.proc)
        except BaseException:
            stop(self.proc)
            raise
        return self.proc

    def __exit__(self, *exc):
        stop(self.proc)
        return False
