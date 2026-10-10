"""The dashboard app's browser code (assets/app/; specs/005-dashboard-redesign research R-13).

Every script is listed in `scripts.txt` and the joined script parses; the pure logic (Markdown,
routing, formatting, charts) is tested with `node --test` on `assets/app/tests/`. Node is a test
tool only: those two tests are skipped without it. The source checks run always: no script builds
HTML from text (FR-026), and nothing loads from outside the page (FR-027). The copied-in
`vendor/` files (Prism, research R-16) are exempt from the markup check only, and the app may call
Prism only to tokenize (FR-033).
"""
import glob
import json
import os
import random
import re
import shutil
import subprocess
import tempfile
import unittest

import helpers  # noqa: F401 - puts the package on sys.path
from devloops import appbundle, artifacts

NODE = shutil.which("node")
APP = appbundle.APP
HTML_SINKS = re.compile(r"\b(innerHTML|outerHTML|insertAdjacentHTML|document\.write)\b")
PRISM_HTML = re.compile(r"\bPrism\.(highlight|highlightElement|highlightAll|highlightAllUnder)\b")
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
            if not appbundle.is_vendor(rel):
                self.assertIsNone(HTML_SINKS.search(text), rel)
                self.assertIsNone(PRISM_HTML.search(text), rel)  # Prism's HTML output, FR-033

    def test_vendor_files_are_served_but_not_exported(self):
        vendor = [n for n in appbundle.script_names() if appbundle.is_vendor(n)]
        self.assertIn("vendor/prism/prism-core.min.js", vendor)
        names = appbundle.script_names()
        self.assertLess(names.index(vendor[-1]), names.index("highlight.js"))
        self.assertIn("Prism.languages", appbundle.script())
        self.assertNotIn("Prism.languages", appbundle.script(vendor=False))
        self.assertTrue(os.path.exists(os.path.join(APP, "vendor", "prism", "LICENSE")))

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
        self.assertNotIn("Prism.languages", inline)  # the export leaves the vendor files out (FR-033)
        self.assertIn("<style>", inline)
        self.assertIn('id="d:x"', inline)
        body = inline.split("<script>", 1)[1].rsplit("</script>", 1)[0]
        self.assertNotIn("</", body)  # the inlined script cannot end its element early


@unittest.skipUnless(NODE, "needs node to check the app's scripts")
class NodeTest(unittest.TestCase):
    def test_the_joined_script_parses(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "app.js")
            for vendor in (True, False):
                with open(path, "w", encoding="utf-8") as f:
                    f.write(appbundle.script(vendor))
                proc = subprocess.run([NODE, "--check", path], capture_output=True, text=True,
                                      timeout=60)
                self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_change_counts_match_the_app(self):
        """The trial view's line counts come from the server (FR-018d): they must be the counts of
        the app's own diff, which its change dialog shows."""
        rng = random.Random(5)
        words = ["a", "b", "c", "", "  d", "e\t"]
        cases = [["", ""], ["x", ""], ["a\n", "a"], ["a\nb\n", "b\na\n"]]
        for _ in range(200):
            cases.append(["\n".join(rng.choice(words) for _ in range(rng.randint(0, 12)))
                          + rng.choice(["", "\n"]) for _ in range(2)])
        big = "\n".join(str(k) for k in range(600))
        cases.append([big, big[::-1]])
        script = ("const DL = require(%s)(['actions.js']);"
                  "const cases = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
                  "process.stdout.write(JSON.stringify(cases.map(([a, b]) => {"
                  "const d = DL.actions.diff(a, b); return [d.added, d.removed]; })));"
                  % json.dumps(os.path.join(APP, "tests", "load.js")))
        proc = subprocess.run([NODE, "-e", script], input=json.dumps(cases), capture_output=True,
                              text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout),
                         [list(artifacts.diff_counts(a, b)) for a, b in cases])

    def test_the_browser_logic(self):
        tests = sorted(glob.glob(os.path.join(APP, "tests", "*.test.js")))
        self.assertTrue(tests)
        proc = subprocess.run([NODE, "--test", *tests], capture_output=True, text=True,
                              timeout=300, cwd=APP)
        self.assertEqual(proc.returncode, 0, proc.stdout[-4000:] + proc.stderr[-2000:])


if __name__ == "__main__":
    unittest.main()
