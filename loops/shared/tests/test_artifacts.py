"""The workspace's files as the dashboard lists and shows them (artifacts.py; specs/005-dashboard-
redesign data-model "Files")."""
import base64
import json
import os
import re
import tempfile
import unittest
from unittest import mock

import helpers  # noqa: F401 - puts the package on sys.path
import samples
from devloops import artifacts, dashboard, workspace
from devloops.redact import Redactor
from stub_loop import WS, StubLoopMixin, implemented
from samples import PNG

SECRET = "S3CR3T-artifacts-value"


class FileKindTest(unittest.TestCase):
    def test_kind_by_extension_then_content(self):
        cases = {
            ("notes.md", "# Title"): ("markdown", ""),
            ("plan.json", "{}"): ("json", ""),
            ("stream.jsonl", '{"a": 1}'): ("jsonl", ""),
            ("server.py", "print(1)"): ("code", "python"),
            ("C1.command", "curl -sS x"): ("code", "shell"),
            ("C1.headers", "HTTP/1.1 200 OK"): ("code", "http"),
            ("runtime.log", "started"): ("log", ""),
            ("C1.body", '{"status": "ok"}'): ("json", ""),   # JSON by content
            ("C2.body", "not found"): ("text", ""),
            ("shot.png", None): ("image", ""),
            ("blob.bin", None): ("binary", ""),
        }
        for (path, text), expected in cases.items():
            self.assertEqual(artifacts.kind_of(path, text)[:2], expected, path)


class FileContentTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.redactor = Redactor({"secrets": {"env": [], "literals": [SECRET]}}, environ={})

    def write(self, name, data):
        path = os.path.join(self.tmp.name, name)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def content(self, path, max_bytes=artifacts.MAX_EMBED_BYTES):
        return artifacts.file_content(path, self.redactor, max_bytes)

    def test_text_is_redacted(self):
        path = self.write("notes.md", f"# Notes\nthe key is {SECRET}\n".encode())
        self.assertEqual(self.content(path), {"kind": "markdown", "lang": "", "size": 42,
                                              "text": "# Notes\nthe key is ***\n"})

    def test_json_is_indented_and_redacted(self):
        path = self.write("a.json", json.dumps({"key": SECRET, "n": [1]}).encode())
        got = self.content(path)
        self.assertEqual(got["kind"], "json")
        self.assertEqual(got["text"], '{\n  "key": "***",\n  "n": [\n    1\n  ]\n}')
        self.assertEqual(self.content(self.write("b.py", b"x = 1\n"))["lang"], "python")

    def test_images_and_binary_files_are_base64(self):
        got = self.content(self.write("shot.png", PNG))
        self.assertEqual(got, {"kind": "image", "size": len(PNG), "type": "image/png",
                               "base64": base64.b64encode(PNG).decode()})
        got = self.content(self.write("blob.bin", b"\x00\x01\xff"))
        self.assertEqual((got["kind"], got["type"], base64.b64decode(got["base64"])),
                         ("binary", "application/octet-stream", b"\x00\x01\xff"))

    def test_a_large_file_is_not_embedded(self):
        path = self.write("big.log", b"y" * 2000)
        self.assertEqual(self.content(path, max_bytes=1000),
                         {"kind": "large", "size": 2000, "not_embedded": True})
        self.assertEqual(self.content(path, max_bytes=None)["size"], 2000)

    def test_an_unreadable_file(self):
        self.assertIsNone(self.content(os.path.join(self.tmp.name, "gone.txt")))


def walk(nodes):
    for node in nodes:
        if "file" in node:
            yield node["file"]
        yield from walk(node.get("children") or [])


