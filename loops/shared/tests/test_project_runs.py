"""Running the loops in a project with its own defaults (002 US2: FR-008, FR-010, FR-013–FR-015;
quickstart §1 rows 4–10). backend-dev uses the stub validator, so no application is needed."""
import json
import os
import shutil
import unittest

import helpers
import samples
from devloops import state
from stub_loop import STUB, implemented


class ProjectRunsTest(unittest.TestCase):
    def setUp(self):
        self.t = helpers.TempEnv().__enter__()
        self.addCleanup(self.t.__exit__, None, None, None)
        loops = os.path.join(self.t.root, "loops")
        self.t.write_file(os.path.join("backend-dev", "loop.json"), json.dumps({
            "name": "backend-dev", "required_inputs": ["requirements"], "required_tools": [],
            "validator": "stub", "requires_openapi_path": False}), base=loops)
        self.t.write_file(os.path.join("shared", "devloops", "validators", "stub.py"), STUB,
                          base=loops)
        self.t.write_file("docs/prd.md", "# PRD\n\n- FR-1 list items\n- FR-2 create items\n",
                          base=self.t.root)
        self.configure()
        self.t.write_scenario({"steps": {"plan": {"structured_output": samples.plan()},
                                         "implement": [implemented("M01-T01"),
                                                       implemented("M02-T01")]}})

    def configure(self, **extra):
        config = {"targets": {"backend-dev": "backend", "frontend-dev": "frontend"},
                  "requirements": {"path": "docs/prd.md"}}
        config.update(extra)
        self.t.make_project(self.t.root, config)

    def write_local(self, data):
        self.t.write_file(".devloops/devloops.local.json", json.dumps(data), base=self.t.root)

    def cli(self, *args, root=None, cwd=None):
        root = root or self.t.root
        code, out, err = helpers.run_cli(list(args), env=self.t.env, root=root, cwd=cwd or root)
        self.output = out + err
        return code

    def ws_dir(self, name="main", root=None):
        return os.path.join(root or self.t.root, ".devloops", "workspaces", name)

    def run_state(self, name="main", root=None):
        return state.read_json(os.path.join(self.ws_dir(name, root), "backend-dev", "state",
                                            "run.json"))

    # --- defaults from the configuration (SC-002, FR-013) ---

    def test_orchestrate_from_a_subfolder_needs_no_flags(self):
        sub = os.path.join(self.t.root, "sub", "dir")
        os.makedirs(sub)
        self.assertEqual(self.cli("orchestrate", "--json", cwd=sub), 10, self.output)
        data = state.read_json(os.path.join(self.ws_dir(), "workspace.json"))
        self.assertEqual(data["targets"], {"backend-dev": "backend", "frontend-dev": "frontend"})
        self.assertEqual(data["requirements"]["path"], os.path.join("docs", "prd.md"))
        self.assertEqual(self.run_state()["target_dir"], os.path.join(self.t.root, "backend"))

    def test_run_writes_code_only_into_the_configured_target(self):
        self.assertEqual(self.cli("run", "backend-dev"), 10, self.output)
        self.assertEqual(self.cli("approve", "--no-continue", "backend-dev"), 0, self.output)
        self.assertEqual(self.cli("run", "backend-dev"), 0, self.output)
        self.assertTrue(os.path.isfile(os.path.join(self.t.root, "backend", "app.py")))
        self.assertFalse(os.path.exists(os.path.join(self.t.root, "app.py")))

    def test_flags_win_over_the_configuration(self):
        code = self.cli("run", "backend-dev", "--workspace", "other", "--target",
                        self.t.target_dir)
        self.assertEqual(code, 10, self.output)
        self.assertEqual(self.run_state("other")["target_dir"], self.t.target_dir)

    # --- precedence (FR-010) ---

    def test_precedence_of_the_configuration_layers(self):
        self.configure(config={"max_trials": 5})
        self.write_local({"config": {"max_trials": 4}})
        ws_config = self.t.write_file("ws-config.json", json.dumps({"max_trials": 3}))
        self.cli("run", "backend-dev", "--workspace", "layers")
        self.assertEqual(self.run_state("layers")["effective_config"]["max_trials"], 4)
        self.cli("run", "backend-dev", "--workspace", "with-config", "--config", ws_config)
        self.assertEqual(self.run_state("with-config")["effective_config"]["max_trials"], 3)
        self.cli("run", "backend-dev", "--workspace", "with-flag", "--config", ws_config,
                 "--max-trials", "2")
        rs = self.run_state("with-flag")
        self.assertEqual(rs["effective_config"]["max_trials"], 2)
        self.assertEqual(rs["config_cli_keys"], ["max_trials"])
        os.remove(os.path.join(self.t.root, ".devloops", "devloops.local.json"))
        self.cli("run", "backend-dev", "--workspace", "shared-only")
        self.assertEqual(self.run_state("shared-only")["effective_config"]["max_trials"], 5)

    # --- drift (FR-015) ---

    def status_json(self, *args):
        self.cli("status", "backend-dev", "--json", *args)
        return json.loads(self.output)

    def test_drift_is_reported_and_not_applied(self):
        self.configure(config={"max_trials": 3})
        self.assertEqual(self.cli("run", "backend-dev", "--max-trials", "2"), 10, self.output)
        self.assertEqual(self.status_json()["config_drift"], [])
        self.configure(config={"max_trials": 3, "max_invocations_per_run": 70})  # whitespace
        self.configure(config={"max_trials": 7, "max_invocations_per_run": 70})
        drift = self.status_json()["config_drift"]
        self.assertEqual(drift, ["max_invocations_per_run"])  # max_trials came from the CLI
        self.cli("status", "backend-dev")
        self.assertIn("configuration changed since the first run (not applied): "
                      "max_invocations_per_run", self.output)
        self.cli("run", "backend-dev")
        cfg = self.run_state()["effective_config"]
        self.assertEqual((cfg["max_trials"], cfg["max_invocations_per_run"]), (2, 60))

    def test_a_target_edit_after_the_first_run_is_drift_not_a_mismatch(self):
        self.assertEqual(self.cli("run", "backend-dev"), 10, self.output)
        self.configure(targets={"backend-dev": "api", "frontend-dev": "frontend"})
        self.assertEqual(self.cli("run", "backend-dev"), 10, self.output)
        self.assertEqual(self.run_state()["target_dir"], os.path.join(self.t.root, "backend"))

    # --- a moved project (FR-013) ---

    def test_a_moved_project_resumes_with_targets_under_the_new_root(self):
        self.assertEqual(self.cli("run", "backend-dev"), 10, self.output)
        moved = os.path.join(self.t.base, "moved")
        shutil.copytree(self.t.root, moved, symlinks=True)
        shutil.rmtree(self.t.root)
        self.t.env["DEVLOOPS_CLAUDE_BIN"] = os.path.join(moved, "loops", "shared", "tests",
                                                         "fake_claude.py")
        self.assertEqual(self.cli("approve", "--no-continue",
                                  "backend-dev", root=moved), 0, self.output)
        self.assertEqual(self.cli("run", "backend-dev", root=moved), 0, self.output)
        rs = self.run_state(root=moved)
        self.assertEqual(rs["status"], "completed")
        self.assertEqual(rs["project_root"], moved)
        self.assertEqual(rs["target_dir"], os.path.join(moved, "backend"))
        self.assertEqual(rs["inputs"]["requirements"]["path"],
                         os.path.join(moved, "docs", "prd.md"))
        self.assertTrue(os.path.isfile(os.path.join(moved, "backend", "app.py")))

    def clone(self):
        clone = os.path.join(self.t.base, "clone")
        shutil.copytree(self.t.root, clone, symlinks=True)
        return clone

    def test_replan_in_a_clone_uses_the_clone_and_leaves_the_original_alone(self):
        self.assertEqual(self.cli("run", "backend-dev"), 10, self.output)
        original = self.run_state()
        clone = self.clone()
        self.assertEqual(self.cli("replan", "--no-continue",
                                  "backend-dev", root=clone), 10, self.output)
        rs = self.run_state(root=clone)
        self.assertEqual(rs["project_root"], clone)
        self.assertEqual(rs["target_dir"], os.path.join(clone, "backend"))
        self.assertEqual(self.run_state(), original)
        plan_calls = [c for c in self.t.fake_calls() if c["step"] == "replan"]
        self.assertEqual(plan_calls[-1]["cwd"], os.path.join(clone, "backend"))

    def test_the_workspace_config_file_follows_a_moved_project(self):
        ws_config = self.t.write_file("ws-config.json", json.dumps({"max_trials": 3}),
                                      base=self.t.root)
        self.assertEqual(self.cli("run", "backend-dev", "--config", ws_config), 10, self.output)
        data = state.read_json(os.path.join(self.ws_dir(), "workspace.json"))
        self.assertEqual(data["config_path"], "ws-config.json")
        clone = self.clone()
        with open(os.path.join(clone, "ws-config.json"), "w") as f:
            json.dump({"max_trials": 4}, f)
        self.cli("status", "backend-dev", "--json", root=clone)
        self.assertEqual(json.loads(self.output)["config_drift"], ["max_trials"])
        self.cli("status", "backend-dev", "--json")
        self.assertEqual(json.loads(self.output)["config_drift"], [])

    # --- errors (FR-008, FR-014) ---

    def test_outside_any_project(self):
        self.assertEqual(self.cli("status", cwd=self.t.base), 2)
        self.assertIn("devloops init", self.output)

    def test_a_first_start_that_stopped_early_reuses_the_recorded_inputs(self):
        self.configure(targets={"backend-dev": "loops"})
        self.assertEqual(self.cli("run", "backend-dev"), 30, self.output)  # recorded requirements
        self.configure()
        self.assertEqual(self.cli("run", "backend-dev"), 10, self.output)

    def test_targets_that_overlap_devloops_or_the_kit_are_refused(self):
        for bad in (".devloops/x", "loops"):
            with self.subTest(target=bad):
                self.configure(targets={"backend-dev": bad})
                ws = "bad-" + bad.replace("/", "").replace(".", "")
                self.assertEqual(self.cli("run", "backend-dev", "--workspace", ws), 30,
                                 self.output)
                self.assertIn("overlaps", self.output)


if __name__ == "__main__":
    unittest.main()
