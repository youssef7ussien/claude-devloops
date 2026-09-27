import json
import os
import re
import tempfile
import unittest
from unittest import mock

import helpers  # noqa: F401
from devloops import redact, state


class StateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_write_and_read_json(self):
        path = os.path.join(self.dir, "a", "run.json")
        state.write_json_atomic(path, {"status": "planning", "n": 1})
        self.assertEqual(state.read_json(path), {"status": "planning", "n": 1})
        self.assertEqual(os.listdir(os.path.dirname(path)), ["run.json"])

    def test_read_json_default_when_missing(self):
        self.assertIsNone(state.read_json(os.path.join(self.dir, "nope.json")))
        self.assertEqual(state.read_json(os.path.join(self.dir, "nope.json"), default={}), {})

    def test_crash_before_replace_keeps_the_old_file(self):
        path = os.path.join(self.dir, "run.json")
        state.write_json_atomic(path, {"version": 1})
        with mock.patch("devloops.state.os.replace", side_effect=OSError("crash")):
            with self.assertRaises(OSError):
                state.write_json_atomic(path, {"version": 2})
        self.assertEqual(state.read_json(path), {"version": 1})
        self.assertEqual(os.listdir(self.dir), ["run.json"])

    def test_crash_while_serializing_keeps_the_old_file(self):
        path = os.path.join(self.dir, "run.json")
        state.write_json_atomic(path, {"version": 1})
        with self.assertRaises(TypeError):
            state.write_json_atomic(path, {"bad": object()})
        self.assertEqual(state.read_json(path), {"version": 1})

    def test_append_jsonl(self):
        path = os.path.join(self.dir, "s", "log.jsonl")
        state.append_jsonl(path, {"a": 1})
        state.append_jsonl(path, {"b": "ü"})
        with open(path, encoding="utf-8") as f:
            self.assertEqual([json.loads(line) for line in f], [{"a": 1}, {"b": "ü"}])
        self.assertEqual(state.read_jsonl(path), [{"a": 1}, {"b": "ü"}])

    def test_now_iso_is_utc_with_z(self):
        self.assertRegex(state.now_iso(), r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")

    def test_record_event(self):
        loop_dir = os.path.join(self.dir, "backend-dev")
        event = state.record_event(loop_dir, "trial-started", "trial 1", milestone="M01", trial=1)
        self.assertEqual(event["loop"], "backend-dev")
        stored = state.read_jsonl(os.path.join(loop_dir, "state", "events.jsonl"))
        self.assertEqual(stored, [event])
        self.assertEqual(set(event), {"at", "loop", "type", "message", "milestone", "trial"})

    def test_record_event_omits_empty_milestone_and_trial(self):
        event = state.record_event(os.path.join(self.dir, "frontend-dev"), "paused", "waiting")
        self.assertNotIn("milestone", event)
        self.assertNotIn("trial", event)

    def test_record_event_rejects_unknown_types(self):
        with self.assertRaises(ValueError):
            state.record_event(self.dir, "made-up", "x")

    def test_record_event_redacts(self):
        r = redact.Redactor({"secrets": {"literals": ["hunter2"]}})
        event = state.record_event(os.path.join(self.dir, "backend-dev"), "stopped",
                                   "password hunter2 rejected", redactor=r)
        self.assertEqual(event["message"], "password *** rejected")

    def test_event_types_match_data_model(self):
        data_model = os.path.join(helpers.REPO_ROOT, "specs", "001-reusable-dev-loops",
                                  "data-model.md")
        if not os.path.exists(data_model):
            self.skipTest("data-model.md not present")
        with open(data_model, encoding="utf-8") as f:
            text = f.read()
        section = text.split("## Event (action-item log)", 1)[1].split("\n## ", 1)[0]
        documented = set(re.findall(r"`([a-z]+(?:-[a-z]+)*)`", section.split("The `type` values are", 1)[1]))
        self.assertEqual(documented, state.EVENT_TYPES)

    def test_stop_run(self):
        stop = state.input_error("input-changed", "changed", input="requirements", tool=None)
        self.assertEqual(stop.exit_code, 30)
        self.assertEqual(stop.status, "stopped-on-input-error")
        self.assertEqual(stop.status_reason(),
                         {"code": "input-changed", "message": "changed", "input": "requirements"})


if __name__ == "__main__":
    unittest.main()
