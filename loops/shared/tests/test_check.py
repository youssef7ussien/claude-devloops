"""`devloops check` (002 FR-018, FR-019, SC-005; research P-14; contracts/cli.md)."""
import json
import os
import stat
import unittest

import helpers
from devloops import checkcmd, preflight

TOOLS = {"claude": "2.1.283 (Claude Code)", "curl": "curl 8.10.1 (x86_64-pc-linux-gnu)",
         "npx": "10.9.0", "git": "git version 2.47.0", "google-chrome": "Google Chrome 131"}


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.t = helpers.TempEnv(symlink=True).__enter__()
        self.addCleanup(self.t.__exit__, None, None, None)
        self.bin = os.path.join(self.t.base, "stub-bin")
        os.makedirs(self.bin)
        for name, output in TOOLS.items():
            self.stub(name, output)
        self.env = dict(self.t.env, PATH=self.bin)
        self.env.pop("DEVLOOPS_CLAUDE_BIN", None)
        self.targets = {"backend-dev": "backend", "frontend-dev": "frontend"}  # both loops
        self.t.make_project(self.t.root, {"workspaces_dir": "workspaces",
                                          "targets": self.targets})

    def stub(self, name, output):
        path = os.path.join(self.bin, name)
        with open(path, "w") as f:
            f.write(f"#!/bin/sh\necho '{output}'\n")
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)

    def hide(self, name):
        os.remove(os.path.join(self.bin, name))

    def check(self, project=True, **kwargs):
        kwargs.setdefault("browser_paths", ())
        kwargs.setdefault("platform", "linux")
        return checkcmd.run_checks(self.t.project() if project else None, self.t.kit(),
                                   self.env, **kwargs)

    def item(self, result, name):
        [item] = [i for i in result["items"] if i["name"] == name]
        return item

    def write_config(self, name, config):
        path = os.path.join(self.t.root, ".devloops", name)
        data = {"config": config}
        if name == "devloops.json":
            data.update(schema_version=1, workspaces_dir="workspaces", targets=self.targets)
        with open(path, "w") as f:
            json.dump(data, f)

    def cli(self, *args, cwd=None):
        code, out, err = helpers.run_cli(["check", *args], env=self.env, root=self.t.root,
                                         cwd=cwd or self.t.root)
        self.output = out + err
        return code, out

    # --- the items ---

    def test_all_present(self):
        result = self.check()
        self.assertTrue(result["ready"])
        self.assertEqual([i["name"] for i in result["items"]],
                         ["python", "claude", "curl", "playwright-mcp", "browser", "git"])
        for item in result["items"]:
            self.assertEqual(item["status"], "ready", item)
            self.assertIsNone(item["fix"])
        self.assertEqual(self.item(result, "claude")["detail"], "2.1.283")

    def test_each_missing_tool_is_named_with_a_fix(self):
        for tool, item in (("claude", "claude"), ("curl", "curl"), ("npx", "playwright-mcp"),
                           ("google-chrome", "browser")):
            with self.subTest(tool=tool):
                self.hide(tool)
                try:
                    result = self.check()
                    self.assertFalse(result["ready"])
                    found = self.item(result, item)
                    self.assertEqual(found["status"], "missing")
                    self.assertTrue(found["fix"])
                finally:
                    self.stub(tool, TOOLS[tool])

    def test_an_old_claude_code_needs_an_update(self):
        self.stub("claude", "2.1.100 (Claude Code)")
        item = self.item(self.check(), "claude")
        self.assertEqual(item["status"], "missing")
        self.assertIn("update", item["fix"])
        self.assertEqual(preflight.parse_version("2.1.283 (Claude Code)"),
                         preflight.MIN_CLAUDE_VERSION)

    def test_a_configured_executable_path_must_be_executable(self):
        self.hide("google-chrome")
        self.write_config("devloops.local.json",
                          {"playwright": {"executable_path": os.path.join(self.bin, "nope")}})
        self.assertEqual(self.item(self.check(), "browser")["status"], "missing")
        self.write_config("devloops.local.json",
                          {"playwright": {"executable_path": os.path.join(self.bin, "npx")}})
        self.assertEqual(self.item(self.check(), "browser")["status"], "ready")

    def test_an_explicit_mcp_command_chooses_the_browser(self):
        self.hide("google-chrome")
        self.write_config("devloops.local.json", {"playwright": {
            "mcp_command": ["npx", "@playwright/mcp@latest", "--browser", "chromium"],
            "executable_path": os.path.join(self.bin, "stale")}})
        for key in ("DISPLAY", "WAYLAND_DISPLAY"):
            self.env.pop(key, None)
        result = self.check()
        self.assertTrue(result["ready"])
        self.assertEqual(self.item(result, "browser")["status"], "ready")
        self.assertIn("mcp_command", self.item(result, "browser")["detail"])
        # No --headless in the explicit command: the browser is visible.
        self.assertEqual(self.item(result, "display")["status"], "warning")
        self.write_config("devloops.local.json", {"playwright": {
            "headless": False, "mcp_command": ["npx", "@playwright/mcp@latest", "--headless"]}})
        self.assertNotIn("display", [i["name"] for i in self.check()["items"]])

    def test_git_is_needed_only_for_per_milestone_commits(self):
        self.hide("git")
        result = self.check()
        self.assertTrue(result["ready"])
        self.assertEqual(self.item(result, "git")["status"], "ready")
        self.write_config("devloops.local.json", {"git": {"commit_per_milestone": True}})
        result = self.check()
        self.assertFalse(result["ready"])
        self.assertEqual(self.item(result, "git")["status"], "missing")

    def test_a_visible_browser_without_a_display_warns(self):
        self.write_config("devloops.local.json", {"playwright": {"headless": False}})
        for key in ("DISPLAY", "WAYLAND_DISPLAY"):
            self.env.pop(key, None)
        result = self.check()
        self.assertTrue(result["ready"])
        self.assertEqual(self.item(result, "display")["status"], "warning")
        self.assertNotIn("shared-visible-browser", [i["name"] for i in result["items"]])
        self.env["DISPLAY"] = ":0"
        self.assertNotIn("display", [i["name"] for i in self.check()["items"]])
        self.env.pop("DISPLAY")
        self.assertNotIn("display", [i["name"] for i in self.check(platform="darwin")["items"]])

    def test_a_visible_browser_in_the_shared_file_warns(self):
        self.write_config("devloops.json", {"playwright": {"headless": False}})
        self.env["DISPLAY"] = ":0"
        result = self.check()
        self.assertTrue(result["ready"])
        self.assertEqual(self.item(result, "shared-visible-browser")["status"], "warning")

    # --- the command ---

    def test_exit_codes_and_json_shape(self):
        code, out = self.cli("--json")
        result = json.loads(out)
        self.assertEqual(set(result), {"ready", "project", "loops", "items"})
        self.assertEqual(result["loops"], ["backend-dev", "frontend-dev"])
        self.assertEqual(result["project"], self.t.root)
        for item in result["items"]:
            self.assertEqual(set(item), {"name", "status", "detail", "fix", "needed_for"})
            self.assertIn(item["status"], ("ready", "missing", "warning"))
            self.assertTrue(set(item["needed_for"]) <= {"backend-dev", "frontend-dev", "all"})
        self.assertEqual(code, 0 if result["ready"] else 30)
        self.hide("claude")
        code, out = self.cli()
        self.assertEqual(code, 30, self.output)
        self.assertRegex(out, r"(?m)^  missing  claude +'claude --version' failed$")
        self.assertRegex(out, r"(?m)^           fix: install Claude Code")

    def test_outside_a_project(self):
        outside = os.path.join(self.t.base, "outside")
        os.makedirs(outside)
        code, out = self.cli("--json", cwd=outside)
        self.assertIsNone(json.loads(out)["project"])
        self.assertEqual(json.loads(out)["loops"], ["backend-dev", "frontend-dev"])
        self.assertIn(code, (0, 30))
        self.assertIsNone(self.check(project=False)["project"])
        self.env["DEVLOOPS_PROJECT"] = outside  # named explicitly, but not a project
        code, _ = self.cli(cwd=outside)
        self.assertEqual(code, 2, self.output)
        self.assertIn("DEVLOOPS_PROJECT", self.output)
        self.assertTrue(self.check(project=False)["ready"])

    # --- only the project's loops (003 FR-015) ---

    def test_a_backend_only_project_does_not_need_the_frontend_tools(self):
        self.targets = {"backend-dev": "backend", "frontend-dev": None}
        self.write_config("devloops.json", {"playwright": {"headless": False}})
        self.hide("npx")
        self.hide("google-chrome")
        for key in ("DISPLAY", "WAYLAND_DISPLAY"):
            self.env.pop(key, None)
        result = self.check()
        self.assertTrue(result["ready"])
        self.assertEqual(result["loops"], ["backend-dev"])
        for name in ("playwright-mcp", "browser", "display"):
            item = self.item(result, name)
            self.assertEqual(item["status"], "unused", item)
            self.assertEqual(item["detail"], "not used by this project (frontend-dev)")
            self.assertIsNone(item["fix"])
        self.assertEqual(self.item(result, "curl")["status"], "ready")
        code, out = self.cli()
        self.assertEqual(code, 0, self.output)
        self.assertRegex(out, r"(?m)^  unused   browser +not used by this project \(frontend-dev\)$")

    def test_a_frontend_only_project_does_not_need_curl(self):
        self.targets = {"backend-dev": None, "frontend-dev": "frontend"}
        self.write_config("devloops.json", {})
        self.hide("curl")
        result = self.check()
        self.assertTrue(result["ready"])
        self.assertEqual(self.item(result, "curl")["status"], "unused")

    def test_a_loop_recorded_in_the_default_workspace_stays_checked(self):
        from devloops import workspace
        ws = workspace.open_workspace(self.t.project().default_workspace, self.t.project(),
                                      self.t.kit())
        ws.set_target("frontend-dev", os.path.join(self.t.root, "frontend"))
        self.targets = {"backend-dev": "backend", "frontend-dev": None}  # null after recording
        self.write_config("devloops.json", {})
        self.hide("google-chrome")
        result = self.check()
        self.assertEqual(result["loops"], ["backend-dev", "frontend-dev"])  # as `run` selects
        self.assertEqual(self.item(result, "browser")["status"], "missing")
        self.assertFalse(result["ready"])

    def test_a_project_with_no_loop_is_not_ready(self):
        self.targets = {"backend-dev": None, "frontend-dev": None}
        self.write_config("devloops.json", {})
        result = self.check()
        self.assertFalse(result["ready"])
        self.assertEqual(result["loops"], [])
        item = self.item(result, "loops")
        self.assertEqual((item["status"], item["detail"]), ("missing",
                                                           "the project includes no loop"))
        self.assertIn("targets.backend-dev", item["fix"])
        self.assertEqual(self.item(result, "curl")["status"], "unused")
        code, _ = self.cli()
        self.assertEqual(code, 30, self.output)


if __name__ == "__main__":
    unittest.main()
