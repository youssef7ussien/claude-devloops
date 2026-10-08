"""`devloops dashboard --serve`: the live dashboard, its files and conversations loaded when opened,
and what keeps it safe (serve.py; 002 FR-042a to FR-042d)."""
import http.client
import io
import json
import os
import re
import signal
import threading
import unittest
from unittest import mock

import helpers  # noqa: F401 - puts the package on sys.path
import samples
from devloops import fulldash, serve, workspace
from stub_loop import WS, StubLoopMixin, implemented, wait_for

SECRET = "S3CR3T-served-value"


class ServeTest(StubLoopMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.t.make_project(self.t.root, {"workspaces_dir": "workspaces",
                                          "config": {"secrets": {"literals": [SECRET]}}})
        # These tests change files and look at once; one test checks the 1 s version cache.
        patch = mock.patch.object(serve, "VERSION_TTL", 0)
        patch.start()
        self.addCleanup(patch.stop)

    def completed(self):
        self.scenario({"plan": {"structured_output": samples.plan(),
                                "result": f"plan done; the key is {SECRET}"},
                       "implement": [implemented("M01-T01"), implemented("M02-T01")]})
        self.approved()
        self.assertEqual(self.cli("run"), 0, self.last_output)

    def ws(self, name=WS):
        return workspace.open_workspace(name, self.t.project(), self.t.kit(), create=False)

    def start(self, **options):
        """Serve in a thread on a free port; stopped when the test ends."""
        ready, holder, out = threading.Event(), {}, io.StringIO()

        def on_ready(server):
            holder["server"] = server
            ready.set()
        thread = threading.Thread(target=serve.serve, args=(self.t.project(), self.t.kit(), self.ws()),
                                  kwargs=dict(dict(port=0, env=self.t.env, out=out, err=out,
                                                   ready=on_ready),
                                              **options), daemon=True)
        thread.start()
        self.assertTrue(ready.wait(30), "the server did not start")
        server = holder["server"]

        def stop():
            server.shutdown()
            thread.join(30)
        self.addCleanup(stop)
        self.server, self.out = server, out
        return server

    def get(self, path, headers=None, method="GET"):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=60)
        try:
            conn.request(method, path, headers=headers or {})
            response = conn.getresponse()
            return response.status, {k.lower(): v for k, v in response.getheaders()}, \
                response.read()
        finally:
            conn.close()

    def page(self, name=WS):
        status, headers, body = self.get(f"/w/{name}/")
        self.assertEqual(status, 200, body)
        return body.decode("utf-8"), headers

    def anchor_of(self, page, rel):
        match = re.search(r'id="(f-[a-z0-9-]+)"[^>]*data-path="' + re.escape(rel) + '"', page)
        self.assertTrue(match, rel)
        return match.group(1)

    # --- the page and what it loads -----------------------------------------------------------------

    def test_the_page_lists_files_and_loads_each_when_opened(self):
        self.completed()
        self.write(os.path.join("outputs", "notes.md"), f"# Notes\nthe key is {SECRET}\n")
        self.start()
        status, headers, _ = self.get("/")
        self.assertEqual((status, headers["location"]), (303, f"/w/{WS}/"))
        page, headers = self.page()
        self.assertIn("default-src 'none'", headers["content-security-policy"])
        self.assertEqual(headers["cache-control"], "no-store")
        self.assertIn("data-serve='3'", page)
        self.assertRegex(page, r"data-version='[0-9a-f]{16}'")
        for view in ("overview", "backend-dev", "calls", "files", "questions", "events"):
            self.assertIn(f'<section class="view" id="{view}"', page)
        self.assertIn('class="btn live"', page)
        # Files are listed, not embedded: their content is loaded when opened.
        rel = "backend-dev/outputs/notes.md"
        anchor = self.anchor_of(page, rel)
        self.assertIn(f'data-src="file/{anchor}"', page)
        self.assertNotIn("the key is", page)
        self.assertNotIn(SECRET, page)
        status, headers, body = self.get(f"/w/{WS}/file/{anchor}")
        self.assertEqual(status, 200)
        self.assertTrue(headers["content-type"].startswith("text/plain"))
        self.assertIn("sandbox", headers["content-security-policy"])
        self.assertEqual(body.decode(), "# Notes\nthe key is ***\n")
        # JSON is indented as the viewer shows it; conversations are placeholders.
        anchor = self.anchor_of(page, "backend-dev/state/plan.json")
        _, _, body = self.get(f"/w/{WS}/file/{anchor}")
        self.assertTrue(body.decode().startswith("{\n  "))
        self.assertIn('<div class="conv-lazy" data-src="call/backend-dev/1">', page)

    def test_no_size_limit(self):
        self.completed()
        size = fulldash.MAX_EMBED_BYTES + 10
        self.write(os.path.join("outputs", "huge.log"), "y" * size)
        self.start()
        page, _ = self.page()
        anchor = self.anchor_of(page, "backend-dev/outputs/huge.log")
        self.assertNotIn('data-kind="large"', page)
        _, _, body = self.get(f"/w/{WS}/file/{anchor}")
        self.assertEqual(len(body), size)

    def test_a_conversation_loads_when_opened(self):
        self.completed()
        self.start()
        status, headers, body = self.get(f"/w/{WS}/call/backend-dev/1")
        self.assertEqual(status, 200)
        self.assertTrue(headers["content-type"].startswith("text/html"))
        text = body.decode()
        self.assertIn('<div class="conv"', text)
        self.assertIn("Tool: Read", text)
        self.assertIn("plan done; the key is ***", text)
        self.assertNotIn(SECRET, text)
        for path in (f"/w/{WS}/call/backend-dev/99", f"/w/{WS}/call/nope/1"):
            self.assertEqual(self.get(path)[0], 404, path)

    def test_images_and_binary_files(self):
        from test_full_dashboard import PNG
        self.completed()
        evidence = self.path(os.path.join("state", "milestones", "M01", "trials", "1", "evidence"))
        with open(os.path.join(evidence, "shot.png"), "wb") as f:
            f.write(PNG)
        with open(os.path.join(evidence, "blob.bin"), "wb") as f:
            f.write(b"\x00\x01\x02")
        self.start()
        page, _ = self.page()
        prefix = "backend-dev/state/milestones/M01/trials/1/evidence/"
        image = self.anchor_of(page, prefix + "shot.png")
        self.assertIn(f'<img loading="lazy" src="file/{image}"', page)
        status, headers, body = self.get(f"/w/{WS}/file/{image}")
        self.assertEqual((status, headers["content-type"], body), (200, "image/png", PNG))
        blob = self.anchor_of(page, prefix + "blob.bin")
        _, headers, body = self.get(f"/w/{WS}/file/{blob}")
        self.assertEqual(headers["content-type"], "application/octet-stream")
        self.assertIn("attachment", headers["content-disposition"])
        self.assertEqual(body, b"\x00\x01\x02")

    def test_search_reads_files_and_conversations_redacted(self):
        self.completed()
        self.write(os.path.join("outputs", "notes.md"), "one\ntwo needle-word three\n")
        self.start()
        page, _ = self.page()
        _, headers, body = self.get(f"/w/{WS}/search?q=NEEDLE-word")
        self.assertTrue(headers["content-type"].startswith("application/json"))
        [hit] = json.loads(body)["results"]
        self.assertEqual(hit, {"id": self.anchor_of(page, "backend-dev/outputs/notes.md"),
                               "kind": "file", "line": 2, "before": "two ",
                               "match": "needle-word", "after": " three"})
        _, _, body = self.get(f"/w/{WS}/search?q=fake-internal")
        kinds = {h["kind"] for h in json.loads(body)["results"]}
        self.assertIn("call", kinds)
        _, _, body = self.get(f"/w/{WS}/search?q={SECRET}")
        self.assertEqual(json.loads(body)["results"], [])

    def test_search_decodes_conversation_records(self):
        # The raw JSON line escapes quotes and non-ASCII text; the viewer shows them decoded.
        self.completed()
        record = {"type": "assistant", "message": {"content": [
            {"type": "text", "text": 'she said "quoted words" in Zürich'}]}}
        path = self.path(os.path.join("state", "conversations", "0001-plan.jsonl"))
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")  # ensure_ascii: Z\u00fcrich
        self.start()
        for query in ('"quoted words"', "zürich"):
            _, _, body = self.get(f"/w/{WS}/search?q={query.replace(' ', '%20')}"
                                  .replace('"', "%22").replace("ü", "%C3%BC"))
            hits = [h for h in json.loads(body)["results"] if h["kind"] == "call"]
            self.assertEqual([h["id"] for h in hits], ["call-backend-dev-1"], query)

    def test_a_large_text_file_is_streamed_with_secrets_hidden(self):
        self.completed()
        lines = [f"line {i} {SECRET}\n" for i in range(2000)]
        self.write(os.path.join("outputs", "big.log"), "".join(lines))
        with mock.patch.object(serve, "STREAM_BYTES", 1024), \
                mock.patch.object(serve, "STREAM_BLOCK", 700):
            self.start()
            page, _ = self.page()
            self.assertRegex(page, r'data-bytes="\d+"')
            _, headers, body = self.get(f"/w/{WS}/file/"
                                        f"{self.anchor_of(page, 'backend-dev/outputs/big.log')}")
        self.assertNotIn("content-length", headers)
        self.assertEqual(body.decode(), "".join(line.replace(SECRET, "***") for line in lines))

    def test_the_page_is_rendered_again_only_when_the_workspace_changed(self):
        self.completed()
        self.start()
        self.page()
        with mock.patch.object(fulldash, "render_full", wraps=fulldash.render_full) as render:
            for _ in range(3):
                self.page()
                self.assertEqual(self.get(f"/w/{WS}/file/f-not-a-file")[0], 404)
            self.assertEqual(render.call_count, 0)
            self.write("progress.md", "changed\n")
            self.page()
            self.assertEqual(render.call_count, 1)

    def test_the_version_is_computed_once_a_second(self):
        self.completed()
        self.start()
        with mock.patch.object(serve, "VERSION_TTL", 60):
            first = json.loads(self.get(f"/w/{WS}/version")[2])["version"]
            self.write("progress.md", "changed\n")
            self.assertEqual(json.loads(self.get(f"/w/{WS}/version")[2])["version"], first)

    def test_a_conversation_uses_the_page_anchors(self):
        self.completed()
        self.start()
        self.page()
        _, _, body = self.get(f"/w/{WS}/call/backend-dev/1")
        anchors = self.server.site.rendered(self.ws())["anchors"]
        rel = os.path.normpath(os.path.join("backend-dev", "state", "conversations",
                                            "0001-plan.jsonl"))
        self.assertIn(f'<div class="conv" id="{anchors[rel]}"', body.decode())

    # --- following a run --------------------------------------------------------------------------------

    def test_the_version_changes_with_the_workspace(self):
        self.completed()
        self.start()
        page, _ = self.page()
        _, _, body = self.get(f"/w/{WS}/version")
        version = json.loads(body)["version"]
        self.assertIn(f"data-version='{version}'", page)
        self.assertEqual(json.loads(self.get(f"/w/{WS}/version")[2])["version"], version)
        self.write("progress.md", "changed\n")
        self.assertNotEqual(json.loads(self.get(f"/w/{WS}/version")[2])["version"], version)

    def test_only_views_that_changed_get_a_new_digest(self):
        self.completed()
        self.start()
        before = dict(re.findall(r'<section class="view" id="([^"]+)"[^>]*data-hash="([0-9a-f]+)"',
                                 self.page()[0]))
        self.write(os.path.join("outputs", "new.md"), "new\n")
        after = dict(re.findall(r'<section class="view" id="([^"]+)"[^>]*data-hash="([0-9a-f]+)"',
                                self.page()[0]))
        self.assertNotEqual(before["files"], after["files"])
        for view in ("calls", "questions", "events"):
            self.assertEqual(before[view], after[view], view)

    def test_a_file_listed_after_the_page_is_found(self):
        self.completed()
        self.start()
        self.page()
        self.write(os.path.join("outputs", "later.md"), "later\n")
        anchor = "f-backend-dev-outputs-later-md"
        status, _, body = self.get(f"/w/{WS}/file/{anchor}")
        self.assertEqual((status, body), (200, b"later\n"))

    # --- workspaces ---------------------------------------------------------------------------------

    def test_one_server_switches_between_workspaces(self):
        self.completed()
        workspace.open_workspace("other", self.t.project(), self.t.kit(), create=True)
        self.start()
        page, _ = self.page()
        self.assertIn('<select class="input" data-action="workspace">', page)
        self.assertIn('<option value="other">other</option>', page)
        self.assertIn(f'<option value="{WS}" selected>', page)
        other, _ = self.page("other")
        self.assertIn("No loop has started in this workspace yet.", other)
        self.assertEqual(self.get("/w/no-such/")[0], 404)
        self.assertEqual(self.get("/w/other")[0], 303)

    # --- safety -------------------------------------------------------------------------------------

    def test_only_the_files_the_page_lists_are_sent(self):
        self.completed()
        outside = os.path.join(self.t.base, "outside.txt")
        with open(outside, "w") as f:
            f.write("not for the dashboard\n")
        os.symlink(outside, self.path(os.path.join("outputs", "link.txt")))
        self.write(os.path.join("outputs", "swapped.txt"), "inside\n")
        self.start()
        page, _ = self.page()
        # A listed file replaced by a link to outside after the page was rendered.
        swapped = self.anchor_of(page, "backend-dev/outputs/swapped.txt")
        os.remove(self.path(os.path.join("outputs", "swapped.txt")))
        os.symlink(outside, self.path(os.path.join("outputs", "swapped.txt")))
        self.assertEqual(self.get(f"/w/{WS}/file/{swapped}")[0], 404)
        link = self.anchor_of(page, "backend-dev/outputs/link.txt")
        for path in (f"/w/{WS}/file/{link}", f"/w/{WS}/file/..%2F..%2Fetc%2Fpasswd",
                     f"/w/{WS}/file/f-nothing-here", f"/w/{WS}/file/../../../etc/passwd",
                     "/etc/passwd", f"/w/{WS}/nope"):
            status, _, body = self.get(path)
            self.assertEqual(status, 404, path)
            self.assertNotIn(b"not for the dashboard", body)
        # The recorded requirements live outside the workspace, and are listed: they are sent.
        prd = self.anchor_of(page, self.t.project().relative_or_absolute(self.prd))
        self.assertEqual(self.get(f"/w/{WS}/file/{prd}")[0], 200)

    def test_read_only(self):
        self.completed()
        self.start()
        for method in ("POST", "PUT", "DELETE"):
            self.assertEqual(self.get(f"/w/{WS}/", method=method)[0], 501, method)
        status, _, body = self.get(f"/w/{WS}/", method="HEAD")
        self.assertEqual((status, body), (200, b""))

    def test_on_localhost_only_requests_to_a_local_name(self):
        self.completed()
        self.start()
        self.assertEqual(self.get(f"/w/{WS}/", {"Host": "evil.example:80"})[0], 403)
        for host in ("localhost", f"localhost:{self.server.server_address[1]}", "127.0.0.1"):
            self.assertEqual(self.get(f"/w/{WS}/", {"Host": host})[0], 200, host)

    def test_a_token_is_asked_once_then_kept_in_a_cookie(self):
        self.completed()
        self.start(token="open-sesame")
        self.assertEqual(self.get(f"/w/{WS}/")[0], 403)
        self.assertEqual(self.get(f"/w/{WS}/?token=wrong")[0], 403)
        status, headers, _ = self.get(f"/w/{WS}/?token=open-sesame")
        self.assertEqual((status, headers["location"]), (303, f"/w/{WS}/"))
        cookie = headers["set-cookie"].split(";", 1)[0]
        self.assertIn("HttpOnly", headers["set-cookie"])
        self.assertIn("SameSite=Strict", headers["set-cookie"])
        self.assertEqual(self.get(f"/w/{WS}/version", {"Cookie": cookie})[0], 200)
        self.assertEqual(self.get(f"/w/{WS}/version", {"Cookie": cookie + "x"})[0], 403)
        self.assertIn("?token=open-sesame", self.out.getvalue())

    def test_beyond_this_machine_a_token_is_required_by_default(self):
        self.completed()
        self.start(host="0.0.0.0")
        urls = [line.strip() for line in self.out.getvalue().splitlines() if "http://" in line]
        self.assertTrue(urls)
        self.assertTrue(all(re.search(r"\?token=[\w-]{20,}$", u) for u in urls), urls)
        self.assertEqual(self.get(f"/w/{WS}/")[0], 403)

    def test_no_token_on_request(self):
        self.completed()
        self.start(host="0.0.0.0", use_token=False)
        self.assertEqual(self.get(f"/w/{WS}/")[0], 200)
        self.assertNotIn("token=", self.out.getvalue())


