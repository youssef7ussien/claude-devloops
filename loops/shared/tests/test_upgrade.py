"""`devloops init --upgrade` (002 US6: FR-027 to FR-029, SC-004; data-model "Install manifest")."""
import contextlib
import hashlib
import io
import json
import os
import unittest

import helpers
from devloops import cli, initcmd, kit as kit_mod

RUN_SKILL = os.path.join(".claude", "skills", "devloops-run", "SKILL.md")
STATUS_SKILL = os.path.join(".claude", "skills", "devloops-status", "SKILL.md")
README = os.path.join(".devloops", "prompts", "README.md")
MANIFEST = os.path.join(".devloops", "manifest.json")
CONFIG = os.path.join(".devloops", "devloops.json")


def sha(data):
    return hashlib.sha256(data).hexdigest()


class UpgradeTest(unittest.TestCase):
    def setUp(self):
        # A copy of the kit whose templates the test edits to simulate a new release.
        self.t = helpers.TempEnv().__enter__()
        self.addCleanup(self.t.__exit__, None, None, None)
        self.old = kit_mod.Kit.from_checkout(self.t.root, version="0.2.0")
        self.new = kit_mod.Kit.from_checkout(self.t.root, version="0.3.0")
        self.dir = os.path.join(self.t.base, "app")
        os.makedirs(self.dir)
        self.assertEqual(self.cli(["init", self.dir, "--no-prompt"], self.old)[0], 0, self.output)

    def cli(self, argv, kit, project=None):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(argv, kit=kit, project=project, env=self.t.env)
        self.output = out.getvalue() + err.getvalue()
        return code, out.getvalue()

    def upgrade(self, *args, kit=None):
        code, out = self.cli(["init", self.dir, "--upgrade", "--json", *args], kit or self.new)
        return code, json.loads(out)

    def path(self, rel):
        return os.path.join(self.dir, rel)

    def read(self, rel, base=None):
        with open(os.path.join(base or self.dir, rel), "rb") as f:
            return f.read()

    def write(self, rel, text, base=None):
        path = os.path.join(base or self.dir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def release(self, template, text):
        """Change a kit template, as a new release would."""
        self.write(template, text, base=self.t.root)

    def manifest(self):
        return json.loads(self.read(MANIFEST))

    # --- the installed files ---

    def test_unchanged_files_are_replaced_and_changed_ones_kept(self):
        skill = os.path.join("loops", "shared", "skills", "devloops-run", "SKILL.md")
        old_run = self.read(RUN_SKILL)
        self.release(skill, self.read(skill, self.t.root).decode() + "\nNew in 0.3.0.\n")
        self.release(os.path.join("loops", "shared", "skills", "devloops-status", "SKILL.md"),
                     "---\nname: \"devloops-status\"\n---\nnew status skill\n")
        self.write(STATUS_SKILL, "my own status skill\n")
        code, result = self.upgrade()
        self.assertEqual(code, 0, self.output)
        self.assertIn(RUN_SKILL, result["changed"])
        self.assertEqual(self.read(RUN_SKILL), old_run + b"\nNew in 0.3.0.\n")
        self.assertEqual(result["kept"], [{"path": STATUS_SKILL,
                                           "new_version": STATUS_SKILL + ".devloops-new"}])
        self.assertEqual(self.read(STATUS_SKILL), b"my own status skill\n")
        self.assertEqual(self.read(STATUS_SKILL + ".devloops-new"),
                         b"---\nname: \"devloops-status\"\n---\nnew status skill\n")
        self.assertNotIn(README, result["changed"])  # the same in both versions

    def test_a_changed_file_the_release_did_not_touch_is_left_alone(self):
        self.write(RUN_SKILL, "my own run skill\n")
        for _ in range(2):
            code, result = self.upgrade()
            self.assertEqual(code, 0, self.output)
            self.assertEqual(result["kept"], [])
            self.assertFalse(os.path.exists(self.path(RUN_SKILL + ".devloops-new")))
        self.assertEqual(self.read(RUN_SKILL), b"my own run skill\n")

    def test_the_new_prompts_readme_is_not_an_ignored_override(self):
        from devloops import prompts
        self.write(README, "my notes\n")
        self.release(os.path.join("loops", "shared", "project", "prompts", "README.md"),
                     "new README\n")
        code, result = self.upgrade()
        self.assertEqual(code, 0, self.output)
        self.assertEqual(result["kept"], [{"path": README,
                                           "new_version": README + ".devloops-new"}])
        self.assertEqual(prompts.ignored(self.dir), [])

    def test_a_deleted_file_is_reported_and_restored_only_on_request(self):
        os.remove(self.path(RUN_SKILL))
        code, result = self.upgrade()
        self.assertEqual(code, 0, self.output)
        self.assertEqual(result["deleted"], [RUN_SKILL])
        self.assertFalse(os.path.exists(self.path(RUN_SKILL)))
        self.assertIn(RUN_SKILL, self.manifest()["files"])  # still reported next time
        code, result = self.upgrade("--restore")
        self.assertEqual(code, 0, self.output)
        self.assertEqual(result["deleted"], [])
        self.assertIn(RUN_SKILL, result["created"])
        self.assertTrue(os.path.isfile(self.path(RUN_SKILL)))

    def test_a_template_added_to_the_kit_is_created(self):
        self.release(os.path.join("loops", "shared", "skills", "devloops-check", "SKILL.md"),
                     "---\nname: \"devloops-check\"\n---\n{{DEVLOOPS}} check $ARGUMENTS --json\n")
        added = os.path.join(".claude", "skills", "devloops-check", "SKILL.md")
        code, result = self.upgrade()
        self.assertEqual(code, 0, self.output)
        self.assertEqual(result["created"], [added])
        self.assertIn(self.new.command_for(self.dir).encode(), self.read(added))
        self.assertIn(added, self.manifest()["files"])

    def test_a_new_template_over_a_different_file_is_a_conflict(self):
        self.release(os.path.join("loops", "shared", "skills", "devloops-check", "SKILL.md"),
                     "new\n")
        self.write(os.path.join(".claude", "skills", "devloops-check", "SKILL.md"), "mine\n")
        before = self.read(MANIFEST)
        code, result = self.upgrade()
        self.assertEqual(code, 30, self.output)
        self.assertIn("init-conflict", result["message"])
        self.assertEqual(self.read(MANIFEST), before)

    def test_a_template_removed_from_the_kit_is_removed_only_if_unchanged(self):
        kit_skills = os.path.join(self.t.root, "loops", "shared", "skills")
        os.remove(os.path.join(kit_skills, "devloops-run", "SKILL.md"))
        os.remove(os.path.join(kit_skills, "devloops-status", "SKILL.md"))
        self.write(STATUS_SKILL, "changed here\n")
        code, result = self.upgrade()
        self.assertEqual(code, 0, self.output)
        self.assertEqual(result["removed"], [RUN_SKILL])
        self.assertFalse(os.path.exists(os.path.dirname(self.path(RUN_SKILL))))
        self.assertIn({"path": STATUS_SKILL, "new_version": None}, result["kept"])
        self.assertEqual(self.read(STATUS_SKILL), b"changed here\n")
        files = self.manifest()["files"]
        self.assertNotIn(RUN_SKILL, files)
        self.assertNotIn(STATUS_SKILL, files)

    # --- what an upgrade never changes ---

    def test_the_configuration_and_the_gitignore_block_are_untouched(self):
        self.write(CONFIG, self.read(CONFIG).decode().replace('"main"', '"mine"'))
        config, gitignore = self.read(CONFIG), self.read(".gitignore")
        self.assertEqual(self.upgrade()[0], 0, self.output)
        self.assertEqual(self.upgrade()[0], 0, self.output)
        self.assertEqual(self.read(CONFIG), config)
        self.assertEqual(self.read(".gitignore"), gitignore)
        self.assertEqual(gitignore.decode().count(initcmd.IGNORE_BEGIN), 1)

    def test_the_manifest_records_the_new_version(self):
        installed = self.manifest()
        self.assertEqual(installed["devloops_version"], "0.2.0")
        self.assertIsNone(installed["upgraded_at"])
        readme = os.path.join("loops", "shared", "project", "prompts", "README.md")
        self.release(readme, "new README\n")
        self.assertEqual(self.upgrade()[0], 0, self.output)
        upgraded = self.manifest()
        self.assertEqual(upgraded["devloops_version"], "0.3.0")
        self.assertEqual(upgraded["installed_at"], installed["installed_at"])
        self.assertTrue(upgraded["upgraded_at"])
        self.assertEqual(upgraded["files"][README], sha(b"new README\n"))
        self.assertEqual(upgraded["ignore_rules"], installed["ignore_rules"])
        for rel, digest in upgraded["files"].items():
            self.assertEqual(sha(self.read(rel)), digest, rel)

    def test_a_downgrade_is_refused(self):
        manifest = self.manifest()
        manifest["devloops_version"] = "9.0.0"
        self.write(MANIFEST, json.dumps(manifest))
        os.remove(self.path(RUN_SKILL))
        before = self.read(MANIFEST)
        code, result = self.upgrade("--restore")
        self.assertEqual(code, 30, self.output)
        self.assertIn("downgrade-refused", result["message"])
        self.assertIn("9.0.0", result["message"])
        self.assertIn("0.3.0", result["message"])
        self.assertEqual(self.read(MANIFEST), before)
        self.assertFalse(os.path.exists(self.path(RUN_SKILL)))
        code, _ = self.cli(["init", self.dir, "--upgrade"], self.new)
        self.assertEqual(code, 30)
        self.assertIn("downgrade-refused", self.output)
        self.assertEqual(initcmd.version_tuple("0.10.0") > initcmd.version_tuple("0.9.1"), True)

    def test_text_output_and_flag_errors(self):
        self.release(os.path.join("loops", "shared", "skills", "devloops-status", "SKILL.md"),
                     "new status skill\n")
        self.write(STATUS_SKILL, "mine\n")
        os.remove(self.path(RUN_SKILL))
        code, out = self.cli(["init", self.dir, "--upgrade"], self.new)
        self.assertEqual(code, 0, self.output)
        self.assertIn("upgraded", out)
        self.assertIn("from devloops 0.2.0 to 0.3.0", out)
        self.assertIn(f"kept: {STATUS_SKILL}", out)
        self.assertIn(STATUS_SKILL + ".devloops-new", out)
        self.assertIn(f"deleted: {RUN_SKILL}", out)
        self.assertNotIn("Next:", out)
        self.assertEqual(self.cli(["init", self.dir, "--restore"], self.new)[0], 2)
        self.assertEqual(self.cli(["init", self.dir, "--upgrade", "--backend-target", "x"],
                                  self.new)[0], 2)
        outside = os.path.join(self.t.base, "outside")
        os.makedirs(outside)
        self.assertEqual(self.cli(["init", outside, "--upgrade"], self.new)[0], 2)

    # --- the version warning (FR-029) ---

    def test_status_warns_on_a_version_mismatch(self):
        from devloops import project, workspace
        proj = project.Project(self.dir)
        workspace.open_workspace("main", proj, self.new, create=True)
        code, out = self.cli(["status", "--json"], self.new, project=proj)
        self.assertEqual(code, 0, self.output)
        [warning] = json.loads(out)["warnings"]
        self.assertIn("devloops 0.2.0; running 0.3.0", warning)
        self.assertIn("init --upgrade", warning)
        self.cli(["status"], self.new, project=proj)
        self.assertIn("devloops: warning: this project was set up with devloops 0.2.0",
                      self.output)
        self.assertEqual(self.upgrade()[0], 0, self.output)
        code, out = self.cli(["status", "--json"], self.new, project=proj)
        self.assertNotIn("warnings", json.loads(out))
        # The older devloops is told to install the newer one, not to upgrade (it would refuse).
        code, out = self.cli(["status", "--json"], self.old, project=proj)
        [warning] = json.loads(out)["warnings"]
        self.assertIn("devloops 0.3.0; running 0.2.0. Install devloops 0.3.0 or later", warning)


if __name__ == "__main__":
    unittest.main()
