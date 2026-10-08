"""Choosing the loops a run includes, and the checks before anything runs (003 FR-005, FR-005a,
FR-006; research R-2, R-3)."""
import json
import os
import tempfile
import unittest

import helpers  # noqa: F401
from devloops import kit, project, state, workspace
from devloops.orchestrator import check_selection, select_loops


class SelectLoopsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = os.path.realpath(self.tmp.name)
        self.repo = os.path.join(self.base, "repo")
        for d in ("loops", "bin", "workspaces"):
            os.makedirs(os.path.join(self.repo, d))
        self.kit = kit.Kit.from_checkout(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def project(self, targets=None):
        data = {"schema_version": 1, "workspaces_dir": "workspaces"}
        if targets is not None:
            data["targets"] = targets
        os.makedirs(os.path.join(self.repo, ".devloops"), exist_ok=True)
        with open(os.path.join(self.repo, ".devloops", "devloops.json"), "w") as f:
            json.dump(data, f)
        return project.Project(self.repo)

    def path(self, *parts):
        return os.path.join(self.repo, *parts)

    def workspace(self, proj, **targets):
        ws = workspace.open_workspace("main", proj, self.kit)
        for loop, target in targets.items():
            ws.set_target(loop.replace("_", "-"), target)
        return ws

    # --- the project configuration ---

    def test_both_targets(self):
        proj = self.project({"backend-dev": "backend", "frontend-dev": "frontend"})
        self.assertEqual(select_loops(proj), {"backend-dev": self.path("backend"),
                                              "frontend-dev": self.path("frontend")})

    def test_order_is_backend_then_frontend(self):
        proj = self.project({"frontend-dev": "frontend", "backend-dev": "backend"})
        self.assertEqual(list(select_loops(proj)), ["backend-dev", "frontend-dev"])

    def test_null_frontend_is_backend_only(self):
        proj = self.project({"backend-dev": "backend", "frontend-dev": None})
        self.assertEqual(select_loops(proj), {"backend-dev": self.path("backend")})

    def test_missing_key_means_not_used(self):
        proj = self.project({"backend-dev": "backend"})
        self.assertEqual(list(select_loops(proj)), ["backend-dev"])

    def test_no_targets_selects_nothing(self):
        self.assertEqual(select_loops(self.project()), {})
        self.assertEqual(select_loops(self.project({"backend-dev": None, "frontend-dev": None})),
                         {})

    # --- flags ---

    def test_explicit_flag_turns_on_a_null_loop(self):
        proj = self.project({"backend-dev": "backend", "frontend-dev": None})
        selected = select_loops(proj, frontend_target=self.path("web"))
        self.assertEqual(selected["frontend-dev"], self.path("web"))

    def test_flag_overrides_the_project_folder(self):
        proj = self.project({"backend-dev": "backend"})
        self.assertEqual(select_loops(proj, backend_target=self.path("api")),
                         {"backend-dev": self.path("api")})

    def test_target_root_places_only_the_project_loops(self):
        proj = self.project({"backend-dev": "backend", "frontend-dev": None})
        root = os.path.join(self.base, "apps")
        self.assertEqual(select_loops(proj, target_root=root),
                         {"backend-dev": os.path.join(root, "backend")})

    def test_target_root_places_both(self):
        proj = self.project({"backend-dev": "api", "frontend-dev": "web"})
        root = os.path.join(self.base, "apps")
        self.assertEqual(select_loops(proj, target_root=root),
                         {"backend-dev": os.path.join(root, "backend"),
                          "frontend-dev": os.path.join(root, "frontend")})

    # --- the workspace ---

    def test_recorded_target_wins_over_the_project(self):
        proj = self.project({"backend-dev": "backend", "frontend-dev": None})
        ws = self.workspace(proj, backend_dev=self.path("old-api"),
                            frontend_dev=self.path("old-web"))
        # Recorded loops stay included, even one the project now sets to null.
        self.assertEqual(select_loops(proj, ws), {"backend-dev": self.path("old-api"),
                                                  "frontend-dev": self.path("old-web")})

    def test_target_root_does_not_move_a_recorded_loop(self):
        proj = self.project({"backend-dev": "backend"})
        ws = self.workspace(proj, backend_dev=self.path("api"))
        self.assertEqual(select_loops(proj, ws, target_root=os.path.join(self.base, "apps")),
                         {"backend-dev": self.path("api")})

    def test_same_flag_as_recorded_is_accepted(self):
        proj = self.project({"backend-dev": "backend"})
        ws = self.workspace(proj, backend_dev=self.path("api"))
        self.assertEqual(select_loops(proj, ws, backend_target=self.path("api")),
                         {"backend-dev": self.path("api")})

    def test_different_flag_than_recorded_is_a_usage_error(self):
        proj = self.project({"backend-dev": "backend"})
        ws = self.workspace(proj, backend_dev=self.path("api"))
        with self.assertRaises(state.UsageError) as cm:
            select_loops(proj, ws, backend_target=self.path("other"))
        self.assertIn("--backend-target", cm.exception.message)
        self.assertIn("recorded", cm.exception.message)
        self.assertEqual(cm.exception.exit_code, 2)

    # --- check_selection ---

    def test_no_loop_stops_with_exit_30(self):
        with self.assertRaises(state.StopRun) as cm:
            check_selection({})
        self.assertEqual((cm.exception.code, cm.exception.exit_code), ("no-loop", 30))
        self.assertIn("no loop to run", cm.exception.message)

    def test_frontend_without_backend_stops_with_exit_30(self):
        with self.assertRaises(state.StopRun) as cm:
            check_selection({"frontend-dev": self.path("web")})
        self.assertEqual((cm.exception.code, cm.exception.exit_code),
                         ("frontend-needs-backend", 30))
        self.assertIn("frontend-only runs are not supported yet", cm.exception.message)

    def test_valid_selections_pass(self):
        check_selection({"backend-dev": self.path("api")})
        check_selection({"backend-dev": self.path("api"), "frontend-dev": self.path("web")})


if __name__ == "__main__":
    unittest.main()
