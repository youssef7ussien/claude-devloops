"""Optional unit tests, shared by both validators (FR-008)."""
import os
import signal
import subprocess

LOG_NAME = os.path.join("evidence", "unit-tests.log")
TIMEOUT_EXIT_CODE = 124


def run(config, plan_runtime, target_dir, trial_dir, redactor=None):
    """Run the unit tests if enabled and return the `unit_tests` part of a validation result.

    The command is `config.unit_tests.command`, else `plan.runtime.unit_test_command`. It runs in
    `<target>/<runtime.cwd>`. `log_path` is relative to the trial directory. A missing command, a
    non-zero exit, or a timeout all fail validation (`exit_code` absent or non-zero).
    """
    settings = config.get("unit_tests") or {}
    if not settings.get("enabled"):
        return {"enabled": False}
    command = settings.get("command") or (plan_runtime or {}).get("unit_test_command")
    log_path = os.path.join(trial_dir, LOG_NAME)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    if not command:
        _write(log_path, "no unit test command: set unit_tests.command or plan "
                         "runtime.unit_test_command\n", redactor)
        return {"enabled": True, "log_path": LOG_NAME}

    cwd = os.path.join(target_dir, (plan_runtime or {}).get("cwd") or ".")
    proc = subprocess.Popen(command, shell=True, cwd=cwd, start_new_session=True, text=True,
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    try:
        output, _ = proc.communicate(timeout=config.get("invocation_timeout_seconds", 1800))
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        output, _ = proc.communicate()
        output = (output or "") + "\n[devloops] unit tests timed out\n"
        exit_code = TIMEOUT_EXIT_CODE
    _write(log_path, f"$ {command}\n{output or ''}\n[exit code {exit_code}]\n", redactor)
    return {"enabled": True, "command": command, "exit_code": exit_code, "log_path": LOG_NAME}


def _write(path, text, redactor):
    if redactor is not None:
        text, _ = redactor.redact(text)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
