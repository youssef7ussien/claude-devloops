"""A `backend-dev` loop wired to a stub validator, shared by the User Story 3 tests (T047-T050).

`StubLoopMixin` is not a `TestCase`, so importing it never makes unittest collect tests twice; a
test class mixes it into `unittest.TestCase`. The stub validator passes every criterion unless
`DEVLOOPS_STUB=fail`, so these tests exercise the engine's limits, recovery, and stops without a
real application.
"""
import json
import os
import signal
import subprocess
import sys
import time

import helpers
import samples
from devloops import inputs, state

WS = "us3"

STUB = '''"""Test-only validator: every criterion passes unless DEVLOOPS_STUB=fail."""
import os


def validate(ctx):
    passed = os.environ.get("DEVLOOPS_STUB", "pass") == "pass"
    os.makedirs(ctx.evidence_dir, exist_ok=True)
    with open(os.path.join(ctx.evidence_dir, "stub.txt"), "w") as f:
        f.write("stub evidence")
    return {
        "kind": "curl",
        "criteria": [{"criterion_id": c["id"], "passed": passed, "observed": "stub",
                      "evidence": ["evidence/stub.txt"]}
                     for c in ctx.milestone["acceptance_criteria"]],
        "contract": {"passed": True, "unmatched_operations": []},
        "unit_tests": {"enabled": False},
    }
'''


def implemented(task_id, needs_input=(), suggested="", **extra):
    """An implement/fix answer that implements `task_id`; `extra` adds answer fields. Each
    `needs_input` question gets `suggested` as its suggested answer."""
    return dict({"structured_output": {
        "tasks": [{"task_id": task_id, "status": "implemented", "note": "done"}],
        "assumptions": [],
        "needs_input": [{"question": q, "requirement_refs": ["FR-1"], "suggested_answer": suggested,
                         "suggestion_reason": "why: " + suggested if suggested else ""}
                        for q in needs_input],
        "files_changed": ["app.py"]},
        "writes": [{"path": "app.py", "content": f"# {task_id}\n", "tool": "Write"}]}, **extra)


def service_error(status):
    """A call that fails before any usable result, as Claude Code does on an API error."""
    return {"exit_code": 1, "api_error_status": status, "result": f"API Error: {status}"}


def wait_for(condition, timeout=30, interval=0.1, what="condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = condition()
        if value:
            return value
        time.sleep(interval)
    raise AssertionError(f"timed out after {timeout}s waiting for {what}")


class StubLoopMixin:
    def setUp(self):
        self.t = helpers.TempEnv(workspace=WS).__enter__()
        self.addCleanup(self.t.__exit__, None, None, None)
        loops = os.path.join(self.t.root, "loops")
        self.t.write_file(os.path.join("backend-dev", "loop.json"), json.dumps({
            "name": "backend-dev", "required_inputs": ["requirements"], "required_tools": [],
            "validator": "stub", "requires_openapi_path": False}), base=loops)
        self.t.write_file(os.path.join("backend-dev", "Loop-instructions.md"),
                          "Backend loop (test).\n", base=loops)
        self.t.write_file(os.path.join("shared", "devloops", "validators", "stub.py"), STUB,
                          base=loops)
        self.prd = self.t.write_file("prd.md", "# PRD\n\n- FR-1 list items\n- FR-2 create items\n")
        self.loop_dir = os.path.join(self.t.workspace_dir, "backend-dev")
        self.scenario({"plan": {"structured_output": samples.plan()},
                       "implement": [implemented("M01-T01"), implemented("M02-T01")],
                       "fix": implemented("M01-T01")})

    # --- driving the CLI ---------------------------------------------------------------------------

    def scenario(self, steps):
        self.t.write_scenario({"steps": steps})

    def cli(self, *args, env=None):
        code, out, err = self.t.run_cli([*args, "--workspace", WS], extra_env=env)
        self.last_output = out + err
        return code

    def first_run(self, *extra, env=None):
        return self.cli("run", "backend-dev", "--requirements", self.prd, "--target",
                        self.t.target_dir, *extra, env=env)

    def approved(self, *extra):
        """Plan and approve; the run is then `implementing`."""
        self.assertEqual(self.first_run(*extra), 10, self.last_output)
        self.assertEqual(self.cli("approve", "--no-continue", "backend-dev"), 0, self.last_output)

    def config_file(self, overrides):
        return self.t.write_file("config.json", json.dumps(overrides))

    def start_cli(self, *args, env=None):
        """Start `bin/devloops args...` in the background; the caller stops it."""
        proc = subprocess.Popen(
            [sys.executable, os.path.join(self.t.root, "bin", "devloops"), *args,
             "--workspace", WS],
            env=dict(self.t.env, **(env or {})), cwd=self.t.root, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(self._reap, proc)
        return proc

    def _reap(self, proc):
        if proc.poll() is None:
            proc.kill()
        proc.communicate()

    def wait_for_call(self, step, count=1):
        """Wait until fake Claude has started `count` calls of `step`; return the last one."""
        return wait_for(lambda: ([c for c in self.t.fake_calls() if c["step"] == step][count - 1:]
                                 or [None])[-1], what=f"{count} {step} call(s)")

    def kill_fake(self, call):
        """Stop a fake Claude call that outlived its driver (it runs in its own session)."""
        try:
            os.killpg(call["pid"], signal.SIGKILL)
        except ProcessLookupError:
            pass

    # --- reading state -----------------------------------------------------------------------------

    def run_state(self):
        return state.read_json(os.path.join(self.loop_dir, "state", "run.json"))

    def path(self, relpath):
        return os.path.join(self.loop_dir, relpath)

    def read(self, relpath):
        with open(os.path.join(self.loop_dir, relpath), encoding="utf-8") as f:
            return f.read()

    def write(self, relpath, text):
        with open(os.path.join(self.loop_dir, relpath), "w", encoding="utf-8") as f:
            f.write(text)

    def trial(self, mid, n):
        return state.read_json(os.path.join(self.loop_dir, "state", "milestones", mid, "trials",
                                            str(n), "trial.json"))

    def events(self, type=None):
        events = state.read_jsonl(os.path.join(self.loop_dir, "state", "events.jsonl"))
        return [e for e in events if type is None or e["type"] == type]

    def steps_called(self):
        return [c["step"] for c in self.t.fake_calls()]

    def calls(self, step):
        return [c for c in self.t.fake_calls() if c["step"] == step]

    def context_of(self, call):
        """The driver context block of a fake-Claude call's prompt."""
        return json.loads(call["prompt"].split("```json\n", 1)[1].rsplit("\n```", 1)[0])

    def answers_sha256(self):
        return inputs.sha256_file(os.path.join(self.loop_dir, "outputs", "open-questions.md"))

    def snapshot_state(self):
        """Every file under the loop directory, by content, to prove a command changed nothing."""
        files = {}
        for root, _, names in os.walk(self.loop_dir):
            for name in names:
                path = os.path.join(root, name)
                if os.path.relpath(path, self.loop_dir) == os.path.join("state", "lock"):
                    continue
                with open(path, "rb") as f:
                    files[os.path.relpath(path, self.loop_dir)] = f.read()
        return files
