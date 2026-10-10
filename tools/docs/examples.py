#!/usr/bin/env python3
"""Write the documentation's example outputs from a real devloops run (spec 006 FR-019, R-9).

    python3 tools/docs/examples.py           # rewrite docs-include/examples/
    python3 tools/docs/examples.py --check   # compare instead; exit 1 naming each differing file

The run is real devloops against the stand-in Claude Code the tests use (`fake_claude.py`), on a
generic sample application: the curl tests' item server (`fixtures/http_app.py`), a plan with
two milestones (`samples.plan()`), and requirements that say only "list and create items"
(constitution II: no application specifics). It runs `init`, `check`, `run` (pausing for the
plan's review), `approve`, `status`, `status --json` and `dashboard --export`, and writes each
command's output to `docs-include/examples/<name>.txt`, plus `workspace-files.txt`: every file
the run wrote, workspace-relative and sorted.

Outputs are made the same on every machine and every run: the temporary folder becomes
`<project>`, times `2026-01-01T00:00:00Z`, durations `1s`, the server's port `8765`, and ids
Claude Code would choose at random are numbered in order of appearance. Costs and token counts
are kept as the stand-in reports them.
"""
import argparse
import json
import os
import re
import socket
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TESTS = os.path.join(ROOT, "loops", "shared", "tests")
OUT = os.path.join(ROOT, "docs-include", "examples")
sys.path.insert(0, TESTS)

import helpers  # noqa: E402  (also puts the devloops package on sys.path)
import samples  # noqa: E402

PORT = 8765  # what the outputs show, whatever port the run used
REQUIREMENTS = """# Items service

A small HTTP service that keeps a list of items.

- FR-1: Clients can list the items.
- FR-2: Clients can create an item with a name.
"""


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def sample_plan(port):
    plan = samples.plan()  # M01 "List items" (GET /items), M02 "Create items" (POST /items)
    plan["runtime"] = {
        "start_command": f"python3 app.py {port}",
        "cwd": ".",
        "base_url": f"http://127.0.0.1:{port}",
        "ready_url": f"http://127.0.0.1:{port}/health",
        "openapi_path": "openapi.json",
    }
    return plan


def openapi(*operations):
    paths = {}
    for method, path, status, text in operations:
        paths.setdefault(path, {})[method] = {"responses": {status: {"description": text}}}
    return {"openapi": "3.0.3", "info": {"title": "items", "version": "1.0.0"}, "paths": paths}


def implemented(task_id, document, app):
    return {"structured_output": {
        "tasks": [{"task_id": task_id, "status": "implemented", "note": "done"}],
        "assumptions": [], "needs_input": [], "files_changed": ["app.py", "openapi.json"]},
        "writes": [{"path": "app.py", "content": app, "tool": "Write"},
                   {"path": "openapi.json", "content": json.dumps(document, indent=2),
                    "tool": "Write"}]}


def scenario():
    """The stand-in's answers: a plan, then per milestone its checks and one passing trial."""
    with open(os.path.join(helpers.FIXTURES_DIR, "http_app.py"), encoding="utf-8") as f:
        app = f.read()
    m01 = openapi(("get", "/items", "200", "the items"))
    m02 = openapi(("get", "/items", "200", "the items"), ("post", "/items", "201", "created"))
    return {
        "author-checks": [
            {"structured_output": {"milestone_id": "M01", "checks": [
                {"id": "C1", "criteria": ["M01-AC1"],
                 "request": {"method": "GET", "path": "/items"},
                 "expect": {"status": 200, "body_contains": ["["]}}]}},
            {"structured_output": {"milestone_id": "M02", "checks": [
                {"id": "C1", "criteria": ["M02-AC1"],
                 "request": {"method": "POST", "path": "/items",
                             "headers": {"Content-Type": "application/json"},
                             "body": {"name": "Widget"}},
                 "expect": {"status": 201, "json_equals": {"name": "Widget"}}}]}},
        ],
        "implement": [implemented("M01-T01", m01, app), implemented("M02-T01", m02, app)],
    }


