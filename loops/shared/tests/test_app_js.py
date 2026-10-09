"""The dashboard app's browser code (assets/app/; specs/005-dashboard-redesign research R-13).

Every script is listed in `scripts.txt` and the joined script parses; the pure logic (Markdown,
routing, formatting, charts) is tested with `node --test` on `assets/app/tests/`. Node is a test
tool only: those two tests are skipped without it. The source checks run always: no script builds
HTML from text (FR-026), and nothing loads from outside the page (FR-027).
"""
import glob
import os
import re
import shutil
import subprocess
import tempfile
import unittest

import helpers  # noqa: F401 - puts the package on sys.path
from devloops import appbundle

NODE = shutil.which("node")
APP = appbundle.APP
HTML_SINKS = re.compile(r"\b(innerHTML|outerHTML|insertAdjacentHTML|document\.write)\b")
OUTSIDE = re.compile(r"@import|url\(\s*['\"]?https?:|(?:src|href)\s*=\s*['\"]?https?:", re.I)


def sources():
    """Every script of the app, except its tests: `{relative path: text}`."""
    found = {}
    for path in glob.glob(os.path.join(APP, "**", "*.js"), recursive=True):
        rel = os.path.relpath(path, APP).replace(os.sep, "/")
        if rel.startswith("tests/"):
            continue
        with open(path, encoding="utf-8") as f:
            found[rel] = f.read()
    return found


class SourcesTest(unittest.TestCase):
    def test_every_script_is_listed_and_every_listed_script_exists(self):
        listed = appbundle.script_names()
        self.assertEqual(sorted(sources()), sorted(listed))
        self.assertEqual(len(listed), len(set(listed)))
        self.assertEqual(listed[0], "core.js")
        self.assertEqual(listed[-1], "main.js")

    def test_no_script_builds_html_from_text(self):
        for rel, text in sources().items():
            self.assertIsNone(HTML_SINKS.search(text), rel)

    def test_nothing_is_loaded_from_outside(self):
        for name in ("app.css", "index.html", "icons.svg"):
            with open(os.path.join(APP, name), encoding="utf-8") as f:
                text = f.read().replace(appbundle.PROJECT_URL, "")
            self.assertIsNone(OUTSIDE.search(text), name)
        for rel, text in sources().items():
            self.assertIsNone(OUTSIDE.search(text.replace(appbundle.PROJECT_URL, "")), rel)

    def test_the_shell(self):
        page = appbundle.shell("devloops · main", {"source": "api", "workspace": "<main>"})
        self.assertTrue(page.startswith("<!doctype html>"))
        self.assertIn(' data-source="api"', page)
        self.assertIn(' data-workspace="&lt;main&gt;"', page)
        self.assertIn(f'src="/assets/app.js?v={appbundle.assets_version()}"', page)
        self.assertIn(f'href="/assets/app.css?v={appbundle.assets_version()}"', page)
        self.assertNotIn("{{", page)
        self.assertNotIn("style=", page)  # the served page's policy allows no inline style
        for hook in ('id="view"', 'id="now"', 'id="viewer"', 'id="palette"', 'id="tip"',
                     'id="i-github"', "data-crumb", "data-status", 'class="nav"'):
            self.assertIn(hook, page)
        inline = appbundle.shell("t", {"source": "embedded"}, inline=True,
                                 data='<script type="application/json" id="d:x">{}</script>')
        self.assertNotIn("/assets/app.js", inline)
        self.assertIn("<style>", inline)
        self.assertIn('id="d:x"', inline)
        body = inline.split("<script>", 1)[1].rsplit("</script>", 1)[0]
        self.assertNotIn("</", body)  # the inlined script cannot end its element early


@unittest.skipUnless(NODE, "needs node to check the app's scripts")
class NodeTest(unittest.TestCase):
    def test_the_joined_script_parses(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "app.js")
            with open(path, "w", encoding="utf-8") as f:
                f.write(appbundle.script())
            proc = subprocess.run([NODE, "--check", path], capture_output=True, text=True,
                                  timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_the_browser_logic(self):
        tests = sorted(glob.glob(os.path.join(APP, "tests", "*.test.js")))
        self.assertTrue(tests)
        proc = subprocess.run([NODE, "--test", *tests], capture_output=True, text=True,
                              timeout=300, cwd=APP)
        self.assertEqual(proc.returncode, 0, proc.stdout[-4000:] + proc.stderr[-2000:])


if __name__ == "__main__":
    unittest.main()
