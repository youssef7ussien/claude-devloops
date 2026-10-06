"""The devloops skills stay thin, and `init --allow-skills` adds their permission rule on request
(002 US4: FR-020 to FR-022b; contracts/skills.md)."""
import json
import os
import re
import tempfile
import unittest

import helpers
from devloops import kit

TEMPLATES = os.path.join(helpers.REPO_ROOT, "loops", "shared", "skills")
COMMANDS = {"devloops-run": "run", "devloops-orchestrate": "orchestrate",
            "devloops-approve": "approve", "devloops-replan": "replan",
            "devloops-retry": "retry", "devloops-status": "status",
            "devloops-dashboard": "dashboard"}
SETTINGS = os.path.join(".claude", "settings.json")


class SkillTemplatesTest(unittest.TestCase):
    def templates(self):
        for name in sorted(os.listdir(TEMPLATES)):
            with open(os.path.join(TEMPLATES, name, "SKILL.md"), encoding="utf-8") as f:
                yield name, f.read()

    def test_the_contract_table_names_every_template(self):
        self.assertEqual(sorted(name for name, _ in self.templates()), sorted(COMMANDS))

    def test_each_template_runs_exactly_one_command(self):
        for name, text in self.templates():
            with self.subTest(skill=name):
                commands = re.findall(r"\{\{DEVLOOPS\}\} (\S+)", text)
                frontmatter = text.split("---", 2)[1]
                body = text.split("---", 2)[2]
                runs = re.findall(r"(?m)^\s*\{\{DEVLOOPS\}\} (\S+) \$ARGUMENTS --json\s*$", body)
                self.assertEqual(runs, [COMMANDS[name]])
                # The only other mention is the pre-approval in the frontmatter (FR-021).
                self.assertEqual(sorted(commands), sorted([COMMANDS[name], "*)"]))
                self.assertIn("allowed-tools: Bash({{DEVLOOPS}} *)\n", frontmatter)
                self.assertIn("user-invocable: true\n", frontmatter)
                self.assertIn(f'name: "{name}"', frontmatter)


class AllowSkillsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = os.path.join(os.path.realpath(self.tmp.name), "app")
        os.makedirs(self.dir)
        self.env = os.environ.copy()
        self.env.pop("DEVLOOPS_PROJECT", None)
        self.rule = f"Bash({kit.Kit.resolve().command_for(self.dir)} *)"

    def init(self, *args):
        code, out, err = helpers.run_cli(["init", "--no-prompt", *args], env=self.env,
                                         cwd=self.dir)
        self.output = out + err
        return code, out

    def settings_text(self):
        with open(os.path.join(self.dir, SETTINGS), encoding="utf-8") as f:
            return f.read()

    def write_settings(self, text):
        os.makedirs(os.path.join(self.dir, ".claude"), exist_ok=True)
        with open(os.path.join(self.dir, SETTINGS), "w", encoding="utf-8") as f:
            f.write(text)

    def test_a_fresh_init_does_not_touch_settings_without_the_flag(self):
        code, out = self.init()
        self.assertEqual(code, 0, self.output)
        self.assertFalse(os.path.exists(os.path.join(self.dir, SETTINGS)))
        self.assertIn("init --allow-skills", out)
        self.assertIn(self.rule, out)

    def test_a_fresh_init_creates_the_settings_with_the_rule(self):
        code, out = self.init("--allow-skills", "--json")
        self.assertEqual(code, 0, self.output)
        result = json.loads(out)
        self.assertIn(SETTINGS, result["created"])
        self.assertEqual(json.loads(self.settings_text()), {"permissions": {"allow": [self.rule]}})

    def test_existing_settings_are_kept_and_the_rule_added_once(self):
        existing = {"model": "opus", "permissions": {"allow": ["Bash(make *)", "Read"],
                                                     "deny": ["Bash(rm *)"]},
                    "hooks": {"Stop": []}}
        self.write_settings(json.dumps(existing))
        code, out = self.init("--allow-skills", "--json")
        self.assertEqual(code, 0, self.output)
        self.assertIn(SETTINGS, json.loads(out)["changed"])
        expected = json.loads(json.dumps(existing))
        expected["permissions"]["allow"].append(self.rule)
        self.assertEqual(json.loads(self.settings_text()), expected)
        self.assertEqual(list(json.loads(self.settings_text())), ["model", "permissions", "hooks"])
        before = self.settings_text()
        code, out = self.init("--allow-skills", "--json")  # now initialized: only the rule
        self.assertEqual(code, 0, self.output)
        self.assertEqual(json.loads(out)["changed"], [])
        self.assertEqual(self.settings_text(), before)

    def test_it_works_on_an_initialized_project_and_reinstalls_nothing(self):
        self.assertEqual(self.init()[0], 0, self.output)
        skill = os.path.join(self.dir, ".claude", "skills", "devloops-run", "SKILL.md")
        os.remove(skill)
        code, out = self.init("--allow-skills")
        self.assertEqual(code, 0, self.output)
        self.assertIn(f"added {self.rule}", out)
        self.assertEqual(json.loads(self.settings_text())["permissions"]["allow"], [self.rule])
        self.assertFalse(os.path.exists(skill))

    def test_the_settings_mode_and_a_symlink_are_kept(self):
        shared = os.path.join(self.dir, "team-settings.json")
        with open(shared, "w") as f:
            f.write('{"model": "opus"}')
        os.chmod(shared, 0o640)
        os.makedirs(os.path.join(self.dir, ".claude"))
        os.symlink(shared, os.path.join(self.dir, SETTINGS))
        self.assertEqual(self.init("--allow-skills")[0], 0, self.output)
        self.assertTrue(os.path.islink(os.path.join(self.dir, SETTINGS)))
        with open(shared) as f:
            self.assertEqual(json.load(f)["permissions"]["allow"], [self.rule])
        self.assertEqual(os.stat(shared).st_mode & 0o777, 0o640)

    def test_a_new_settings_file_is_readable_by_all(self):
        self.assertEqual(self.init("--allow-skills")[0], 0, self.output)
        self.assertEqual(os.stat(os.path.join(self.dir, SETTINGS)).st_mode & 0o777, 0o644)

    def test_unreadable_settings_are_left_alone(self):
        self.write_settings("{not json")
        code, _ = self.init("--allow-skills")
        self.assertEqual(code, 30, self.output)
        self.assertIn("settings-unreadable", self.output)
        self.assertIn(self.rule, self.output)
        self.assertEqual(self.settings_text(), "{not json")
        self.assertFalse(os.path.exists(os.path.join(self.dir, ".devloops")))  # nothing written
        self.write_settings('{"permissions": {"allow": "Bash(*)"}}')
        self.assertEqual(self.init("--allow-skills")[0], 30, self.output)


if __name__ == "__main__":
    unittest.main()