class RecordTest(unittest.TestCase):
    def test_a_live_record_is_kept_and_a_stale_one_replaced(self):
        import socket
        import tempfile
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path, err = os.path.join(tmp.name, "devloops", "serve-x.json"), io.StringIO()
        live = {"pid": os.getpid(), "hostname": socket.gethostname(), "local_url": "http://a"}
        self.assertIsNone(serve._claim_record(path, live, err))
        mine = {"pid": os.getpid() + 1, "hostname": socket.gethostname()}
        self.assertEqual(serve._claim_record(path, mine, err), live)  # the first one keeps it
        with open(path, "w") as f:
            json.dump({"pid": 2 ** 22 + 12345, "hostname": socket.gethostname()}, f)  # gone
        self.assertIsNone(serve._claim_record(path, mine, err))
        with open(path) as f:
            self.assertEqual(json.load(f), mine)


class ServeCommandTest(StubLoopMixin, unittest.TestCase):
    def serving(self, *args):
        proc = self.start_cli("dashboard", "--serve", "--port", "0", "--json", *args)
        line = wait_for(proc.stdout.readline, what="the server's first line")
        return proc, json.loads(line)

    def test_serve_records_itself_and_the_hints_show_its_url(self):
        self.assertEqual(self.first_run(), 10, self.last_output)
        self.assertIn("files and conversations: devloops dashboard --serve --workspace us3",
                      self.last_output)
        proc, started = self.serving()
        self.assertEqual(started["host"], "127.0.0.1")
        self.assertIsNone(started["token"])
        url = f"http://127.0.0.1:{started['port']}/w/{WS}/"
        self.assertEqual(started["url"], url)
        record = serve.running(self.t.project(), self.t.env)
        self.assertEqual(record["pid"], proc.pid)
        # Every command now says where it is served.
        self.assertEqual(self.cli("dashboard"), 0, self.last_output)
        self.assertIn(f"files and conversations: {url} (dashboard server running)",
                      self.last_output)
        self.assertEqual(self.cli("approve", "--no-continue"), 0, self.last_output)
        self.assertIn(url, self.last_output)
        # A second server is not started.
        code, out, err = self.t.run_cli(["dashboard", "--serve", "--workspace", WS])
        self.assertEqual(code, 0, out + err)
        self.assertIn(f"already serving: {url} (pid {proc.pid})", out)
        # Stopped, it removes its record.
        proc.send_signal(signal.SIGTERM)
        self.assertEqual(proc.wait(timeout=30), 0)
        self.assertIsNone(serve.running(self.t.project(), self.t.env))
        self.assertFalse(os.path.exists(serve.record_path(self.t.project(), self.t.env)))

    def test_a_named_workspace_that_does_not_exist_is_an_error(self):
        self.assertEqual(self.first_run(), 10, self.last_output)  # only us3 exists
        default = self.t.project().default_workspace
        self.assertNotEqual(default, WS)
        code, out, err = self.t.run_cli(["dashboard", "--serve", "--workspace", default])
        self.assertEqual(code, 2, out + err)
        self.assertIn("does not exist", err)

    def test_flags_that_need_serve_or_export(self):
        self.assertEqual(self.first_run(), 10, self.last_output)
        for args in (["--port", "1"], ["--host", "0.0.0.0"], ["--open"], ["--no-token"],
                     ["--out", "x.html"], ["--serve", "--token", "abcdefgh", "--no-token"],
                     ["--serve", "--token", "short"], ["--serve", "--token", "has;semicolons"],
                     ["--serve", "--export"]):
            self.assertEqual(self.cli("dashboard", *args), 2, args)


if __name__ == "__main__":
    unittest.main()
