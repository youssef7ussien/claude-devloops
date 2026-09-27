"""The unchanged loops build two unrelated applications (T068; FR-037, FR-050, FR-059; SC-006).

For each smoke fixture (`fixtures/smoke`, a status endpoint; `fixtures/smoke-alt`, a counter), in
its own workspace (`reuse-a`, `reuse-b`), this runs the real `backend-dev` flow and then the real
`frontend-dev` flow through `bin/devloops`, with only Claude faked:

- fake `implement` writes a small stdlib server and its OpenAPI document into the backend target;
  the curl validator starts that server and runs the frozen checks against it;
- the frontend takes the backend's published `outputs/openapi.json` as `--api-spec` and its
  runtime as `backend.*`, so the Playwright adapter starts the same server next to the UI.

Nothing about either application appears in `loops/` or `bin/`: their manifests are identical
before and after, and the two workspaces share no files.
"""
import json
import os
import socket
import sys
import unittest

import helpers
from devloops import boundary, state

PLAYWRIGHT_TOOLS = ["mcp__playwright__browser_navigate", "mcp__playwright__browser_snapshot"]

HEALTH_SERVER = '''import json, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/health":
            self.send_error(404)
            return
        body = json.dumps({"status": "ok"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
'''

COUNTER_SERVER = '''import json, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VALUE = [0]


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, obj):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/counter":
            self._send(200, {"value": VALUE[0]})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/counter/increment":
            VALUE[0] += 1
            self._send(200, {"value": VALUE[0]})
        else:
            self._send(404, {"error": "not found"})

    def log_message(self, *args):
        pass


ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
'''


def _op(summary):
    return {"summary": summary, "responses": {"200": {"description": summary}}}


# One unrelated application per fixture: nothing below is shared between them.
APPS = {
    "reuse-a": {
        "fixture": "smoke", "story": "HEALTH-1", "server": HEALTH_SERVER, "ready_path": "/health",
        "openapi": {"openapi": "3.0.3", "info": {"title": "status", "version": "1.0.0"},
                    "paths": {"/health": {"get": _op("the service status")}}},
        "checks": [{"id": "C1", "criteria": ["M01-AC1"],
                    "request": {"method": "GET", "path": "/health"},
                    "expect": {"status": 200, "json_equals": {"status": "ok"}}}],
        "page": "<h1>Status</h1><p id='status'></p>\n",
        "ui_requests": [("GET", "/health")],
    },
    "reuse-b": {
        "fixture": "smoke-alt", "story": "COUNTER-1", "server": COUNTER_SERVER,
        "ready_path": "/counter",
        "openapi": {"openapi": "3.0.3", "info": {"title": "counter", "version": "1.0.0"},
                    "paths": {"/counter": {"get": _op("the current value")},
                              "/counter/increment": {"post": _op("the new value")}}},
        "checks": [{"id": "C1", "criteria": ["M01-AC1"],
                    "request": {"method": "POST", "path": "/counter/increment"},
                    "expect": {"status": 200, "json_equals": {"value": 1}}},
                   {"id": "C2", "criteria": ["M01-AC1"],
                    "request": {"method": "GET", "path": "/counter"},
                    "expect": {"status": 200, "json_equals": {"value": 1}}}],
        "page": "<h1>Counter</h1><button id='inc'>+1</button><p id='value'></p>\n",
        "ui_requests": [("GET", "/counter"), ("POST", "/counter/increment")],
    },
}


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def one_milestone_plan(story, title, runtime):
    return {
        "requirements_inventory": [{"ref": story, "summary": title}],
        "stack": {"summary": "Python stdlib", "source": "proposed", "conflicts": []},
        "runtime": runtime,
        "milestones": [{
            "id": "M01", "title": title, "goal": title, "depends_on": [],
            "tasks": [{"id": "M01-T01", "title": title, "description": title,
                       "requirement_refs": [story]}],
            "acceptance_criteria": [{"id": "M01-AC1", "text": title,
                                     "requirement_refs": [story]}],
        }],
        "open_questions": [],
        "assumptions": [],
    }


