"""The full dashboard: when it is written, what it embeds, and that it is safe to share (002 FR-035
to FR-042, SC-009, SC-010; contracts/full-dashboard.md)."""
import base64
import json
import os
import re
import shutil
import socket
import unittest
from datetime import datetime, timezone

import helpers  # noqa: F401 - puts the package on sys.path
import samples
from devloops import fulldash, state, ui, workspace
from stub_loop import WS, StubLoopMixin, implemented

SECRET = "S3CR3T-dashboard-value"
# The smallest valid PNG: one transparent pixel.
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA"
                       "60e6kgAAAABJRU5ErkJggg==")


class FullDashboardTest(StubLoopMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.configure()
        self.dash_dir = os.path.join(self.t.root, ".devloops", "dashboards", WS)

    def configure(self, full_on_stop=True, **extra):
        # Most of these tests are about the dashboards written at a final status, which
        # `dashboard.full_on_stop` turns on (by default only `devloops dashboard` writes one).
        self.t.make_project(self.t.root, dict({"workspaces_dir": "workspaces", "config": {
            "secrets": {"literals": [SECRET]}, "dashboard": {"full_on_stop": full_on_stop}}},
            **extra))

    def dashboards(self):
        try:
            return sorted(os.listdir(self.dash_dir))
        except FileNotFoundError:
            return []

    def completed(self):
        self.scenario({"plan": {"structured_output": samples.plan(),
                                "result": f"plan done; the key is {SECRET}"},
                       "implement": [implemented("M01-T01"), implemented("M02-T01")]})
        self.approved()
        self.assertEqual(self.cli("run"), 0, self.last_output)

    def page(self, name=None):
        name = name or self.dashboards()[-1]
        with open(os.path.join(self.dash_dir, name), encoding="utf-8") as f:
            return f.read()

    def ws(self):
        return workspace.open_workspace(WS, self.t.project(), self.t.kit(), create=False)

    # --- when it is written (FR-039) ---

    def test_written_at_a_final_status_only(self):
        self.assertEqual(self.first_run(), 10, self.last_output)
        self.assertEqual(self.dashboards(), [])
        self.assertEqual(self.cli("approve", "--no-continue"), 0, self.last_output)
        self.assertEqual(self.dashboards(), [])
        self.assertEqual(self.cli("run", "--json"), 0, self.last_output)
        [name] = self.dashboards()
        self.assertRegex(name, r"^\d{8}T\d{6}Z(-\d+)?\.html$")
        out = json.loads(self.last_output)
        self.assertEqual(out["full_dashboard"]["path"], os.path.join(self.dash_dir, name))
        self.assertEqual(out["full_dashboard"]["bytes"],
                         os.path.getsize(os.path.join(self.dash_dir, name)))
        # A command that changes nothing (the run already ended) writes no new one.
        self.cli("run")
        self.assertNotIn("full dashboard:", self.last_output)
        self.assertEqual(self.dashboards(), [name])

    def test_by_default_only_the_dashboard_command_writes_one(self):
        self.configure(full_on_stop=False)
        self.approved("--max-trials", "1")
        self.assertEqual(self.cli("run", env={"DEVLOOPS_STUB": "fail"}), 20,
                         self.last_output)
        self.assertEqual(self.dashboards(), [])
        # The summary says where files and conversations are instead.
        self.assertIn(f"files and conversations: devloops dashboard --serve --workspace {WS}",
                      self.last_output)
        self.assertEqual(self.cli("dashboard"), 0, self.last_output)
        self.assertEqual(self.dashboards(), [])  # the summary page only
        self.assertEqual(self.cli("dashboard", "--export"), 0, self.last_output)
        self.assertEqual(len(self.dashboards()), 1)

    def test_full_on_stop_follows_the_project_files_as_they_are_now(self):
        # A view preference: switched on after the run started, it applies at the next stop.
        self.configure(full_on_stop=False)
        self.approved("--max-trials", "1")
        self.configure(full_on_stop=True)
        self.assertEqual(self.cli("run", env={"DEVLOOPS_STUB": "fail"}), 20,
                         self.last_output)
        self.assertEqual(len(self.dashboards()), 1)

    def test_written_after_a_stop_on_failure(self):
        self.approved("--max-trials", "1")
        code = self.cli("run", env={"DEVLOOPS_STUB": "fail"})
        self.assertEqual(code, 20, self.last_output)
        self.assertEqual(len(self.dashboards()), 1)
        self.assertIn("full dashboard: ", self.last_output)
        # Started again without a retry grant: nothing changes, so no new one.
        self.assertEqual(self.cli("run"), 20, self.last_output)
        self.assertEqual(len(self.dashboards()), 1)

    def test_not_written_when_the_lock_is_refused(self):
        self.approved()
        before = self.dashboards()
        lock = self.path(os.path.join("state", "lock"))
        with open(lock, "w") as f:
            json.dump({"pid": os.getpid(), "host": socket.gethostname(),
                       "started_at": state.now_iso()}, f)
        self.assertEqual(self.cli("run"), 40, self.last_output)
        self.assertEqual(self.dashboards(), before)

    def test_which_endings_count_as_final(self):
        from devloops import cli
        self.assertTrue(cli._ends_final(None, "completed"))
        self.assertTrue(cli._ends_final(state.StopRun("stopped-on-input-error", "x", "m"),
                                        "stopped-on-input-error"))
        self.assertFalse(cli._ends_final(None, "awaiting-approval"))
        self.assertFalse(cli._ends_final(None, "implementing"))
        for error in (KeyboardInterrupt(), state.LockHeld("held"), state.UsageError("bad")):
            self.assertFalse(cli._ends_final(error, "completed"), error)

    # --- naming (FR-036) ---

    def test_same_second_generations_never_replace_each_other(self):
        self.completed()
        os.remove(os.path.join(self.dash_dir, self.dashboards()[0]))
        now = datetime(2026, 10, 6, 12, 0, 0, tzinfo=timezone.utc)
        first = fulldash.write(self.ws(), now=now)
        second = fulldash.write(self.ws(), now=now)
        self.assertEqual(os.path.basename(first["path"]), "20261006T120000Z.html")
        self.assertEqual(os.path.basename(second["path"]), "20261006T120000Z-2.html")
        self.assertEqual(self.dashboards(), ["20261006T120000Z-2.html", "20261006T120000Z.html"])

    # --- embedded content (FR-035, FR-040) ---

    def test_every_artifact_and_conversation_is_embedded(self):
        self.completed()
        evidence = self.path(os.path.join("state", "milestones", "M01", "trials", "1", "evidence"))
        with open(os.path.join(evidence, "shot.png"), "wb") as f:
            f.write(PNG)
        with open(os.path.join(evidence, "page.html"), "w") as f:
            f.write("<script>alert('x')</script>")
        page = self.page(self.cli_dashboard()["path"])
        self.assertIn("data:image/png;base64," + base64.b64encode(PNG).decode(), page)
        loop_files = []
        for root, _, names in os.walk(self.loop_dir):
            for name in names:
                loop_files.append(os.path.relpath(os.path.join(root, name), self.t.workspace_dir))
        expected = [p for p in loop_files if re.search(
            r"(validation|checks|plan|trial)\.json$|progress\.md$|/outputs/|/state/prompts/.*\.md$",
            p)]
        self.assertTrue(any("/state/prompts/" in p for p in expected))
        for rel in expected:
            self.assertIn(f"<code>{rel}</code>", page, rel)
        self.assertIn("&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt;", page)
        # Conversations: the fake transcript's tool use, its result, and its unknown record.
        self.assertIn("Tool: Read", page)
        self.assertIn("Result", page)
        self.assertIn("fake-internal", page)
        self.assertIn("&quot;x&quot;: 1", page)
        self.assertIn("plan done; the key is ***", page)
        records = state.read_jsonl(self.path(os.path.join("state", "invocations.jsonl")))
        for r in records:
            self.assertIn(r["session_id"], page)
            self.assertIn(f'id="call-backend-dev-{r["seq"]}"', page)
        # Each call's prompt parts and where they came from (002 FR-031).
        self.assertIn("<code>steps/plan.md</code>: packaged <code>shared/prompts/steps/plan.md</code>",
                      page)
        # The layout: one view per section, the explorer, the viewer, and every call's source.
        for view in ("overview", "backend-dev", "calls", "files", "questions", "events"):
            self.assertIn(f'<section class="view" id="{view}"', page)
        self.assertIn('<div class="explorer">', page)
        self.assertIn('<dialog class="viewer" id="viewer"', page)
        self.assertIn('data-kind="markdown"', page)
        self.assertIn('data-kind="image"', page)
        for r in records:
            self.assertIn(f'data-open="call-backend-dev-{r["seq"]}"', page)

    def test_a_file_over_the_limit_is_listed_but_not_embedded(self):
        self.completed()
        with open(self.path(os.path.join("outputs", "huge.log")), "w") as f:
            f.write("y" * (fulldash.MAX_EMBED_BYTES + 1))
        result = self.cli_dashboard()
        rel = os.path.join("backend-dev", "outputs", "huge.log")
        self.assertEqual(result["not_embedded"], [{"path": rel,
                                                   "bytes": fulldash.MAX_EMBED_BYTES + 1}])
        page = self.page(result["path"])
        self.assertLess(os.path.getsize(result["path"]), fulldash.MAX_EMBED_BYTES)
        self.assertIn(f"<code>{rel}</code>", page)
        self.assertIn('data-kind="large"', page)
        self.assertIn("Not embedded: 5.0 MB, over the 5.0 MB limit", page)
        self.assertEqual(self.cli("dashboard", "--export"), 0, self.last_output)
        self.assertIn(f"not embedded (over 5.0 MB):\n    {rel} (5.0 MB)", self.last_output)

    def test_a_missing_evidence_file_is_shown_as_missing(self):
        self.completed()
        stub = os.path.join("state", "milestones", "M01", "trials", "1", "evidence", "stub.txt")
        os.remove(self.path(stub))
        page = self.page(self.cli_dashboard()["path"])
        self.assertIn(f"missing: <code>{os.path.join('backend-dev', stub)}</code>", page)

    def test_a_conversation_that_was_not_copied_is_shown_unavailable(self):
        self.t.write_scenario({"transcript": False,
                               "steps": {"plan": {"structured_output": samples.plan()}}})
        self.assertEqual(self.first_run(), 10, self.last_output)
        record = state.read_jsonl(self.path(os.path.join("state", "invocations.jsonl")))[0]
        result = self.cli_dashboard()
        self.assertEqual(result["unavailable"], 1)
        page = self.page(result["path"])
        self.assertIn("Conversation unavailable (not-found)", page)
        self.assertIn(record["session_id"], page)

    def test_an_older_record_reads_the_history(self):
        self.assertEqual(self.first_run(), 10, self.last_output)
        path = self.path(os.path.join("state", "invocations.jsonl"))
        records = state.read_jsonl(path)
        for r in records:  # as written before conversations were copied
            for key in ("conversation", "conversation_path", "conversation_reason"):
                r.pop(key, None)
        shutil.rmtree(self.path(os.path.join("state", "conversations")))
        with open(path, "w") as f:
            f.writelines(json.dumps(r) + "\n" for r in records)
        page = self.page(self.cli_dashboard()["path"])
        self.assertIn("read from Claude Code's history", page)
        self.assertIn("Tool: Read", page)

    # --- self-contained and safe (FR-041, SC-009, SC-010) ---

    def test_self_contained_and_redacted(self):
        self.completed()
        with open(self.path(os.path.join("outputs", "notes.md")), "w") as f:
            f.write(f"a note that mentions {SECRET}\n")
        page = self.page(self.cli_dashboard()["path"])
        self.assertEqual(page.count(SECRET), 0)
        project = f'href="{ui.PROJECT_URL}"'  # the one outside link: it only navigates
        self.assertEqual(page.count(project), 1)
        self.assertNotRegex(page.replace(project, ""), r"""(src|href)=["']?(https?:|//)""")
        self.assertEqual(page.count("<script"), 1)
        self.assertIn(fulldash.NOTICE, page)
        self.assertIn("a note that mentions ***", page)

    def test_a_copy_elsewhere_still_shows_everything(self):
        self.completed()
        path = self.cli_dashboard()["path"]
        elsewhere = os.path.join(self.t.base, "elsewhere")
        os.makedirs(elsewhere)
        copy = shutil.copy(path, elsewhere)
        shutil.rmtree(self.t.workspace_dir)
        with open(copy, encoding="utf-8") as f:
            page = f.read()
        for anchor in re.findall(r'href="#([^"]+)"', page):
            self.assertIn(f'id="{anchor}"', page, anchor)
        self.assertNotRegex(page.replace(f'href="{ui.PROJECT_URL}"', ""),
                            r"""(src|href)=["'](?!#|data:)""")

    # --- the dashboard command ---

    def cli_dashboard(self, *args):
        self.assertEqual(self.cli("dashboard", "--export", "--json", *args), 0, self.last_output)
        out = json.loads(self.last_output)
        return out.get("full_dashboard")

    def test_dashboard_command_reports_the_largest_items(self):
        self.completed()
        full = self.cli_dashboard()
        self.assertTrue(os.path.isfile(full["path"]))
        self.assertEqual(full["bytes"], os.path.getsize(full["path"]))
        self.assertTrue(1 <= len(full["largest"]) <= 5)
        sizes = [i["bytes"] for i in full["largest"]]
        self.assertEqual(sizes, sorted(sizes, reverse=True))
        self.assertEqual(self.cli("dashboard", "--export"), 0, self.last_output)
        self.assertIn("largest embedded items:", self.last_output)

    def test_export_to_a_named_file(self):
        self.completed()
        before = self.dashboards()
        out = os.path.join(self.t.base, "share", "run.html")
        full = self.cli_dashboard("--out", out)
        self.assertEqual(full["path"], out)
        self.assertEqual(self.dashboards(), before)  # not in the dashboards folder
        with open(out, encoding="utf-8") as f:
            self.assertIn(fulldash.NOTICE, f.read())
        self.cli_dashboard("--out", out)  # replaced, not refused
        self.assertEqual(os.listdir(os.path.dirname(out)), ["run.html"])

    def test_dashboard_without_export_writes_no_full_dashboard(self):
        self.completed()
        before = self.dashboards()
        for args in ([], ["--light"]):  # --light: what earlier versions needed for this
            self.assertEqual(self.cli("dashboard", "--json", *args), 0, self.last_output)
            self.assertNotIn("full_dashboard", json.loads(self.last_output))
        self.assertEqual(self.dashboards(), before)

    # --- failures (FR-039) ---

    def test_a_write_failure_warns_and_keeps_the_exit_code(self):
        os.makedirs(os.path.join(self.t.root, ".devloops"), exist_ok=True)
        with open(os.path.join(self.t.root, "not-a-dir"), "w") as f:
            f.write("a file where the dashboards folder should be")
        self.configure(dashboards_dir="not-a-dir")
        self.approved()
        self.assertEqual(self.cli("run"), 0, self.last_output)
        self.assertIn("devloops: warning: could not write the full dashboard", self.last_output)
        self.assertEqual(self.run_state()["status"], "completed")

    # --- links and status (FR-036a) ---

    def test_the_lightweight_page_and_status_list_them(self):
        self.completed()
        self.cli_dashboard()
        names = self.dashboards()
        self.assertEqual(len(names), 2)
        with open(os.path.join(self.t.workspace_dir, "dashboard.html"), encoding="utf-8") as f:
            light = f.read()
        def when(name):
            stamp, _, n = name[:-len(".html")].partition("-")
            return stamp, int(n or 1)
        newest, oldest = sorted(names, key=when, reverse=True)
        links = re.findall(r'href="([^"]+\.html)"', light)
        rel = os.path.relpath(self.dash_dir, self.t.workspace_dir)
        self.assertEqual(links[:2], [os.path.join(rel, newest), os.path.join(rel, oldest)])
        self.assertEqual(self.cli("status", "--json"), 0, self.last_output)
        status = json.loads(self.last_output)
        self.assertEqual(status["full_dashboards"]["count"], 2)
        self.assertEqual(status["full_dashboards"]["latest"], os.path.join(self.dash_dir, newest))
        self.assertEqual(status["loops"]["backend-dev"]["full_dashboards"]["count"], 2)
        self.cli("status")
        self.assertIn("full dashboards: 2", self.last_output)


if __name__ == "__main__":
    unittest.main()
