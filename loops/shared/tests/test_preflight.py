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

    def test_all_present(self):
        self.tool("claude")
        self.tool("curl")
        self.tool("npx")
        preflight.check_tools({"required_tools": ["curl", "playwright-mcp"]}, self.config, self.env())

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
