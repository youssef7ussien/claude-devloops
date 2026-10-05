import json
import os
import tempfile
import unittest

import helpers  # noqa: F401
from devloops import config, schema, state


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.loop_dir = os.path.join(self.dir, "backend-dev")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, obj):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(obj if isinstance(obj, str) else json.dumps(obj))
        return path

    def test_defaults_are_valid_and_have_no_stack_commands(self):
        defaults = state.read_json(config.DEFAULTS_PATH)
        self.assertEqual(schema.validate(defaults, "config.schema.json"), [])
        self.assertEqual(defaults["runtime"], {"ready_timeout_seconds": 120})
        self.assertEqual(defaults["backend"], {})
        self.assertIsNone(defaults["unit_tests"]["command"])

    def test_merge_order(self):
        ws = self.write("config.json", {"max_trials": 5, "runtime": {"base_url": "http://x"},
                                        "secrets": {"env": ["TOKEN"]}})
        eff = config.load_effective(config.DEFAULTS_PATH, ws, {"max_trials": 7})
        self.assertEqual(eff["max_trials"], 7)
        self.assertEqual(eff["runtime"], {"ready_timeout_seconds": 120, "base_url": "http://x"})
        self.assertEqual(eff["secrets"], {"env": ["TOKEN"], "literals": []})
        self.assertEqual(eff["invocation_timeout_seconds"], 1800)

    def test_unset_cli_flags_do_not_override(self):
        eff = config.load_effective(config.DEFAULTS_PATH, None, {"max_trials": None,
                                                                 "runtime": {"cwd": None}})
        self.assertEqual(eff["max_trials"], 3)
        self.assertNotIn("cwd", eff["runtime"])

    def test_lists_replace(self):
        eff = config.load_effective(config.DEFAULTS_PATH, None, {"implement_tools": ["Read"]})
        self.assertEqual(eff["implement_tools"], ["Read"])

    def test_invalid_config_exits_2_listing_every_error(self):
        ws = self.write("config.json", {"max_trials": 0, "unknown": 1})
        with self.assertRaises(config.ConfigError) as cm:
            config.load_effective(config.DEFAULTS_PATH, ws, {})
        self.assertEqual(cm.exception.exit_code, 2)
        self.assertEqual(len(cm.exception.errors), 2)
        self.assertIn("unknown", str(cm.exception))

    def test_unreadable_or_bad_json_config(self):
        with self.assertRaises(config.ConfigError):
            config.load_effective(config.DEFAULTS_PATH, os.path.join(self.dir, "missing.json"), {})
        with self.assertRaises(config.ConfigError):
            config.load_effective(config.DEFAULTS_PATH, self.write("bad.json", "{nope"), {})
        with self.assertRaises(config.ConfigError):
            config.load_effective(config.DEFAULTS_PATH, self.write("list.json", "[]"), {})

    def test_first_run_freezes_effective_config(self):
        run = {}
        eff = config.resolve_for_run(run, self.loop_dir, {"max_trials": 4})
        self.assertEqual(run["effective_config"], eff)
        self.assertEqual(eff["max_trials"], 4)
        self.assertEqual(state.read_jsonl(os.path.join(self.loop_dir, "state", "events.jsonl")), [])

    def test_later_workspace_edits_do_not_apply(self):
        ws = self.write("config.json", {"max_trials": 5})
        run = {}
        config.resolve_for_run(run, self.loop_dir, {}, workspace_config_path=ws)
        self.write("config.json", {"max_trials": 9})
        eff = config.resolve_for_run(run, self.loop_dir, {}, workspace_config_path=ws)
        self.assertEqual(eff["max_trials"], 5)

    def test_later_cli_override_is_applied_and_recorded(self):
        run = {}
        config.resolve_for_run(run, self.loop_dir, {})
        eff = config.resolve_for_run(run, self.loop_dir, {"max_trials": 6})
        self.assertEqual(eff["max_trials"], 6)
        self.assertEqual(run["effective_config"]["max_trials"], 6)
        events = state.read_jsonl(os.path.join(self.loop_dir, "state", "events.jsonl"))
        self.assertEqual([e["type"] for e in events], ["config-override"])
        self.assertIn("max_trials = 6", events[0]["message"])

    def test_same_cli_value_again_records_nothing(self):
        run = {}
        config.resolve_for_run(run, self.loop_dir, {"max_trials": 6})
        config.resolve_for_run(run, self.loop_dir, {"max_trials": 6})
        self.assertEqual(state.read_jsonl(os.path.join(self.loop_dir, "state", "events.jsonl")), [])

    def test_invalid_later_override_exits_2(self):
        run = {}
        config.resolve_for_run(run, self.loop_dir, {})
        with self.assertRaises(config.ConfigError):
            config.resolve_for_run(run, self.loop_dir, {"max_trials": 0})
        self.assertEqual(run["effective_config"]["max_trials"], 3)



class McpCommandTest(unittest.TestCase):
    """The derived Playwright MCP command (002 research P-15, FR-017)."""

    def cfg(self, **playwright):
        return {"playwright": playwright}

    def test_default_is_headless_npx(self):
        defaults = state.read_json(config.DEFAULTS_PATH)
        self.assertEqual(config.mcp_command(defaults),
                         ["npx", "@playwright/mcp@latest", "--headless"])
        self.assertEqual(config.mcp_command({}), ["npx", "@playwright/mcp@latest", "--headless"])

    def test_visible_browser_drops_headless(self):
        self.assertEqual(config.mcp_command(self.cfg(headless=False)),
                         ["npx", "@playwright/mcp@latest"])

    def test_executable_path_is_appended(self):
        self.assertEqual(config.mcp_command(self.cfg(executable_path="/usr/bin/chromium")),
                         ["npx", "@playwright/mcp@latest", "--headless", "--executable-path",
                          "/usr/bin/chromium"])

    def test_an_explicit_command_is_used_unchanged(self):
        explicit = ["my-mcp", "--port", "1"]
        self.assertEqual(config.mcp_command(self.cfg(mcp_command=explicit, headless=False,
                                                     executable_path="/x")), explicit)

    def test_a_frozen_001_configuration_behaves_as_before(self):
        frozen = {"playwright": {"mcp_command": ["npx", "@playwright/mcp@latest", "--headless"]}}
        self.assertEqual(schema.validate(frozen, "config.schema.json"), [])
        self.assertEqual(config.mcp_command(frozen),
                         ["npx", "@playwright/mcp@latest", "--headless"])

    def test_the_new_keys_validate(self):
        self.assertEqual(schema.validate(self.cfg(headless=False, executable_path=None,
                                                  mcp_command=None), "config.schema.json"), [])
        self.assertNotEqual(schema.validate(self.cfg(headless="no"), "config.schema.json"), [])


if __name__ == "__main__":
    unittest.main()
