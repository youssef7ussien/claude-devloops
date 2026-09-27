import hashlib
import os
import tempfile
import unittest

import helpers  # noqa: F401
from devloops import inputs, state


class InputsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, content):
        path = os.path.join(self.dir, name)
        with open(path, "wb") as f:
            f.write(content)
        return path

    def assert_missing(self, path):
        with self.assertRaises(state.StopRun) as cm:
            inputs.check_requirements(path)
        self.assertEqual((cm.exception.status, cm.exception.code),
                         ("stopped-on-input-error", "missing-input"))
        self.assertEqual(cm.exception.exit_code, 30)
        return cm.exception

    def test_valid_file(self):
        path = self.write("prd.md", b"# PRD\n")
        self.assertEqual(inputs.check_requirements(path), os.path.abspath(path))

    def test_missing_empty_blank_directory_and_none(self):
        self.assertIn("does not exist", self.assert_missing(os.path.join(self.dir, "no.md")).message)
        self.assertIn("empty", self.assert_missing(self.write("e.md", b"")).message)
        self.assert_missing(self.write("ws.md", b" \n\t\r\n"))
        self.assert_missing(self.dir)
        self.assert_missing(None)

    @unittest.skipIf(os.geteuid() == 0, "root can read anything")
    def test_unreadable(self):
        path = self.write("secret.md", b"x")
        os.chmod(path, 0)
        try:
            self.assertIn("cannot be read", self.assert_missing(path).message)
        finally:
            os.chmod(path, 0o600)

    def test_sha256_is_byte_level(self):
        a = self.write("a.md", b"line\n")
        b = self.write("b.md", b"line\r\n")
        self.assertEqual(inputs.sha256_file(a), hashlib.sha256(b"line\n").hexdigest())
        self.assertNotEqual(inputs.sha256_file(a), inputs.sha256_file(b))

    def run_state(self, prd, spec=None, answers=None):
        run = {"inputs": {"requirements": {"path": prd, "sha256": inputs.sha256_file(prd),
                                           "mode": "prd", "story_id": None}}}
        if spec:
            run["inputs"]["api_spec"] = {"path": spec, "sha256": inputs.sha256_file(spec)}
        if answers:
            run["approval"] = {"answers_path": answers, "answers_sha256": inputs.sha256_file(answers)}
        return run

    def assert_changed(self, run, name):
        with self.assertRaises(state.StopRun) as cm:
            inputs.compare_fingerprints(run, inputs.current_fingerprints(run))
        self.assertEqual(cm.exception.status_reason()["code"], "input-changed")
        self.assertEqual(cm.exception.details, {"input": name})

    def test_unchanged_inputs_pass(self):
        run = self.run_state(self.write("p.md", b"p"), self.write("s.json", b"{}"),
                             self.write("oq.md", b"a"))
        before = repr(run)
        inputs.compare_fingerprints(run, inputs.current_fingerprints(run))
        self.assertEqual(repr(run), before)  # nothing is changed

    def test_each_input_is_named(self):
        prd, spec, answers = self.write("p.md", b"p"), self.write("s.json", b"{}"), \
            self.write("oq.md", b"a")
        run = self.run_state(prd, spec, answers)
        self.write("oq.md", b"b")
        self.assert_changed(run, "answers")
        self.write("s.json", b"{ }")
        self.assert_changed(run, "api-spec")
        self.write("p.md", b"p ")
        self.assert_changed(run, "requirements")  # reported first

    def test_deleted_input_counts_as_changed(self):
        prd = self.write("p.md", b"p")
        run = self.run_state(prd)
        os.remove(prd)
        self.assert_changed(run, "requirements")

    def test_answers_ignored_until_an_approval_records_them(self):
        run = self.run_state(self.write("p.md", b"p"))
        self.write("oq.md", b"edited while awaiting approval")
        inputs.compare_fingerprints(run, inputs.current_fingerprints(run))


if __name__ == "__main__":
    unittest.main()
