"""Each call's Claude Code conversation is copied, redacted, into the workspace (002 FR-040 to
FR-042, research P-9)."""
import json
import os
import unittest

import helpers  # noqa: F401 - puts the package on sys.path
import samples
from devloops import state
from stub_loop import StubLoopMixin

SECRET = "S3CR3T-conversation-value"


class ConversationCopyTest(StubLoopMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.t.make_project(self.t.root, {"workspaces_dir": "workspaces",
                                          "config": {"secrets": {"literals": [SECRET]}}})

    def records(self):
        return state.read_jsonl(self.path(os.path.join("state", "invocations.jsonl")))

    def transcript(self, record):
        """The fake Claude's own transcript for a record's session (the original, unredacted)."""
        projects = os.path.join(self.t.env["CLAUDE_CONFIG_DIR"], "projects")
        for folder in os.listdir(projects):
            path = os.path.join(projects, folder, record["session_id"] + ".jsonl")
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as f:
                    return f.read()
        self.fail(f"no transcript for {record['session_id']}")

    def test_each_call_is_copied_and_redacted(self):
        self.scenario({"plan": {"structured_output": samples.plan(),
                                "result": f"planned with {SECRET}"}})
        self.assertEqual(self.first_run(), 10, self.last_output)
        [record] = self.records()
        self.assertEqual(record["conversation"], "copied")
        self.assertEqual(record["conversation_path"],
                         os.path.join("state", "conversations", "0001-plan.jsonl"))
        self.assertNotIn("conversation_reason", record)
        self.assertTrue(record["redacted"])
        original = self.transcript(record)
        self.assertIn(SECRET, original)
        copy = self.read(record["conversation_path"])
        self.assertNotIn(SECRET, copy)
        self.assertEqual(copy, original.replace(SECRET, "***"))

    def test_a_secret_escaped_by_json_is_still_redacted(self):
        secret = 'quote"d-secret'
        self.t.make_project(self.t.root, {"workspaces_dir": "workspaces",
                                          "config": {"secrets": {"literals": [secret]}}})
        self.scenario({"plan": {"structured_output": samples.plan(), "result": secret}})
        self.assertEqual(self.first_run(), 10, self.last_output)
        [record] = self.records()
        self.assertIn(json.dumps(secret)[1:-1], self.transcript(record))
        copy = self.read(record["conversation_path"])
        self.assertNotIn(json.dumps(secret)[1:-1], copy)
        self.assertIn("***", copy)
        for line in copy.splitlines():
            json.loads(line)

    def test_a_line_separator_inside_a_string_does_not_split_the_record(self):
        from devloops.claude import redact_transcript
        from devloops.redact import Redactor
        secret = 'quote"d'
        line = json.dumps({"text": "a\u2028b " + secret}, ensure_ascii=False)
        self.assertIn("\u2028", line)
        text, changed = redact_transcript(line + "\n" + line + "\n",
                                          Redactor({"secrets": {"literals": [secret]}}))
        self.assertTrue(changed)
        self.assertNotIn('quote\\"d', text)
        self.assertEqual(text.count("\n"), 2)
        self.assertEqual(json.loads(text.split("\n")[0]), {"text": "a\u2028b ***"})

    def test_a_shortened_project_folder_is_found_by_session(self):
        self.t.write_scenario({"transcript_dir": "-tmp-shortened-1a2b3c",
                               "steps": {"plan": {"structured_output": samples.plan()}}})
        self.assertEqual(self.first_run(), 10, self.last_output)
        [record] = self.records()
        self.assertEqual(record["conversation"], "copied")
        self.assertEqual(self.read(record["conversation_path"]), self.transcript(record))

    def test_a_missing_transcript_is_unavailable_and_the_run_goes_on(self):
        self.t.write_scenario({"transcript": False,
                               "steps": {"plan": {"structured_output": samples.plan()}}})
        self.assertEqual(self.first_run(), 10, self.last_output)
        [record] = self.records()
        self.assertEqual(record["conversation"], "unavailable")
        self.assertEqual(record["conversation_reason"], "not-found")
        self.assertNotIn("conversation_path", record)
        self.assertFalse(os.path.exists(self.path(os.path.join("state", "conversations"))))
        self.assertEqual(self.run_state()["status"], "awaiting-approval")

    def test_every_call_of_a_full_run_has_its_own_copy(self):
        self.approved()
        self.assertEqual(self.cli("run"), 0, self.last_output)
        records = self.records()
        self.assertGreaterEqual(len(records), 3)
        for record in records:
            self.assertEqual(record["conversation_path"], os.path.join(
                "state", "conversations", f"{record['seq']:04d}-{record['step']}.jsonl"))
            self.assertTrue(os.path.isfile(self.path(record["conversation_path"])))


if __name__ == "__main__":
    unittest.main()
