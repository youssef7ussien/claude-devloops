"""This repository is an initialized project whose skills come from the kit's templates (FR-022)."""
import json
import os
import unittest

import helpers
from devloops import initcmd, kit

SKILLS_DIR = os.path.join(helpers.REPO_ROOT, ".claude", "skills")


class RepoSkillsTest(unittest.TestCase):
    def setUp(self):
        self.rendered = initcmd.render_skills(kit.Kit.resolve(), helpers.REPO_ROOT)

    def test_six_skills_are_rendered(self):
        self.assertEqual(len(self.rendered), 6)

    def test_the_orchestrate_skill_is_gone(self):  # 003 FR-017
        self.assertFalse(os.path.exists(os.path.join(SKILLS_DIR, "devloops-orchestrate")))

    def test_repository_skills_equal_the_rendered_templates(self):
        for rel, text in self.rendered.items():
            with self.subTest(skill=rel):
                with open(os.path.join(helpers.REPO_ROOT, rel), encoding="utf-8") as f:
                    self.assertEqual(f.read(), text, f"{rel} differs from its template; run "
                                     "`bin/devloops init --upgrade` or re-render it")

    def test_no_old_loops_skills_remain(self):
        self.assertEqual([n for n in os.listdir(SKILLS_DIR) if n.startswith("loops-")], [])

    def test_manifest_lists_them(self):
        with open(os.path.join(helpers.REPO_ROOT, ".devloops", "manifest.json")) as f:
            manifest = json.load(f)
        for rel in self.rendered:
            self.assertIn(rel.replace(os.sep, "/"), manifest["files"])
        self.assertEqual(manifest["command"], os.path.join("bin", "devloops"))


if __name__ == "__main__":
    unittest.main()
