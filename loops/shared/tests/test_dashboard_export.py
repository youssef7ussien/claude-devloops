"""`devloops dashboard --export`: the dashboard app in one file with its data embedded
(specs/005-dashboard-redesign contracts/export.md, FR-028–FR-030, SC-007, SC-008)."""
import base64
import html
import json
import os
import re
import shutil
import unittest
from datetime import datetime, timezone
from unittest import mock

import helpers  # noqa: F401 - puts the package on sys.path
import samples
from devloops import appbundle, artifacts, dashboard, dashboard_export, serve, state, workspace
from stub_loop import WS, StubLoopMixin, implemented

SECRET = "S3CR3T-export-value"
DATA = re.compile(r'<script type="application/json" id="d:([^"<]+)">(.*?)</script>', re.S)
CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; "
       "base-uri 'none'; form-action 'none'")


class ExportTest(StubLoopMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.t.make_project(self.t.root, {"workspaces_dir": "workspaces",
                                          "config": {"secrets": {"literals": [SECRET]}}})
        self.exports = os.path.join(self.t.workspace_dir, "exports")

    def completed(self):
        self.scenario({"plan": {"structured_output": samples.plan(),
                                "result": f"plan done; the key is {SECRET}"},
                       "implement": [implemented("M01-T01"), implemented("M02-T01")]})
        self.approved()
        self.assertEqual(self.cli("run"), 0, self.last_output)

    def ws(self):
        return workspace.open_workspace(WS, self.t.project(), self.t.kit(), create=False)

    def export(self, *args):
        self.assertEqual(self.cli("dashboard", "--export", *args, "--json"), 0, self.last_output)
        out = json.loads(self.last_output)
        self.assertEqual(out["workspace"], WS)
        return out["export"]

    def read(self, path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    def data(self, page):
        return {key: json.loads(text) for key, text in DATA.findall(page)}

    def root_attrs(self, page):
        tag = re.search(r"<html[^>]*>", page).group(0)
        return {k: html.unescape(v) for k, v in re.findall(r'data-([a-z-]+)="([^"]*)"', tag)}

    # --- name and location ---

    def test_default_path_and_same_second_exports(self):
        self.completed()
        report = self.export()
        self.assertEqual(os.path.dirname(report["path"]), self.exports)
        self.assertRegex(os.path.basename(report["path"]), r"^\d{8}T\d{6}Z\.html$")
        self.assertEqual(report["bytes"], os.path.getsize(report["path"]))
        now = datetime(2026, 10, 6, 12, 0, 0, tzinfo=timezone.utc)
        first = dashboard_export.write(self.ws(), env=self.t.env, now=now)
        second = dashboard_export.write(self.ws(), env=self.t.env, now=now)
        self.assertEqual(os.path.basename(first["path"]), "20261006T120000Z.html")
        self.assertEqual(os.path.basename(second["path"]), "20261006T120000Z-2.html")
        self.assertEqual(len(os.listdir(self.exports)), 3)

    def test_a_given_path_is_written_and_replaced(self):
        self.completed()
        out = os.path.join(self.t.base, "share", "run.html")
        self.assertEqual(self.export(out)["path"], out)
        self.export(out)  # replaced, not refused
        self.assertEqual(os.listdir(os.path.dirname(out)), ["run.html"])
        self.assertFalse(os.path.exists(self.exports))

    def test_the_text_report(self):
        self.completed()
        self.assertEqual(self.cli("dashboard", "--export"), 0, self.last_output)
        self.assertIn(f"export: {self.exports}{os.sep}", self.last_output)
        self.assertIn("largest embedded items:", self.last_output)

    def test_usage_errors(self):
        self.completed()
        for extra in (["--port", "9000"], ["--no-open"], ["--stop"]):
            code = self.cli("dashboard", "--export", *extra)
            self.assertEqual(code, 2, (extra, self.last_output))

    # --- structure ---

    def test_the_page_holds_the_app_and_every_answer(self):
        self.completed()
        evidence = self.path(os.path.join("state", "milestones", "M01", "trials", "1", "evidence"))
        with open(os.path.join(evidence, "shot.png"), "wb") as f:
            f.write(samples.PNG)
        with open(os.path.join(evidence, "page.html"), "w") as f:
            f.write("<script>alert('x')</script><!-- c -->")
        report = self.export()
        page = self.read(report["path"])
        attrs = self.root_attrs(page)
        self.assertEqual(attrs["source"], "embedded")
        self.assertEqual(attrs["workspace"], WS)
        self.assertEqual(attrs["running"], "false")
        self.assertRegex(attrs["exported-at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertEqual(attrs["devloops-version"], appbundle.__version__)
        self.assertIn(f'<meta http-equiv="Content-Security-Policy" content="{CSP}">', page)
        self.assertNotIn("WorkerGlobalScope", page)  # no Prism: no highlighting (FR-033)
        data = self.data(page)
        # Every element is its server answer; `</` never appears inside one.
        for _, text in DATA.findall(page):
            self.assertNotIn("</", text)
            self.assertNotIn("<!--", text)
        ws = self.ws()
        site = serve.Site(self.t.project(), self.t.kit(), self.t.env)
        index = data["index"]["items"]
        for item in index:  # every view, loop, milestone, trial, call, and file of the index
            route = item["route"]
            path = self.api_path(route)
            self.assertIn(path, data, route)
            if path.startswith("files/"):
                continue
            status, body, _ = site.answer(ws, path)
            self.assertEqual(status, 200, path)
            served, embedded = json.loads(body), dict(data[path])
            if path == "summary":  # the server's own: its workspaces, version, and time
                for key in ("workspaces", "version", "generated_at"):
                    del served[key], embedded[key]
            self.assertEqual(embedded, served, path)
        for kind in ("view", "loop", "trial", "call", "file"):
            self.assertTrue([i for i in index if i["kind"] == kind], kind)
        # Files: text as the server sends it, images as base64.
        refs = {i["detail"]: i["route"].rsplit("/", 1)[1] for i in index if i["kind"] == "file"}
        rel = "backend-dev/state/milestones/M01/trials/1/evidence/"
        shot = data["files/" + refs[rel + "shot.png"]]
        self.assertEqual((shot["type"], base64.b64decode(shot["base64"])), ("image/png", samples.PNG))
        text = data["files/" + refs[rel + "page.html"]]
        self.assertEqual(text["text"], "<script>alert('x')</script><!-- c -->")
        self.assertEqual(text["text"], site_file(site, ws, refs[rel + "page.html"]))
        # Conversations are embedded whole; the search corpus covers files, calls, and events.
        records = state.read_jsonl(self.path(os.path.join("state", "invocations.jsonl")))
        for r in records:
            call = data[f"calls/backend-dev/{r['seq']}"]
            self.assertEqual(call["conversation"], "copied")
            self.assertTrue(call["records"])
        kinds = {i["kind"] for i in data["search-corpus"]["items"]}
        self.assertEqual(kinds, {"file", "call", "event"})
        self.assertIn("plan done; the key is ***", page)

    def api_path(self, route):
        """The API path the app asks for at `route` (assets/app/views/)."""
        r = route.split("?", 1)[0].lstrip("#/")
        for pattern, path in ((r"^$", "summary"), (r"^run$", "summary"),
                              (r"^loop/([^/]+)$", "loops/{0}"),
                              (r"^loop/([^/]+)/m/([^/]+)/t/([^/]+)$",
                               "loops/{0}/milestones/{1}/trials/{2}"),
                              (r"^call/([^/]+)/([^/]+)$", "calls/{0}/{1}"),
                              (r"^file/([^/]+)$", "files/{0}"),
                              (r"^(calls|files|questions|events)$", "{0}")):
            m = re.match(pattern, r)
            if m:
                return path.format(*m.groups())
        self.fail(route)

    def test_a_running_export_says_so(self):
        self.completed()
        with mock.patch.object(dashboard, "running", return_value=True):
            report = dashboard_export.write(self.ws(), env=self.t.env)
        self.assertEqual(self.root_attrs(self.read(report["path"]))["running"], "true")

    # --- limits and the report ---

    def test_a_file_over_the_limit_is_not_embedded(self):
        self.completed()
        size = artifacts.MAX_EMBED_BYTES + 1
        with open(self.path(os.path.join("outputs", "huge.log")), "w") as f:
            f.write("y" * size)
        report = self.export()
        rel = "backend-dev/outputs/huge.log"
        self.assertEqual(report["not_embedded"], [{"path": rel, "bytes": size}])
        self.assertLess(report["bytes"], artifacts.MAX_EMBED_BYTES)
        data = self.data(self.read(report["path"]))
        [entry] = [v for k, v in data.items() if k.startswith("files/") and v.get("not_embedded")]
        self.assertEqual(entry, {"not_embedded": True, "size": size, "path": rel})
        self.assertEqual(self.cli("dashboard", "--export"), 0, self.last_output)
        self.assertIn(f"not embedded (over 5.0 MB):\n    {rel} (5.0 MB)", self.last_output)

    def test_the_largest_items(self):
        self.completed()
        report = self.export()
        self.assertTrue(1 <= len(report["largest"]) <= 5)
        sizes = [i["bytes"] for i in report["largest"]]
        self.assertEqual(sizes, sorted(sizes, reverse=True))
        self.assertEqual(report["unavailable"], 0)

    def test_an_unavailable_conversation_is_counted(self):
        self.t.write_scenario({"transcript": False,
                               "steps": {"plan": {"structured_output": samples.plan()}}})
        self.assertEqual(self.first_run(), 10, self.last_output)
        report = self.export()
        self.assertEqual(report["unavailable"], 1)
        self.assertEqual(self.data(self.read(report["path"]))["calls/backend-dev/1"]["conversation"],
                         "unavailable")

    # --- self-contained and safe (SC-007, SC-008) ---

    def test_redacted_and_self_contained(self):
        self.completed()
        with open(self.path(os.path.join("outputs", "notes.md")), "w") as f:
            f.write(f"a note that mentions {SECRET}\n")
        page = self.read(self.export()["path"])
        self.assertEqual(page.count(SECRET), 0)
        self.assertIn("a note that mentions ***", page)
        project = f'href="{appbundle.PROJECT_URL}"'  # the one outside link: it only navigates
        self.assertEqual(page.count(project), 1)
        self.assertNotRegex(page.replace(project, ""), r"""(src|href)=["']?(https?:|//)""")
        self.assertNotRegex(page, r"""<(script|link|img)[^>]*\s(src|href)=""")

    def test_a_copy_elsewhere_still_holds_everything(self):
        self.completed()
        path = self.export()["path"]
        before = self.data(self.read(path))
        elsewhere = os.path.join(self.t.base, "elsewhere")
        os.makedirs(elsewhere)
        copy = shutil.copy(path, elsewhere)
        shutil.rmtree(self.t.workspace_dir)
        page = self.read(copy)
        self.assertEqual(self.data(page), before)
        # Inside the page, links are the app's addresses or the icons (`#…`), nothing else.
        self.assertNotRegex(page.replace(f'href="{appbundle.PROJECT_URL}"', ""),
                            r"""(src|href)=["'](?!#|data:)""")


def site_file(site, ws, file_id):
    """A text file as the server sends it."""
    path = site.file(ws, file_id)
    with open(path, encoding="utf-8") as f:
        return artifacts.viewer_text(artifacts.sniff(path, os.path.getsize(path), 0)[0], f.read(),
                                     site.redactor(ws))


if __name__ == "__main__":
    unittest.main()
