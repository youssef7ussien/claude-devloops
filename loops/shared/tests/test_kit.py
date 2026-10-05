"""Kit resolution and the skill command (002 research P-2, P-7)."""
import os
import shutil
import tempfile
import unittest

import helpers
from devloops import __version__, kit


class KitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = os.path.realpath(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_resolve_from_this_checkout_is_source_mode(self):
        k = kit.Kit.resolve()
        repo = os.path.realpath(helpers.REPO_ROOT)
        self.assertEqual(k.mode, "source")
        self.assertEqual(k.root, os.path.join(repo, "loops"))
        self.assertEqual(k.reserved, [os.path.join(repo, "loops"), os.path.join(repo, "bin")])
        self.assertEqual(k.version, __version__)

    def test_path_finds_packaged_files(self):
        k = kit.Kit.resolve()
        self.assertTrue(os.path.isfile(k.path("shared", "prompts", "common.md")))
        self.assertTrue(os.path.isfile(k.path("backend-dev", "loop.json")))
        self.assertTrue(os.path.isfile(k.path("shared", "schemas", "project-config.schema.json")))

    def test_command_when_the_checkout_is_the_project(self):
        k = kit.Kit.from_checkout(self.base)
        self.assertEqual(k.command_for(self.base), os.path.join("bin", "devloops"))

    def test_command_when_the_checkout_is_inside_the_project(self):
        project = os.path.join(self.base, "app")
        k = kit.Kit.from_checkout(os.path.join(project, "tools", "devloops"))
        self.assertEqual(k.command_for(project),
                         os.path.join("tools", "devloops", "bin", "devloops"))

    def test_command_when_the_checkout_is_elsewhere_is_absolute(self):
        k = kit.Kit.from_checkout(os.path.join(self.base, "checkout"))
        self.assertEqual(k.command_for(os.path.join(self.base, "app")),
                         os.path.join(self.base, "checkout", "bin", "devloops"))

    def test_installed_mode_command_is_devloops(self):
        root = os.path.join(self.base, "site", "devloops_kit")
        shutil.copytree(os.path.join(helpers.REPO_ROOT, "loops", "backend-dev"),
                        os.path.join(root, "backend-dev"))
        k = kit.Kit(root=root, mode="installed",
                    reserved=[root, os.path.join(self.base, "site", "devloops")])
        self.assertEqual(k.command_for(self.base), "devloops")
        self.assertTrue(os.path.isfile(k.path("backend-dev", "loop.json")))
        self.assertIn(root, k.reserved)


if __name__ == "__main__":
    unittest.main()