class Normaliser:
    """Makes an output the same on every machine and run (see the module docstring)."""

    TIME = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?")
    CLOCK = re.compile(r"\b\d{2}:\d{2}:\d{2}\b")  # progress lines
    STAMP = re.compile(r"\b\d{8}T\d{6}Z(-\d+)?\b")  # export file names
    DURATION = re.compile(r"\b\d+(?:\.\d+)?(?:ms|s)\b|\b\d+m ?\d+s\b")
    UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
    HEX = re.compile(r"\b[0-9a-f]{64}\b")

    # `devloops check` reports the versions on this machine; the examples show fixed ones.
    TOOLS = {"python": "3.12.3", "claude": "2.1.0", "curl": "8.5.0", "git": "/usr/bin/git"}

    def __init__(self, base, port, commands):
        self.base, self.port, self.commands = base, port, commands
        self.ids = {}

    def _id(self, match):
        value = match.group(0)
        if value not in self.ids:
            self.ids[value] = f"00000000-0000-4000-8000-{len(self.ids) + 1:012d}"
        return self.ids[value]

    def __call__(self, text):
        for command in self.commands:  # the checkout's bin/devloops, as an install names it
            text = text.replace(command, "devloops")
        text = text.replace(os.path.join(self.base, "app"), "<project>")
        text = text.replace(self.base, "<tmp>")
        text = re.sub(rf"\b{self.port}\b", str(PORT), text)
        for tool, shown in self.TOOLS.items():
            text = re.sub(rf"^(\s+ready\s+{tool}\s+)\S+$", rf"\g<1>{shown}", text, flags=re.M)
        text = self.TIME.sub("2026-01-01T00:00:00Z", text)
        text = self.CLOCK.sub("00:00:00", text)
        text = self.STAMP.sub("20260101T000000Z", text)
        text = self.DURATION.sub("1s", text)
        text = self.UUID.sub(self._id, text)
        text = self.HEX.sub("0" * 64, text)
        return text.rstrip() + "\n"


def sample_run():
    """Run the sample and return `{name: normalised output}`."""
    # A temporary folder whose path has the same length everywhere: the export embeds the
    # workspace's records, so its sizes in `export.txt` would otherwise vary by machine.
    if os.path.isdir("/tmp"):
        tempfile.tempdir = "/tmp"
    t = helpers.TempEnv(workspace="main", symlink=True).__enter__()
    try:
        port = free_port()
        app_dir = os.path.join(t.base, "app")
        t.write_file("requirements.md", REQUIREMENTS, base=app_dir)
        devloops = os.path.join(t.root, "bin", "devloops")
        norm = Normaliser(t.base, port, [devloops, os.path.realpath(devloops)])
        outputs = {}

        def cli(name, *args):
            # stdout and stderr in one stream, in the order a terminal shows them
            env = dict(t.env, COLUMNS="100", PYTHONUNBUFFERED="1")  # after write_scenario
            proc = subprocess.run([sys.executable, devloops, *args], cwd=app_dir, env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                  timeout=300)
            code = proc.returncode
            text = f"$ devloops {' '.join(args)}\n" + proc.stdout
            if code:
                text += f"(exit code {code})\n"
            outputs[name] = norm(text)
            return code

        def expect(code, wanted, name):
            if code != wanted:
                raise SystemExit(f"examples: `{name}` exited {code}, not {wanted}:\n"
                                 + outputs[name])

        t.write_scenario({"steps": {"plan": {"structured_output": sample_plan(port)}}})
        expect(cli("init", "init", "--no-frontend", "--requirements", "requirements.md",
                   "--no-prompt"), 0, "init")
        expect(cli("check", "check"), 0, "check")
        expect(cli("run", "run", "--review-plan"), 10, "run")
        t.write_scenario({"steps": scenario()})
        expect(cli("approve", "approve"), 0, "approve")
        expect(cli("status", "status"), 0, "status")
        expect(cli("status-json", "status", "--json"), 0, "status-json")
        expect(cli("export", "dashboard", "--export"), 0, "export")

        workspace = os.path.join(app_dir, ".devloops", "workspaces", "main")
        files = []
        for directory, _, names in os.walk(workspace):
            for name in names:
                rel = os.path.relpath(os.path.join(directory, name), workspace)
                files.append(norm(rel.replace(os.sep, "/")).strip())
        outputs["workspace-files"] = "\n".join(sorted(files)) + "\n"
        return outputs
    finally:
        t.__exit__(None, None, None)


# Sizes in `devloops dashboard --export`'s report: the export embeds each call's settings, which
# name this machine's Python, so its size differs by a few bytes between machines. `--check`
# compares the reports without them; the file keeps the sizes of the run that wrote it.
SIZE = re.compile(r"\(\d+(?:\.\d+)? (?:B|KB|MB|GB)\)")


def same(current, new):
    return current is not None and SIZE.sub("(size)", current) == SIZE.sub("(size)", new)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Write the documentation's example outputs.")
    parser.add_argument("--check", action="store_true",
                        help="compare with docs-include/examples/ instead of writing; exit 1 "
                             "naming each differing file")
    args = parser.parse_args(argv)
    outputs = sample_run()
    differing = []
    for name, text in sorted(outputs.items()):
        path = os.path.join(OUT, name + ".txt")
        try:
            with open(path, encoding="utf-8") as f:
                current = f.read()
        except FileNotFoundError:
            current = None
        if current == text or (args.check and same(current, text)):
            continue
        if args.check:
            differing.append(os.path.relpath(path, ROOT))
        else:
            os.makedirs(OUT, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"wrote {os.path.relpath(path, ROOT)}")
    if differing:
        print("differs from what examples.py writes now (run python3 tools/docs/examples.py):")
        for path in differing:
            print(f"  {path}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