def implemented(files):
    return {"structured_output": {
        "tasks": [{"task_id": "M01-T01", "status": "implemented", "note": "done"}],
        "assumptions": [], "needs_input": [], "files_changed": sorted(files)},
        "writes": [{"path": p, "content": c, "tool": "Write"} for p, c in files.items()]}


def loops_and_bin(root):
    """The `boundary.snapshot` manifest of `loops/` and `bin/` alone (no loop `state/` dir)."""
    return boundary.snapshot(root, os.path.join(root, "no-such-loop-dir"), [])["manifest"]


def files_under(directory):
    return {os.path.realpath(os.path.join(d, n)) for d, _, names in os.walk(directory)
            for n in names}


class ReusabilityTest(unittest.TestCase):
    def setUp(self):
        self.t = helpers.TempEnv(workspace="reuse-a").__enter__()
        self.addCleanup(self.t.__exit__, None, None, None)
        self.fixtures = os.path.join(self.t.root, "loops", "shared", "tests", "fixtures")

    def cli(self, ws, *args):
        code, out, err = self.t.run_cli([*args, "--workspace", ws])
        self.last_output = out + err
        return code

    def scenario(self, steps):
        self.t.write_scenario({"steps": steps})

    def loop_dir(self, ws, loop):
        return os.path.join(self.t.root, "workspaces", ws, loop)

    def run_state(self, ws, loop):
        return state.read_json(os.path.join(self.loop_dir(ws, loop), "state", "run.json"))

    # --- the two flows -----------------------------------------------------------------------------

    def build_backend(self, ws, app, target, port):
        base_url = f"http://127.0.0.1:{port}"
        runtime = {"start_command": f"{sys.executable} server.py {port}", "cwd": ".",
                   "base_url": base_url, "ready_url": base_url + app["ready_path"],
                   "openapi_path": "openapi.json"}
        requirements = os.path.join(self.fixtures, app["fixture"], "requirements.md")
        self.scenario({"plan": {"structured_output": one_milestone_plan(
            app["story"], "Backend", runtime)}})
        self.assertEqual(self.cli(ws, "run", "backend-dev", "--requirements", requirements,
                                  "--target", target), 10, self.last_output)
        self.assertEqual(self.cli(ws, "approve", "backend-dev"), 0, self.last_output)
        self.scenario({
            "author-checks": {"structured_output": {"milestone_id": "M01",
                                                    "checks": app["checks"]}},
            "implement": implemented({"server.py": app["server"],
                                      "openapi.json": json.dumps(app["openapi"])})})
        self.assertEqual(self.cli(ws, "run", "backend-dev"), 0, self.last_output)
        return requirements, runtime

    def build_frontend(self, ws, app, requirements, backend_target, backend_runtime):
        port = free_port()
        ui_url = f"http://127.0.0.1:{port}"
        api_spec = os.path.join(self.loop_dir(ws, "backend-dev"), "outputs", "openapi.json")
        config = self.t.write_file(f"{ws}-frontend.json", json.dumps({
            "playwright": {"mcp_command": [sys.executable, "-c", "pass"]},
            "backend": {"start_command": backend_runtime["start_command"], "cwd": backend_target,
                        "ready_url": backend_runtime["ready_url"]}}))
        runtime = {"start_command": f"{sys.executable} -m http.server {port} --bind 127.0.0.1",
                   "cwd": ".", "base_url": ui_url, "ready_url": ui_url + "/"}
        self.scenario({"plan": {"structured_output": one_milestone_plan(
            app["story"], "Page", runtime)}})
        target = os.path.join(self.t.base, f"{ws}-frontend")
        self.assertEqual(self.cli(ws, "run", "frontend-dev", "--requirements", requirements,
                                  "--target", target, "--api-spec", api_spec, "--config", config),
                         10, self.last_output)
        self.assertEqual(self.cli(ws, "approve", "frontend-dev"), 0, self.last_output)

        evidence = os.path.join(self.loop_dir(ws, "frontend-dev"), "state", "milestones", "M01",
                                "trials", "1", "evidence", "page.png")
        backend_url = backend_runtime["base_url"]
        self.scenario({
            "implement": implemented({"index.html": app["page"]}),
            "validate-ui": {
                "structured_output": {
                    "criteria": [{"criterion_id": "M01-AC1", "passed": True,
                                  "steps": ["open the UI URL", "snapshot the page"],
                                  "observed": "the page shows the backend's value",
                                  "evidence": ["evidence/page.png"]}],
                    "network_requests": [{"method": "GET", "url": ui_url + "/", "status": 200}] +
                    [{"method": m, "url": backend_url + p, "status": 200}
                     for m, p in app["ui_requests"]]},
                "tool_uses": PLAYWRIGHT_TOOLS,
                "writes": [{"path": evidence, "content": "PNG"}]}})
        self.assertEqual(self.cli(ws, "run", "frontend-dev"), 0, self.last_output)
        return ui_url

    # --- the test ------------------------------------------------------------------------------------

    def test_two_unrelated_applications_leave_the_loops_unchanged(self):
        before = loops_and_bin(self.t.root)
        self.assertTrue(before)

        for ws, app in APPS.items():
            with self.subTest(workspace=ws):
                backend_target = os.path.join(self.t.base, f"{ws}-backend")
                requirements, runtime = self.build_backend(ws, app, backend_target, free_port())
                ui_url = self.build_frontend(ws, app, requirements, backend_target, runtime)

                backend, frontend = (self.run_state(ws, "backend-dev"),
                                     self.run_state(ws, "frontend-dev"))
                self.assertEqual((backend["status"], frontend["status"]),
                                 ("completed", "completed"))
                with open(os.path.join(self.loop_dir(ws, "backend-dev"), "outputs",
                                       "openapi.json"), encoding="utf-8") as f:
                    self.assertEqual(json.load(f), app["openapi"])
                # curl ran every frozen check against the server fake Claude wrote.
                trial = os.path.join("state", "milestones", "M01", "trials", "1")
                checked = state.read_json(os.path.join(self.loop_dir(ws, "backend-dev"), trial,
                                                       "validation.json"))
                self.assertEqual([(c["check_id"], c["passed"], c["response"]["status"])
                                  for c in checked["checks"]],
                                 [(c["id"], True, 200) for c in app["checks"]])
                self.assertEqual(frontend["ui_url"], ui_url)
                validation = state.read_json(os.path.join(self.loop_dir(ws, "frontend-dev"),
                                                          trial, "validation.json"))
                self.assertEqual(validation["contract"],
                                 {"passed": True, "unmatched_operations": []})
                # The Playwright adapter started the same backend next to the UI.
                self.assertTrue(os.path.exists(os.path.join(self.loop_dir(ws, "frontend-dev"),
                                                            trial, "backend.log")))

        # The loops were used, not changed (FR-037, FR-050).
        self.assertEqual(loops_and_bin(self.t.root), before)

        # Each application lives in its own workspace, with its own requirements (SC-006).
        a, b = (os.path.join(self.t.root, "workspaces", ws) for ws in APPS)
        a_files, b_files = files_under(a), files_under(b)
        self.assertTrue(a_files and b_files)
        self.assertEqual(a_files & b_files, set())
        for ws, app in APPS.items():
            recorded = state.read_json(os.path.join(self.t.root, "workspaces", ws,
                                                    "workspace.json"))["requirements"]
            self.assertIn(os.path.join(app["fixture"], "requirements.md"), recorded["path"])


if __name__ == "__main__":
    unittest.main()
