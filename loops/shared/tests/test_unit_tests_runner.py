import os
import tempfile
import unittest

import helpers  # noqa: F401
import samples
from devloops.redact import Redactor
from devloops.validators import unit_tests


class UnitTestsRunnerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.target = os.path.join(self.tmp.name, "target")
        self.trial = os.path.join(self.tmp.name, "trial")
        os.makedirs(os.path.join(self.target, "app"))
        self.config = samples.config()

    def tearDown(self):
        self.tmp.cleanup()

    def enable(self, command=None):
        self.config["unit_tests"] = {"enabled": True, "command": command}

    def log(self, result):
        with open(os.path.join(self.trial, result["log_path"])) as f:
            return f.read()

    def test_disabled_does_nothing(self):
        self.assertEqual(unit_tests.run(self.config, {}, self.target, self.trial),
                         {"enabled": False})
        self.assertFalse(os.path.exists(self.trial))

    def test_config_command_passes(self):
        self.enable("pwd && echo ok")
        result = unit_tests.run(self.config, {"cwd": "app"}, self.target, self.trial)
        self.assertEqual((result["enabled"], result["exit_code"]), (True, 0))
        self.assertEqual(result["log_path"], os.path.join("evidence", "unit-tests.log"))
        log = self.log(result)
        self.assertIn(os.path.join(self.target, "app"), log)
        self.assertIn("[exit code 0]", log)

    def test_falls_back_to_plan_command(self):
        self.enable()
        result = unit_tests.run(self.config, {"unit_test_command": "exit 4"}, self.target,
                                self.trial)
        self.assertEqual((result["command"], result["exit_code"]), ("exit 4", 4))

    def test_config_command_wins(self):
        self.enable("true")
        result = unit_tests.run(self.config, {"unit_test_command": "false"}, self.target,
                                self.trial)
        self.assertEqual(result["command"], "true")

    def test_enabled_without_a_command_fails(self):
        self.enable()
        result = unit_tests.run(self.config, {}, self.target, self.trial)
        self.assertEqual(result["enabled"], True)
        self.assertNotIn("exit_code", result)
        self.assertIn("no unit test command", self.log(result))

    def test_timeout(self):
        self.enable("sleep 30")
        self.config["invocation_timeout_seconds"] = 1
        result = unit_tests.run(self.config, {}, self.target, self.trial)
        self.assertEqual(result["exit_code"], unit_tests.TIMEOUT_EXIT_CODE)
        self.assertIn("timed out", self.log(result))

    def test_log_is_redacted(self):
        self.enable("echo token=abc123")
        self.config["secrets"] = {"env": [], "literals": ["abc123"]}
        result = unit_tests.run(self.config, {}, self.target, self.trial, Redactor(self.config))
        self.assertIn("token=***", self.log(result))
        self.assertNotIn("abc123", self.log(result))


if __name__ == "__main__":
    unittest.main()