class FileIndexTest(StubLoopMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.t.make_project(self.t.root, {"workspaces_dir": "workspaces",
                                          "config": {"secrets": {"literals": [SECRET]}}})
        self.scenario({"plan": {"structured_output": samples.plan()},
                       "implement": [implemented("M01-T01"), implemented("M02-T01")]})
        self.approved()
        self.assertEqual(self.cli("run"), 0, self.last_output)

    def ws(self):
        return workspace.open_workspace(WS, self.t.project(), self.t.kit(), create=False)

    def index(self):
        ws = self.ws()
        return artifacts.file_index(ws, dashboard.collect(ws))

    def test_the_ids_and_files_are_todays(self):
        index = self.index()
        files = list(walk(index["trees"]))
        self.assertEqual(index["count"], len(files))
        self.assertEqual(set(index["by_id"]), {ref["id"] for ref in files})
        for ref in files:
            slug = re.sub(r"[^A-Za-z0-9]+", "-", ref["path"]).strip("-").lower()
            self.assertRegex(ref["id"], rf"^f-{re.escape(slug)}(-\d+)?$", ref)
        self.assertFalse([f for f in files if f["path"].endswith(".jsonl")
                          and "/conversations/" in f["path"]])

    def test_the_trees(self):
        index = self.index()
        top = index["trees"][0]
        self.assertEqual((top["name"], top["badge"], top["open"]),
                         ("backend-dev", {"status": "completed", "table": "run"}, True))
        files = [n["file"]["path"] for n in top["children"] if "file" in n]  # after the folders
        self.assertEqual(files[0], "backend-dev/progress.md")
        names = [n["name"] for n in top["children"] if "children" in n]
        self.assertEqual(names, ["Inputs", "Plan", "Milestones", "Calls", "Outputs", "Run state"])
        milestones = next(n for n in top["children"] if n["name"] == "Milestones")
        m01 = milestones["children"][0]
        self.assertEqual((m01["name"], m01["badge"]), ("M01", {"status": "achieved",
                                                                "table": "milestone"}))
        trial = next(n for n in m01["children"] if n["name"] == "Trial 1")
        self.assertEqual(trial["badge"], {"status": "passed", "table": "trial"})
        plan = next(f for f in walk(index["trees"]) if f["path"] == "backend-dev/state/plan.json")
        st = os.stat(self.path(os.path.join("state", "plan.json")))
        self.assertEqual(plan["version"], f"{st.st_size}-{st.st_mtime_ns}")
        self.assertEqual((plan["kind"], plan["size"]), ("json", st.st_size))

    def test_an_input_outside_the_workspace_and_a_missing_file(self):
        index = self.index()
        rel = self.t.project().relative_or_absolute(self.prd)
        [prd] = [f for f in walk(index["trees"]) if f["path"] == rel]
        self.assertIn(prd["id"], index["inputs"])
        self.assertEqual(index["by_id"][prd["id"]], self.prd)
        os.remove(self.prd)
        index = self.index()
        [prd] = [f for f in walk(index["trees"]) if f["path"] == rel]
        self.assertEqual(prd, {"id": prd["id"], "path": rel, "missing": True})
        self.assertNotIn(prd["id"], index["by_id"])

    def test_an_input_outside_labelled_like_a_workspace_file_keeps_its_own_id(self):
        # An input inside the project is labelled project-relative; here, as a workspace file is.
        rel = "notes/prd.md"
        twin = os.path.join(self.ws().path, "notes", "prd.md")  # the workspace's own file
        os.makedirs(os.path.dirname(twin))
        with open(twin, "w") as f:
            f.write("the workspace's copy\n")
        with mock.patch.object(artifacts, "_label", lambda ws, path: rel):
            index = self.index()
        found = [f for f in walk(index["trees"]) if f["path"] == rel]
        self.assertEqual(len(found), 2)
        ids = {f["id"] for f in found}
        self.assertEqual(len(ids), 2)
        self.assertEqual({index["by_id"][i] for i in ids}, {self.prd, twin})
        [outside] = [i for i in ids if index["by_id"][i] == self.prd]
        self.assertEqual(index["inputs"], {outside})


if __name__ == "__main__":
    unittest.main()
