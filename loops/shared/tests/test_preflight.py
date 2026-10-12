import os
import stat
import sys
import tempfile
import unittest

import helpers
import samples
from devloops import preflight, state


class PreflightTest(unittest.TestCase):
    """Each test builds a PATH that holds exactly the tools it wants to exist."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bin = os.path.join(self.tmp.name, "bin")
        os.makedirs(self.bin)
        self.config = samples.config()

    def tearDown(self):
        self.tmp.cleanup()

    def tool(self, name, exit_code=0):
        path = os.path.join(self.bin, name)
        with open(path, "w") as f:
            f.write(f"#!/bin/sh\necho {name} 1.0\nexit {exit_code}\n")
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
        return path

    def env(self, **extra):
        return {"PATH": self.bin, **extra}

    def assert_missing(self, loop_def, tool, env=None):
        with self.assertRaises(state.StopRun) as cm:
            preflight.check_tools(loop_def, self.config, env or self.env())
        self.assertEqual((cm.exception.code, cm.exception.details), ("missing-tool", {"tool": tool}))
        self.assertEqual(cm.exception.status, "stopped-on-input-error")

    def check(self, loop_def, env=None):
        """`check_tools` with no browser outside the test's PATH."""
        preflight.check_tools(loop_def, self.config, env or self.env(), browser_paths=(),
                              chromium_paths=())

    def test_all_present(self):
        self.tool("claude")
        self.tool("curl")
        self.tool("npx")
        self.tool("google-chrome")
        self.check({"required_tools": ["curl", "playwright-mcp"]})

    def test_the_browser_is_checked_before_a_run(self):
        """Spec 002 FR-018a: a missing browser stops the run before anything is spent,
        and the message says how to fix it, naming an installed Chromium."""
        self.tool("claude")
        self.tool("npx")
        self.config["playwright"] = {"headless": True}  # the default server, which starts Chrome
        loop_def = {"required_tools": ["playwright-mcp"]}
        with self.assertRaises(state.StopRun) as cm:
            self.check(loop_def)
        self.assertEqual((cm.exception.code, cm.exception.details),
                         ("missing-tool", {"tool": "browser"}))
        self.assertIn("npx playwright install chrome", cm.exception.message)
        chromium = self.tool("chromium")
        with self.assertRaises(state.StopRun) as cm:
            self.check(loop_def)
        self.assertIn(f"Chromium is at {chromium}", cm.exception.message)
        self.assertIn(f'"executable_path": "{chromium}"', cm.exception.message)
        self.config["playwright"]["executable_path"] = chromium
        self.check(loop_def)
        self.config["playwright"]["executable_path"] = os.path.join(self.bin, "gone")
        with self.assertRaises(state.StopRun) as cm:
            self.check(loop_def)
        self.assertIn("is not an executable file", cm.exception.message)
        # An explicit MCP command chooses its own browser: nothing to check.
        self.tool("my-mcp")
        self.config["playwright"]["mcp_command"] = ["my-mcp"]
        self.check(loop_def)

    def test_all_present_with_the_default_server_needs_chrome(self):
        self.tool("claude")
        self.tool("npx")
        self.config["playwright"] = {"headless": True}
        self.tool("google-chrome")
        self.check({"required_tools": ["playwright-mcp"]})

    def test_claude_missing_or_failing(self):
        self.assert_missing({}, "claude")
        self.tool("claude", exit_code=1)
        self.assert_missing({}, "claude")

    def test_claude_bin_override(self):
        env = self.env(DEVLOOPS_CLAUDE_BIN=helpers.FAKE_CLAUDE)
        env["PATH"] += os.pathsep + os.path.dirname(sys.executable)  # for its python3 shebang
        preflight.check_tools({}, self.config, env)

    def test_curl_required_only_when_listed(self):
        self.tool("claude")
        preflight.check_tools({}, self.config, self.env())
        self.assert_missing({"required_tools": ["curl"]}, "curl")

    def test_playwright_mcp_uses_configured_command(self):
        self.tool("claude")
        self.assert_missing({"required_tools": ["playwright-mcp"]}, "playwright-mcp")
        self.tool("my-mcp")
        self.config["playwright"]["mcp_command"] = ["my-mcp", "--headless"]
        preflight.check_tools({"required_tools": ["playwright-mcp"]}, self.config, self.env())

    def test_other_tools_must_be_on_path(self):
        self.tool("claude")
        self.assert_missing({"required_tools": ["jq"]}, "jq")


if __name__ == "__main__":
    unittest.main()
