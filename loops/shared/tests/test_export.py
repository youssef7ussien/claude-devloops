"""`devloops export-sessions [--csv <file>]` (T072; FR-033)."""
import csv
import io
import os
import unittest

import helpers  # noqa: F401
from devloops import cli, workspace
from stub_loop import StubLoopMixin, WS

COLUMNS = ["workspace", "loop", "step", "milestone", "trial", "session_id", "prompt_path",
           "input_tokens", "output_tokens", "cache_creation_tokens", "cache_read_tokens",
           "cost_usd", "started_at", "ended_at"]


class ExportSessionsTest(StubLoopMixin, unittest.TestCase):
    def completed(self):
        self.approved()
        self.assertEqual(self.cli("run", "backend-dev"), 0, self.last_output)

    def rows(self, text):
        reader = csv.DictReader(io.StringIO(text))
        self.assertEqual(reader.fieldnames, COLUMNS)
        return list(reader)

    def test_every_invocation_becomes_a_row(self):
        self.completed()
        path = os.path.join(self.t.base, "sessions.csv")
        self.assertEqual(self.cli("export-sessions", "--csv", path), 0, self.last_output)
        self.assertIn("3 invocation(s) written", self.last_output)
        with open(path, encoding="utf-8", newline="") as f:
            rows = self.rows(f.read())

        calls = self.t.fake_calls()
        self.assertEqual([(r["loop"], r["step"], r["milestone"], r["trial"]) for r in rows],
                         [("backend-dev", "plan", "", "1"), ("backend-dev", "implement", "M01", "1"),
                          ("backend-dev", "implement", "M02", "1")])
        self.assertEqual([r["session_id"] for r in rows], [c["session_id"] for c in calls])
        for row in rows:
            self.assertEqual(row["workspace"], WS)
            # The prompt path is relative to the workspace and names the stored prompt.
            self.assertTrue(row["prompt_path"].startswith("backend-dev/state/prompts/"), row)
            self.assertTrue(os.path.isfile(os.path.join(self.t.workspace_dir,
                                                        row["prompt_path"])), row)
            for column in ("input_tokens", "output_tokens", "cost_usd", "started_at",
                           "ended_at"):
                self.assertNotEqual(row[column], "", (column, row))

    def test_without_csv_it_writes_to_standard_output(self):
        self.completed()
        code, out, err = self.t.run_cli(["export-sessions", "--workspace", WS])
        self.assertEqual(code, 0, out + err)
        self.assertEqual(len(self.rows(out)), 3)

    def test_a_loop_that_never_ran_adds_no_rows(self):
        self.completed()
        ws = workspace.open_workspace(WS, self.t.project(), self.t.kit(), create=False)
        self.assertEqual({r["loop"] for r in cli.session_rows(ws)}, {"backend-dev"})

    def test_an_unknown_workspace_is_a_usage_error(self):
        code, out, err = self.t.run_cli(["export-sessions", "--workspace", "no-such-ws"])
        self.assertEqual(code, 2, out + err)
        self.assertIn("does not exist", err)


if __name__ == "__main__":
    unittest.main()
