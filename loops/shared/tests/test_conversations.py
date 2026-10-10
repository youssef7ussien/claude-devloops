"""Each call's Claude Code conversation is copied, redacted, into the workspace (002 FR-040 to
FR-042, research P-9), and parsed into records for the dashboard: redacted, with failed tool results
and the files the call changed (artifacts.parse_conversation; specs/005-dashboard-redesign R-7)."""
import json
import os
import unittest

import helpers  # noqa: F401 - puts the package on sys.path
import samples
from devloops import artifacts, state
from devloops.redact import Redactor
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


# --- parsing for the dashboard ----------------------------------------------------------------

def lines(*records):
    return "\n".join(r if isinstance(r, str) else json.dumps(r) for r in records) + "\n"


def tool_use(name, **data):
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "t", "name": name, "input": data}]}}


def result(text, error=False):
    return {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "t", "content": text, "is_error": error}]}}


class ParseConversationTest(unittest.TestCase):
    def setUp(self):
        self.redactor = Redactor({"secrets": {"env": [], "literals": [SECRET]}}, environ={})

    def parse(self, text):
        return artifacts.parse_conversation(text, self.redactor)

    def test_records_are_parsed_and_redacted(self):
        parsed = self.parse(lines({"type": "system", "subtype": "init"}, "",
                                  {"type": "assistant", "message": {"content": [
                                      {"type": "text", "text": f"the key is {SECRET}"}]}}))
        self.assertEqual(len(parsed["records"]), 2)  # the blank line is not a record
        self.assertEqual(parsed["records"][1]["message"]["content"][0]["text"], "the key is ***")
        self.assertNotIn(SECRET, json.dumps(parsed))
        self.assertEqual((parsed["errors"], parsed["files_changed"]), ([], []))

    def test_a_line_that_is_not_json_is_kept_raw(self):
        parsed = self.parse(lines({"type": "system"}, f"not json {SECRET}"))
        self.assertEqual(parsed["records"][1], {"raw": "not json ***"})

    def test_a_line_separator_inside_a_string_does_not_split_a_record(self):
        text = json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "one two"}]}}, ensure_ascii=False)
        parsed = self.parse(text + "\n")
        self.assertEqual(len(parsed["records"]), 1)
        self.assertEqual(parsed["records"][0]["message"]["content"][0]["text"], "one two")

    def test_failed_tool_results_are_listed(self):
        parsed = self.parse(lines(tool_use("Bash", command="ls"), result("ok"),
                                  tool_use("Bash", command="false"), result("exit 1", error=True)))
        self.assertEqual(parsed["errors"], [3])

    def test_files_changed_keep_the_last_change_of_each_path(self):
        parsed = self.parse(lines(
            tool_use("Write", file_path="/t/a.py", content="x"),
            tool_use("Edit", file_path="/t/b.py", old_string="a", new_string="b"),
            tool_use("Read", file_path="/t/c.py"),
            tool_use("Edit", file_path="/t/a.py", old_string="x", new_string="y"),
            tool_use("MultiEdit", file_path="/t/d.py", edits=[]),
            tool_use("NotebookEdit", notebook_path="/t/e.ipynb", new_source="")))
        self.assertEqual(parsed["files_changed"], [  # lines of all of a path's changes
            {"path": "/t/b.py", "tool": "Edit", "block": 1, "added": 1, "removed": 1},
            {"path": "/t/a.py", "tool": "Edit", "block": 3, "added": 2, "removed": 1},
            {"path": "/t/d.py", "tool": "MultiEdit", "block": 4, "added": 0, "removed": 0},
            {"path": "/t/e.ipynb", "tool": "NotebookEdit", "block": 5, "added": 0, "removed": 0}])

    def test_change_counts(self):
        self.assertEqual(artifacts.diff_counts("a\nb\nc\nd", "a\nx\nc\nd\ne"), (2, 1))
        self.assertEqual(artifacts.diff_counts("", "n\n"), (1, 0))
        self.assertEqual(artifacts.diff_counts("same", "same"), (0, 0))
        big = "\n".join(str(k) for k in range(600))
        self.assertEqual(artifacts.diff_counts(big, big[::-1]), (600, 600))  # over DIFF_CELLS
        self.assertEqual(artifacts.edit_counts("MultiEdit", {"edits": [
            {"old_string": "a", "new_string": "b\nc"}, "junk", {"old_string": "x"}]}), (2, 2))
        self.assertEqual(artifacts.edit_counts("Write", {"content": "1\n2\n"}), (2, 0))
        self.assertEqual(artifacts.edit_counts("NotebookEdit", {"new_source": "x"}), (0, 0))


if __name__ == "__main__":
    unittest.main()
