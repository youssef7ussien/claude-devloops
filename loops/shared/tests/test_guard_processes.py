"""The Bash guard: no process killing by name or pattern (hooks/guard_processes.py)."""
import json
import os
import subprocess
import sys
import unittest

import helpers

GUARD = os.path.join(helpers.REPO_ROOT, "loops", "shared", "hooks", "guard_processes.py")


def run_guard(command):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command},
                          "hook_event_name": "PreToolUse"})
    proc = subprocess.run([sys.executable, GUARD], input=payload, capture_output=True, text=True,
                          timeout=30)
    return proc.returncode, proc.stderr


class GuardProcessesTest(unittest.TestCase):
    def test_killing_by_name_or_pattern_is_blocked(self):
        for command in ('pkill -f "quickflow/backend"', "killall node", "/usr/bin/pkill -f app",
                        "killall5 -9", "npm test; pkill node", "sudo -E pkill -f app",
                        "kill $(pgrep -f uvicorn)", "pgrep -f server | xargs kill",
                        "P=$(pgrep -f uvicorn); kill $P", "pids=$(pgrep -f app)\nkill $pids",
                        "ps aux | grep uvicorn | awk '{print $2}' | xargs -r kill -9",
                        "kill -9 `pidof python3`", "(pgrep -f app && kill 12) || true",
                        "sudo -u me pkill -f target", "timeout 5 pkill -f app",
                        "bash -c 'pkill -f /path/target'", "kill -9 -1", "kill 0",
                        "kill -- -4242", 'kill "$(pgrep -f app)"'):
            code, err = run_guard(command)
            self.assertEqual(code, 2, command)
            self.assertIn("by their PID", err)

    def test_other_commands_are_allowed(self):
        for command in ("kill $(cat server.pid)", "kill 4242", "npm run build",
                        "python3 -m pytest -k 'skill or kill_switch'", "pgrep -f uvicorn",
                        "echo $! > server.pid", "grep -rn pkill .", "ps aux | grep uvicorn",
                        "fuser -k 8000/tcp", "kill $(lsof -t -i:8000)",
                        "kill -0 $(cat app.pid) && echo running", "echo 'killall is blocked'",
                        "kill $(cat app.pid); sleep 1; ps -p $(cat app.pid)",
                        'echo "a; ps x" && kill 12', "kill -s TERM 55", "kill %1"):
            self.assertEqual(run_guard(command), (0, ""), command)

    def test_unreadable_input_is_allowed(self):
        proc = subprocess.run([sys.executable, GUARD], input="not json", capture_output=True,
                              text=True, timeout=30)
        self.assertEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
