"""Project discovery and the project configuration files (002 FR-008, FR-012, FR-016)."""
import json
import os
import tempfile
import unittest

import helpers
from devloops import project, state


class ProjectTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = os.path.realpath(self.tmp.name)
        self.root = os.path.join(self.base, "app")
        self.write_config({"schema_version": 1})

    def tearDown(self):
        self.tmp.cleanup()

    def write_config(self, data, name="devloops.json", root=None):
        path = os.path.join(root or self.root, ".devloops", name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(data if isinstance(data, str) else json.dumps(data))
        return path

    # --- discovery ---

    def test_found_from_a_nested_subfolder(self):
        nested = os.path.join(self.root, "src", "deep")
        os.makedirs(nested)
        self.assertEqual(project.find(nested, env={}).root, self.root)

    def test_the_nearest_of_two_nested_projects_wins(self):
        inner = os.path.join(self.root, "packages", "inner")
        self.write_config({"schema_version": 1}, root=inner)
        start = os.path.join(inner, "src")
        os.makedirs(start)
        self.assertEqual(project.find(start, env={}).root, inner)

    def test_a_dot_devloops_folder_without_the_config_is_not_a_project(self):
        os.remove(os.path.join(self.root, ".devloops", "devloops.json"))
        with self.assertRaises(state.UsageError):
            project.find(self.root, env={})

    def test_devloops_project_overrides_the_search(self):
        other = os.path.join(self.base, "other")
        os.makedirs(other)
        found = project.find(other, env={"DEVLOOPS_PROJECT": self.root})
        self.assertEqual(found.root, self.root)

    def test_no_project_is_a_usage_error_suggesting_init(self):
        outside = os.path.join(self.base, "outside")
        os.makedirs(outside)
        with self.assertRaises(state.UsageError) as cm:
            project.find(outside, env={})
        self.assertEqual(cm.exception.exit_code, 2)
        self.assertIn("devloops init", cm.exception.message)
        with self.assertRaises(state.UsageError):
            project.find(outside, env={"DEVLOOPS_PROJECT": outside})

    # --- validation (FR-016) ---

    def assert_invalid(self, data, *needles, name="devloops.json"):
        path = self.write_config(data, name=name)
        with self.assertRaises(project.ProjectConfigError) as cm:
            project.Project(self.root).merged
        self.assertEqual(cm.exception.exit_code, 30)
        self.assertIn(path, cm.exception.message)
        for needle in needles:
            self.assertIn(needle, cm.exception.message)

    def test_invalid_json(self):
        self.assert_invalid("{nope", "not valid JSON")

    def test_unknown_key(self):
        self.assert_invalid({"schema_version": 1, "worksapce": "x"}, "worksapce")

    def test_a_removed_key_says_it_was_removed(self):
        self.assert_invalid({"schema_version": 1, "dashboards_dir": ".devloops/dashboards"},
                            '"dashboards_dir" was removed (the dashboard is served or exported '
                            'now); delete it')
        self.assert_invalid({"schema_version": 1, "config": {"dashboard": {"light": False}}},
                            '"dashboard" was removed')

    def test_wrong_type(self):
        self.assert_invalid({"schema_version": 1, "targets": {"backend-dev": 3}},
                            "targets.backend-dev")

    def test_unknown_run_config_key(self):
        self.assert_invalid({"schema_version": 1, "config": {"max_trails": 2}}, "max_trails")

    def test_requirements_with_both_forms(self):
        self.assert_invalid({"schema_version": 1,
                             "requirements": {"path": "prd.md", "speckit_feature": "active"}},
                            "requirements", "exactly one")

    def test_requirements_with_neither_form(self):
        self.assert_invalid({"schema_version": 1, "requirements": {}}, "requirements",
                            "exactly one")

    def test_story_file_without_path(self):
        self.assert_invalid({"schema_version": 1,
                             "requirements": {"speckit_feature": "active", "story_file": True}},
                            "story_file")

    def test_invalid_local_file_names_its_own_path(self):
        self.assert_invalid({"targets": {"backend-dev": False}}, "targets.backend-dev",
                            name="devloops.local.json")

    # --- merge and values ---

    def test_local_file_is_deep_merged_over_the_shared_one(self):
        self.write_config({"schema_version": 1, "workspace": "shared",
                           "targets": {"backend-dev": "api", "frontend-dev": "web"},
                           "requirements": {"path": "prd.md", "story_file": True},
                           "config": {"max_trials": 2, "playwright": {"mcp_command": ["a"]}}})
        self.write_config({"targets": {"frontend-dev": "ui"},
                           "requirements": {"speckit_feature": "active"},
                           "config": {"max_trials": 5}}, name="devloops.local.json")
        p = project.Project(self.root)
        self.assertEqual(p.default_workspace, "shared")
        self.assertEqual(p.targets, {"backend-dev": os.path.join(self.root, "api"),
                                     "frontend-dev": os.path.join(self.root, "ui")})
        self.assertEqual(p.requirements, {"speckit_feature": "active"})  # replaced whole
        self.assertEqual(p.run_config_layers(),
                         [{"max_trials": 2, "playwright": {"mcp_command": ["a"]}},
                          {"max_trials": 5}])

    def test_defaults(self):
        p = project.Project(self.root)
        self.assertEqual(p.default_workspace, "main")
        self.assertEqual(p.workspaces_dir, os.path.join(self.root, ".devloops", "workspaces"))
        self.assertEqual(p.targets, {"backend-dev": None, "frontend-dev": None})
        self.assertIsNone(p.requirements)
        self.assertEqual(p.run_config_layers(), [{}, {}])
        self.assertIsNone(p.manifest())

    def test_configured_directories_resolve_against_the_root(self):
        self.write_config({"schema_version": 1, "workspaces_dir": "workspaces",
                           "requirements": {"path": "docs/prd.md"}})
        p = project.Project(self.root)
        self.assertEqual(p.workspaces_dir, os.path.join(self.root, "workspaces"))
        self.assertEqual(p.requirements, {"path": os.path.join(self.root, "docs", "prd.md")})

    def test_relative_or_absolute_round_trips(self):
        p = project.Project(self.root)
        inside = os.path.join(self.root, "backend")
        self.assertEqual(p.relative_or_absolute(inside), "backend")
        self.assertEqual(p.resolve(p.relative_or_absolute(inside)), inside)
        self.assertEqual(p.relative_or_absolute("backend"), "backend")
        outside = os.path.join(self.base, "elsewhere")
        self.assertEqual(p.relative_or_absolute(outside), outside)
        self.assertEqual(p.resolve(outside), outside)


class ProjectCliTest(unittest.TestCase):
    """How every command finds and checks its project (T014)."""

    def setUp(self):
        self.t = helpers.TempEnv(symlink=True).__enter__()
        self.addCleanup(self.t.__exit__, None, None, None)

    def write_manifest(self, version):
        with open(os.path.join(self.t.root, ".devloops", "manifest.json"), "w") as f:
            json.dump({"schema_version": 1, "devloops_version": version, "files": {}}, f)

    def test_version_mismatch_warns_on_stderr_and_in_json(self):
        self.write_manifest("0.0.1")
        code, out, err = self.t.run_cli(["status", "--workspace", "w1"])
        self.assertIn('devloops: warning: this project was set up with devloops 0.0.1; running',
                      err)
        self.assertIn('"devloops init --upgrade"', err)
        code, out, err = self.t.run_cli(["status", "--workspace", "w1", "--json"])
        self.assertIn("set up with devloops 0.0.1", json.loads(out)["warnings"][0])
        self.assertNotIn("warning", err)

    def test_same_version_does_not_warn(self):
        from devloops import __version__
        self.write_manifest(__version__)
        code, out, err = self.t.run_cli(["status", "--workspace", "w1", "--json"])
        self.assertNotIn("warnings", json.loads(out))
        self.assertNotIn("warning", err)

    def test_invalid_project_config_stops_before_any_workspace_is_written(self):
        self.t.make_project(self.t.root, {"workspaces_dir": "workspaces", "bogus": 1})
        code, out, err = self.t.run_cli(["run", "--workspace", "w1",
                                         "--requirements", "x.md", "--backend-target",
                                         self.t.target_dir])
        self.assertEqual(code, 30, out + err)
        self.assertIn("devloops.json", err)
        self.assertIn("bogus", err)
        self.assertFalse(os.path.exists(os.path.join(self.t.root, "workspaces", "w1")))

    def test_workspace_defaults_to_the_project_setting(self):
        self.t.make_project(self.t.root, {"workspaces_dir": "workspaces", "workspace": "dflt"})
        self.t.run_cli(["run", "--backend-target", self.t.target_dir])
        self.assertTrue(os.path.isfile(os.path.join(self.t.root, "workspaces", "dflt",
                                                    "workspace.json")))

    def test_runs_from_a_subfolder(self):
        sub = os.path.join(self.t.root, "src", "deep")
        os.makedirs(sub)
        code, out, err = self.t.run_cli(["status", "--workspace", "nope"], cwd=sub)
        self.assertEqual(code, 2)
        self.assertIn(os.path.join(self.t.root, "workspaces", "nope"), err)


if __name__ == "__main__":
    unittest.main()
