"""`devloops init` (002 US1: FR-003 to FR-007b, SC-003; quickstart §1 rows 1–3)."""
import hashlib
import json
import os
import pty
import select
import subprocess
import sys
import tempfile
import time
import unittest

import helpers

SKILLS = ("approve", "dashboard", "orchestrate", "replan", "retry", "run", "status")
INSTALLED = sorted([".devloops/prompts/README.md"]
                   + [f".claude/skills/devloops-{name}/SKILL.md" for name in SKILLS])
CREATED = sorted(INSTALLED + [".devloops/devloops.json", ".devloops/manifest.json", ".gitignore"])
COMMAND = os.path.join(helpers.REPO_ROOT, "bin", "devloops")


def all_files(root):
    return sorted(os.path.relpath(os.path.join(d, n), root).replace(os.sep, "/")
                  for d, dirs, names in os.walk(root) for n in names)


def mtimes(root):
    return {p: os.stat(os.path.join(root, p)).st_mtime_ns for p in all_files(root)}


class InitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(os.path.realpath(self.tmp.name), "app")
        os.makedirs(self.dir)
        self.env = os.environ.copy()
        self.env.pop("DEVLOOPS_PROJECT", None)

    def tearDown(self):
        self.tmp.cleanup()

    def init(self, *args):
        return helpers.run_cli(["init", *args], env=self.env, cwd=self.dir)

    def init_json(self, *args):
        code, out, err = self.init("--no-prompt", "--json", *args)
        return code, json.loads(out)

    def read(self, rel):
        with open(os.path.join(self.dir, rel), encoding="utf-8") as f:
            return f.read()

    def write(self, rel, text):
        path = os.path.join(self.dir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    # --- file modes ---

    def test_created_files_are_0644_and_an_existing_gitignore_keeps_its_mode(self):
        self.write(".gitignore", "node_modules/\n")
        os.chmod(os.path.join(self.dir, ".gitignore"), 0o664)
        code, result = self.init_json()
        self.assertEqual(code, 0, result)
        self.assertEqual(os.stat(os.path.join(self.dir, ".gitignore")).st_mode & 0o777, 0o664)
        for rel in result["created"]:
            with self.subTest(file=rel):
                self.assertEqual(os.stat(os.path.join(self.dir, rel)).st_mode & 0o777, 0o644)

    # --- fresh project ---

    def test_fresh_init_creates_exactly_the_listed_files(self):
        code, result = self.init_json()
        self.assertEqual(code, 0, result)
        self.assertEqual(all_files(self.dir), CREATED)
        self.assertEqual(sorted(result["created"]), CREATED)
        for key in ("project", "created", "changed", "kept", "deleted", "removed", "conflicts",
                    "permission_rule", "next", "exit_code", "message"):
            self.assertIn(key, result)
        self.assertEqual(result["project"], self.dir)
        self.assertEqual(result["permission_rule"], f"Bash({COMMAND} *)")
        self.assertEqual(result["next"], f"{COMMAND} check")

        config = json.loads(self.read(".devloops/devloops.json"))
        self.assertEqual(config["targets"], {"backend-dev": "backend", "frontend-dev": "frontend"})
        self.assertEqual(config["workspace"], "main")
        self.assertIsNone(config["requirements"])
        self.assertIn("no requirements set", result["message"])

        manifest = json.loads(self.read(".devloops/manifest.json"))
        self.assertEqual(sorted(manifest["files"]), INSTALLED)
        for rel, sha in manifest["files"].items():
            with open(os.path.join(self.dir, rel), "rb") as f:
                self.assertEqual(hashlib.sha256(f.read()).hexdigest(), sha, rel)
        self.assertEqual((manifest["kit_mode"], manifest["command"]), ("source", COMMAND))
        from devloops import schema
        self.assertEqual(schema.validate(manifest, "manifest.schema.json"), [])
        self.assertEqual(schema.validate(config, "project-config.schema.json"), [])

    def test_skills_call_the_project_command(self):
        self.init_json()
        text = self.read(".claude/skills/devloops-run/SKILL.md")
        self.assertIn(f"allowed-tools: Bash({COMMAND} *)", text)
        self.assertIn(f"{COMMAND} run $ARGUMENTS --json", text)
        self.assertNotIn("{{DEVLOOPS}}", text)

    def test_text_output_names_the_next_steps(self):
        code, out, err = self.init("--no-prompt")
        self.assertEqual(code, 0, err)
        self.assertIn(f"Bash({COMMAND} *)", out)
        self.assertIn(f"{COMMAND} check", out)
        self.assertIn("created: .devloops/manifest.json", out)

    def test_second_init_changes_nothing(self):
        self.init_json()
        before = mtimes(self.dir)
        time.sleep(0.01)
        code, result = self.init_json()
        self.assertEqual(code, 0)
        self.assertIn("already initialized", result["message"])
        self.assertEqual(result["created"], [])
        self.assertEqual(mtimes(self.dir), before)

    def test_dir_argument(self):
        other = os.path.join(self.dir, "sub")
        code, out, err = helpers.run_cli(["init", "--no-prompt", other], env=self.env,
                                         cwd=self.dir)
        self.assertEqual(code, 0, err)
        self.assertTrue(os.path.isfile(os.path.join(other, ".devloops", "manifest.json")))

    def test_existing_devloops_json_is_kept(self):
        original = '{"schema_version": 1, "workspaces_dir": "ws"}\n'
        self.write(".devloops/devloops.json", original)
        code, result = self.init_json("--backend-target", "api")
        self.assertEqual(code, 0, result)
        self.assertEqual(self.read(".devloops/devloops.json"), original)
        self.assertIn("kept the existing", result["message"])
        self.assertIn("--backend-target ignored", result["message"])
        self.assertIn("ws/", self.read(".gitignore"))

    # --- conflicts (FR-005) ---

    def test_a_different_existing_skill_is_a_conflict_and_nothing_is_written(self):
        self.write(".claude/skills/devloops-run/SKILL.md", "mine\n")
        code, result = self.init_json()
        self.assertEqual(code, 30)
        self.assertIn("init-conflict", result["message"])
        self.assertEqual(result["conflicts"], [".claude/skills/devloops-run/SKILL.md"])
        self.assertEqual(all_files(self.dir), [".claude/skills/devloops-run/SKILL.md"])
        code, out, err = self.init("--no-prompt")
        self.assertEqual(code, 30)
        self.assertIn(".claude/skills/devloops-run/SKILL.md", err)

    def test_an_identical_existing_file_is_adopted(self):
        from devloops import initcmd, kit
        rel = ".devloops/prompts/README.md"
        data = initcmd.installed_files(kit.Kit.resolve(), self.dir)[rel]
        self.write(rel, data.decode("utf-8"))
        code, result = self.init_json()
        self.assertEqual(code, 0, result)
        self.assertEqual(result["adopted"], [rel])
        self.assertNotIn(rel, result["created"])
        self.assertIn(rel, json.loads(self.read(".devloops/manifest.json"))["files"])

    # --- .gitignore ---

    def test_track_flags_drop_their_lines(self):
        self.init_json("--track-workspaces", "--track-dashboards")
        self.assertEqual(self.read(".gitignore").splitlines(),
                         ['# >>> devloops (added by "devloops init")',
                          ".devloops/devloops.local.json", "# <<< devloops"])
        manifest = json.loads(self.read(".devloops/manifest.json"))
        self.assertEqual(manifest["ignore_rules"], [".devloops/devloops.local.json"])

    def test_an_existing_gitignore_is_appended_and_the_block_is_not_added_twice(self):
        self.write(".gitignore", "node_modules/")
        code, result = self.init_json()
        self.assertEqual(result["changed"], [".gitignore"])
        text = self.read(".gitignore")
        self.assertTrue(text.startswith("node_modules/\n\n# >>> devloops"), text)
        os.remove(os.path.join(self.dir, ".devloops", "manifest.json"))  # init again
        self.init_json()
        self.assertEqual(self.read(".gitignore"), text)

    # --- targets and requirements (FR-007, FR-007b) ---

    def test_a_target_inside_dot_devloops_is_refused_before_any_write(self):
        code, result = self.init_json("--backend-target", ".devloops/x")
        self.assertEqual(code, 30)
        self.assertIn("target-unwritable", result["message"])
        self.assertEqual(all_files(self.dir), [])

    def test_the_same_target_for_both_loops_is_refused(self):
        code, result = self.init_json("--backend-target", "app", "--frontend-target", "app")
        self.assertEqual(code, 30)
        self.assertIn("target-unwritable", result["message"])
        self.assertEqual(all_files(self.dir), [])

    def test_target_and_requirements_flags(self):
        self.write("docs/prd.md", "# PRD\n")
        outside = os.path.join(os.path.dirname(self.dir), "web")
        code, result = self.init_json("--backend-target", "src/api", "--frontend-target", outside,
                                      "--requirements", "docs/prd.md")
        self.assertEqual(code, 0, result)
        config = json.loads(self.read(".devloops/devloops.json"))
        self.assertEqual(config["targets"], {"backend-dev": "src/api", "frontend-dev": outside})
        self.assertEqual(config["requirements"], {"path": "docs/prd.md"})

    def test_missing_requirements_file_is_refused(self):
        code, result = self.init_json("--requirements", "nope.md")
        self.assertEqual(code, 30)
        self.assertEqual(all_files(self.dir), [])

    def test_active_spec_kit_feature_is_the_default(self):
        self.write("specs/001-x/spec.md", "# Spec\n")
        self.write(".specify/feature.json", '{"feature_directory": "specs/001-x"}')
        code, result = self.init_json()
        self.assertEqual(json.loads(self.read(".devloops/devloops.json"))["requirements"],
                         {"speckit_feature": "active"})
        code, result = self.init_json()  # already initialized: unchanged
        os.remove(os.path.join(self.dir, ".devloops", "manifest.json"))
        os.remove(os.path.join(self.dir, ".devloops", "devloops.json"))
        self.init_json("--speckit-feature", "specs/001-x")
        self.assertEqual(json.loads(self.read(".devloops/devloops.json"))["requirements"],
                         {"speckit_feature": "specs/001-x"})


class InteractiveInitTest(unittest.TestCase):
    """`init` on a terminal asks for each value (FR-007a); invalid answers are asked again."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(os.path.realpath(self.tmp.name), "app")
        os.makedirs(self.dir)

    def tearDown(self):
        self.tmp.cleanup()

    def run_tty(self, answers, *args):
        """Run `bin/devloops init` with a pseudo-terminal; return (exit code, transcript)."""
        master, slave = pty.openpty()
        env = dict(os.environ)
        env.pop("DEVLOOPS_PROJECT", None)
        proc = subprocess.Popen([sys.executable, COMMAND, "init", *args], cwd=self.dir,
                                stdin=slave, stdout=slave, stderr=slave, env=env)
        os.close(slave)
        os.write(master, "".join(a + "\n" for a in answers).encode())
        chunks = []
        deadline = time.time() + 60
        while time.time() < deadline:
            ready, _, _ = select.select([master], [], [], 0.2)
            if ready:
                try:
                    data = os.read(master, 4096)
                except OSError:  # EIO: the child closed the terminal
                    break
                if not data:
                    break
                chunks.append(data)
            elif proc.poll() is not None:
                break
        code = proc.wait(timeout=30)
        os.close(master)
        return code, b"".join(chunks).decode("utf-8", "replace")

    def config(self):
        with open(os.path.join(self.dir, ".devloops", "devloops.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_accepting_the_defaults(self):
        code, out = self.run_tty(["", "", ""])
        self.assertEqual(code, 0, out)
        self.assertIn("Backend target [backend]", out)
        self.assertIn("Frontend target [frontend]", out)
        self.assertEqual(self.config()["targets"],
                         {"backend-dev": "backend", "frontend-dev": "frontend"})
        self.assertIsNone(self.config()["requirements"])

    def test_an_invalid_backend_answer_is_asked_again(self):
        code, out = self.run_tty([".devloops/x", "api", "", ""])
        self.assertEqual(code, 0, out)
        self.assertEqual(out.count("Backend target [backend]"), 2, out)
        self.assertIn("overlaps", out)
        self.assertEqual(self.config()["targets"]["backend-dev"], "api")

    def test_the_active_feature_is_the_requirements_default(self):
        os.makedirs(os.path.join(self.dir, "specs", "001-x"))
        with open(os.path.join(self.dir, "specs", "001-x", "spec.md"), "w") as f:
            f.write("# Spec\n")
        os.makedirs(os.path.join(self.dir, ".specify"))
        with open(os.path.join(self.dir, ".specify", "feature.json"), "w") as f:
            json.dump({"feature_directory": "specs/001-x"}, f)
        code, out = self.run_tty(["", "", ""])
        self.assertEqual(code, 0, out)
        self.assertIn("active spec-kit feature (specs/001-x)", out)
        self.assertEqual(self.config()["requirements"], {"speckit_feature": "active"})

    def test_a_missing_requirements_file_is_asked_again(self):
        with open(os.path.join(self.dir, "prd.md"), "w") as f:
            f.write("# PRD\n")
        code, out = self.run_tty(["", "", "nope.md", "prd.md"])
        self.assertEqual(code, 0, out)
        self.assertIn("does not exist", out)
        self.assertEqual(self.config()["requirements"], {"path": "prd.md"})

    def test_end_of_input_with_a_rejected_default_stops(self):
        code, out = self.run_tty(["\x04"], "--backend-target", "frontend")
        self.assertEqual(code, 2, out)
        self.assertIn("no valid answer", out)
        self.assertFalse(os.path.exists(os.path.join(self.dir, ".devloops")))

    def test_end_of_input_takes_the_remaining_defaults(self):
        code, out = self.run_tty(["api", "\x04"])
        self.assertEqual(code, 0, out)
        self.assertEqual(self.config()["targets"],
                         {"backend-dev": "api", "frontend-dev": "frontend"})

    def test_an_existing_devloops_json_is_not_asked_about(self):
        os.makedirs(os.path.join(self.dir, ".devloops"))
        with open(os.path.join(self.dir, ".devloops", "devloops.json"), "w") as f:
            json.dump({"schema_version": 1}, f)
        code, out = self.run_tty([])
        self.assertEqual(code, 0, out)
        self.assertNotIn("Backend target", out)
        self.assertIn("kept the existing", out)

    def test_no_prompt_never_asks(self):
        code, out = self.run_tty([], "--no-prompt")
        self.assertEqual(code, 0, out)
        self.assertNotIn("Backend target", out)


if __name__ == "__main__":
    unittest.main()
