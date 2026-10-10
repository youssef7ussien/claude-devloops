"""The dashboards' shared shell and components (ui.py, assets/): file kinds, embedding, the page."""
import os
import shutil
import subprocess
import unittest

import helpers  # noqa: F401 - puts the package on sys.path
from devloops import dashboard, ui

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
