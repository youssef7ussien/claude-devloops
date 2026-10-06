"""The dashboards' shared shell and components (ui.py, assets/): file kinds, embedding, the page."""
import os
import shutil
import subprocess
import tempfile
import unittest

import helpers  # noqa: F401 - puts the package on sys.path
from devloops import dashboard, fulldash, ui
from devloops.redact import Redactor

NODE = shutil.which("node")


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
            self.assertEqual(ui.kind_of(path, text)[:2], expected, path)


class EmbedTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.redactor = Redactor({"secrets": {"env": [], "literals": ["hunter2"]}}, environ={})

    def write(self, name, data):
        path = os.path.join(self.tmp.name, name)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def test_json_found_by_content_is_indented_and_redacted(self):
        path = self.write("C1.body", b'{"status":"ok","token":"hunter2"}')
        kind, _, _, content, size = fulldash.embed(path, self.redactor)
        self.assertEqual((kind, size), ("json", 33))
        self.assertIn("{\n  &quot;status&quot;: &quot;ok&quot;,\n  &quot;token&quot;: &quot;***&quot;",
                      content)
        self.assertNotIn("hunter2", content)

    def test_markdown_stays_text_for_the_viewer(self):
        kind, _, ic, content, _ = fulldash.embed(self.write("a.md", b"# T\n<b>x</b>"), self.redactor)
        self.assertEqual((kind, ic), ("markdown", "md"))
        self.assertIn('<pre class="src"># T\n&lt;b&gt;x&lt;/b&gt;</pre>', content)

    def test_a_file_node_is_labelled_and_tagged_with_its_kind(self):
        node = ui.file_node("f-a", "backend-dev/outputs/a.md", "markdown", "", "md", "5 bytes",
                            "milestone M01", "<pre class=\"src\">x</pre>")
        for part in ('id="f-a"', 'data-kind="markdown"', 'data-path="backend-dev/outputs/a.md"',
                     "<code>backend-dev/outputs/a.md</code>", "5 bytes · milestone M01",
                     '<span class="nm">a.md</span>'):
            self.assertIn(part, node)

    def test_a_file_over_the_limit_is_not_embedded(self):
        path = self.write("huge.log", b"x" * 2048)
        kind, _, _, content, size = fulldash.embed(path, self.redactor, max_bytes=1024)
        self.assertEqual((kind, size), ("large", 2048))
        self.assertIn("Not embedded: 2.0 KB, over the 1.0 KB limit", content)
        self.assertNotIn("xxxx", content)

    def test_unreadable_is_none(self):
        self.assertIsNone(fulldash.embed(os.path.join(self.tmp.name, "gone.txt"), self.redactor))


class TreeTest(unittest.TestCase):
    def test_folders_count_and_order(self):
        top = ui.Dir("backend-dev", open_=True)
        top.dir("Outputs").files.append("<x>")
        top.dir("Inputs").files += ["<a>", "<b>"]
        top.dir("Inputs").dir("deep").files.append("<c>")
        top.order(["Inputs", "Outputs"])
        self.assertEqual(list(top.dirs), ["Inputs", "Outputs"])
        self.assertEqual(top.count(), 4)
        html_ = top.html()
        self.assertTrue(html_.startswith('<li class="d"><details class="dir" open>'))
        self.assertLess(html_.index("Inputs"), html_.index("Outputs"))


class ChartTest(unittest.TestCase):
    def test_bar_chart_has_no_table_view_but_a_screen_reader_table(self):
        out = dashboard.bar_chart([("plan", 0.5, "plan: $0.50")], dashboard.money, "Cost by step",
                                  ("Step", "Cost"))
        self.assertNotIn("Table view", out)
        self.assertIn('<table class="sr-only"><caption>Cost by step</caption>', out)
        self.assertIn("<td>$0.50</td>", out)


class PageTest(unittest.TestCase):
    def test_the_shell(self):
        page = ui.page("t", "<aside></aside>", "<header></header>", [ui.view("overview", "Overview", "")])
        self.assertEqual(page.count("<script"), 1)
        for part in ('id="viewer"', 'id="palette"', 'id="i-github"', 'id="overview"',
                     "class='no-js'"):
            self.assertIn(part, page)
        side = ui.sidebar("main", "dashboard", [("Run", [ui.nav_link("overview", "Overview", "grid")])],
                          "now", "1.0")
        self.assertIn(f'href="{ui.PROJECT_URL}" target="_blank" rel="noopener noreferrer"', side)
        self.assertIn(f"by {ui.OWNER}", side)

    @unittest.skipUnless(NODE, "needs node to check the script's syntax")
    def test_the_script_parses(self):
        proc = subprocess.run([NODE, "--check", os.path.join(ui.ASSETS, "dashboard.js")],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
