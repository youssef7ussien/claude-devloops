"""`devloops dashboard`'s server: the app shell, the data API, files, and what keeps it safe
(serve.py; specs/005-dashboard-redesign contracts/api.md; 002 FR-042b)."""
import http.client
import io
import json
import os
import re
import threading
import unittest
from unittest import mock

import helpers  # noqa: F401 - puts the package on sys.path
import samples
from devloops import appbundle, artifacts, dashboard, serve, workspace
from stub_loop import WS, StubLoopMixin, implemented

SECRET = "S3CR3T-served-value"


def find_file(trees, path):
    """The FileRef listed at `path` in the files' trees, or None."""
    for node in trees:
        if node.get("file") and node["file"]["path"] == path:
            return node["file"]
        found = find_file(node.get("children") or [], path)
        if found:
            return found
    return None


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

    def api(self, path, status=200):
        code, headers, body = self.get(f"/w/{WS}/api/{path}")
        self.assertEqual(code, status, body)
        self.assertTrue(headers["content-type"].startswith("application/json"), headers)
        return json.loads(body), headers

    def builder(self, name, fn):
        """Register `fn` as the builder of `api/<name>` for this test (the real builders are the
        dashboard's views)."""
        entry = (re.compile("^" + re.escape(name) + "$"), fn)
        serve.API.insert(0, entry)
        self.addCleanup(serve.API.remove, entry)

    def file_id(self, rel):
        ws = self.ws()
        index = artifacts.file_index(ws, dashboard.collect(ws))
        ref = find_file(index["trees"], rel)
        self.assertTrue(ref, rel)
        return ref["id"]

    def file(self, rel):
        return self.get(f"/w/{WS}/api/files/{self.file_id(rel)}")

    # --- the shell and its assets -------------------------------------------------------------------

    def test_the_shell_and_its_assets(self):
        self.completed()
        self.start()
        status, headers, _ = self.get("/")
        self.assertEqual((status, headers["location"]), (303, f"/w/{WS}/"))
        status, headers, body = self.get(f"/w/{WS}/")
        self.assertEqual(status, 200)
        page = body.decode()
        csp = headers["content-security-policy"]
        self.assertIn("script-src 'self'", csp)
        self.assertIn("style-src 'self'", csp)
        self.assertNotIn("unsafe-inline", csp)
        self.assertEqual(headers["cache-control"], "no-store")
        self.assertIn(' data-source="api"', page)
        self.assertIn(' data-poll="3"', page)
        self.assertIn(f' data-workspace="{WS}"', page)
        self.assertRegex(page, r' data-version="[0-9a-f]{16}"')
        self.assertNotIn("<script>", page)  # no inline script: the policy would block it
        v = appbundle.assets_version()
        for path, ctype, text in ((f"/assets/app.js?v={v}", "text/javascript", appbundle.script()),
                                  (f"/assets/app.css?v={v}", "text/css", appbundle.stylesheet())):
            self.assertIn(path, page)
            status, headers, body = self.get(path)
            self.assertEqual(status, 200, path)
            self.assertTrue(headers["content-type"].startswith(ctype), headers)
            self.assertIn("immutable", headers["cache-control"])
            self.assertEqual(body.decode(), text)
        self.assertEqual(self.get("/assets/other.js")[0], 404)

    # --- the API ----------------------------------------------------------------------------------

    def test_answers_are_redacted_json_with_the_version(self):
        self.completed()
        self.builder("probe", lambda ctx: {"text": f"the key is {SECRET}", "nested": [SECRET]})
        self.start()
        data, headers = self.api("probe")
        self.assertEqual(data, {"text": "the key is ***", "nested": ["***"]})
        version = json.loads(self.get(f"/w/{WS}/version")[2])["version"]
        self.assertEqual(headers["x-devloops-version"], version)
        self.assertEqual(headers["cache-control"], "no-store")

    def test_summary_and_loop_are_redacted(self):
        self.completed()
        plan = self.path(os.path.join("state", "plan.json"))
        with open(plan, encoding="utf-8") as f:
            doc = json.load(f)
        doc["milestones"][0]["title"] = f"Use {SECRET}"
        with open(plan, "w", encoding="utf-8") as f:
            json.dump(doc, f)
        workspace.open_workspace("other", self.t.project(), self.t.kit(), create=True)
        self.start()
        summary, headers = self.api("summary")
        self.assertEqual(summary["workspaces"], ["other", WS])
        self.assertEqual(summary["version"], headers["x-devloops-version"])
        self.assertEqual([c["loop"] for c in summary["loops"]], ["backend-dev"])
        loop, _ = self.api("loops/backend-dev")
        self.assertEqual(loop["milestones"][0]["title"], "Use ***")
        for body in (summary, loop):
            self.assertNotIn(SECRET, json.dumps(body))
            self.assertIn("Use ***", json.dumps(body))
        self.assertEqual(self.api("loops/frontend-dev", 404)[0],
                         {"error": "no loop 'frontend-dev' in this workspace"})
        for path in ("calls", "files", "events", "questions"):
            self.assertNotIn(SECRET, json.dumps(self.api(path)[0]), path)

    def test_a_builder_runs_once_per_version(self):
        self.completed()
        calls = []
        self.builder("probe", lambda ctx: calls.append(1) or {"n": len(calls)})
        self.start()
        self.assertEqual(self.api("probe")[0], {"n": 1})
        self.assertEqual(self.api("probe")[0], {"n": 1})
        self.assertEqual(len(calls), 1)
        self.write("progress.md", "changed\n")
        self.assertEqual(self.api("probe")[0], {"n": 2})
        self.assertEqual(len(calls), 2)

    def test_the_query_is_part_of_the_answer_for_a_builder_that_takes_it(self):
        self.completed()
        calls = []
        self.builder("probe", lambda ctx, query: calls.append(1) or dict(query))
        self.builder("plain", lambda ctx: calls.append(2) or {"same": True})
        self.start()
        self.assertEqual(self.api("probe?loop=a")[0], {"loop": "a"})
        self.assertEqual(self.api("probe?loop=b")[0], {"loop": "b"})
        self.assertEqual(self.api("probe?loop=a")[0], {"loop": "a"})
        self.assertEqual(calls, [1, 1])
        for query in ("", "?x=1", "?x=2"):  # a query a builder does not take changes nothing
            self.assertEqual(self.api("plain" + query)[0], {"same": True})
        self.assertEqual(calls, [1, 1, 2])

    def test_concurrent_first_requests_collect_once(self):
        self.completed()
        self.builder("probe", lambda ctx: {"loops": sorted(ctx.data["loops"]),
                                           "files": ctx.index["count"]})
        self.start()
        with mock.patch.object(dashboard, "collect", wraps=dashboard.collect) as collect:
            results = []
            threads = [threading.Thread(target=lambda: results.append(self.api("probe")[0]))
                       for _ in range(6)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(60)
        self.assertEqual(len(results), 6)
        self.assertEqual(collect.call_count, 1)

    def test_parameters_and_not_found(self):
        self.completed()

        def call(ctx, loop, seq):
            if seq != "1":
                raise dashboard.NotFound(f"no call {seq} of {loop}")
            return {"loop": loop, "seq": seq}
        entry = (re.compile(r"^probe/(?P<loop>[^/]+)/(?P<seq>[^/]+)$"), call)
        serve.API.insert(0, entry)
        self.addCleanup(serve.API.remove, entry)
        self.start()
        self.assertEqual(self.api("probe/backend-dev/1")[0], {"loop": "backend-dev", "seq": "1"})
        self.assertEqual(self.api("probe/backend-dev/9", 404)[0],
                         {"error": "no call 9 of backend-dev"})
        self.assertEqual(self.api("no/such/route", 404)[0], {"error": "not found"})
        self.assertEqual(self.api("files/f-not-a-file", 404)[0]["error"],
                         "not a file of this workspace")

    # --- files --------------------------------------------------------------------------------------

    def test_a_listed_file_is_sent_redacted(self):
        self.completed()
        self.write(os.path.join("outputs", "notes.md"), f"# Notes\nthe key is {SECRET}\n")
        self.start()
        status, headers, body = self.file("backend-dev/outputs/notes.md")
        self.assertEqual(status, 200)
        self.assertTrue(headers["content-type"].startswith("text/plain"))
        self.assertIn("sandbox", headers["content-security-policy"])
        self.assertEqual(body.decode(), "# Notes\nthe key is ***\n")
        # JSON is indented as the viewer shows it.
        _, _, body = self.file("backend-dev/state/plan.json")
        self.assertTrue(body.decode().startswith("{\n  "))

    def test_no_size_limit(self):
        self.completed()
        size = artifacts.MAX_EMBED_BYTES + 10
        self.write(os.path.join("outputs", "huge.log"), "y" * size)
        self.start()
        _, _, body = self.file("backend-dev/outputs/huge.log")
        self.assertEqual(len(body), size)

    def test_images_and_binary_files(self):
        from test_full_dashboard import PNG
        self.completed()
        evidence = self.path(os.path.join("state", "milestones", "M01", "trials", "1", "evidence"))
        with open(os.path.join(evidence, "shot.png"), "wb") as f:
            f.write(PNG)
        with open(os.path.join(evidence, "blob.bin"), "wb") as f:
            f.write(b"\x00\x01\x02")
        self.start()
        prefix = "backend-dev/state/milestones/M01/trials/1/evidence/"
        status, headers, body = self.file(prefix + "shot.png")
        self.assertEqual((status, headers["content-type"], body), (200, "image/png", PNG))
        _, headers, body = self.file(prefix + "blob.bin")
        self.assertEqual(headers["content-type"], "application/octet-stream")
        self.assertIn("attachment", headers["content-disposition"])
        self.assertEqual(body, b"\x00\x01\x02")

    def test_a_large_text_file_is_streamed_with_secrets_hidden(self):
        self.completed()
        lines = [f"line {i} {SECRET}\n" for i in range(2000)]
        self.write(os.path.join("outputs", "big.log"), "".join(lines))
        with mock.patch.object(serve, "STREAM_BYTES", 1024), \
                mock.patch.object(serve, "STREAM_BLOCK", 700):
            self.start()
            _, headers, body = self.file("backend-dev/outputs/big.log")
        self.assertNotIn("content-length", headers)
        self.assertEqual(body.decode(), "".join(line.replace(SECRET, "***") for line in lines))

    def test_a_file_written_after_the_last_answer_is_found(self):
        self.completed()
        self.start()
        self.write(os.path.join("outputs", "later.md"), "later\n")
        status, _, body = self.file("backend-dev/outputs/later.md")
        self.assertEqual((status, body), (200, b"later\n"))

    # --- search -------------------------------------------------------------------------------------

    def test_search_reads_files_and_conversations_redacted(self):
        self.completed()
        self.write(os.path.join("outputs", "notes.md"), "one\ntwo needle-word three\n")
        self.start()
        data, _ = self.api("search?q=NEEDLE-word")
        [hit] = data["results"]
        self.assertEqual(hit, {"id": self.file_id("backend-dev/outputs/notes.md"),
                               "kind": "file", "line": 2, "before": "two ",
                               "match": "needle-word", "after": " three"})
        data, _ = self.api("search?q=fake-internal")
        self.assertIn("call", {h["kind"] for h in data["results"]})
        data, _ = self.api(f"search?q={SECRET}")
        self.assertEqual(data["results"], [])

    def test_search_decodes_conversation_records(self):
        # The raw JSON line escapes quotes and non-ASCII text; the viewer shows them decoded.
        self.completed()
        record = {"type": "assistant", "message": {"content": [
            {"type": "text", "text": 'she said "quoted words" in Zürich'}]}}
        path = self.path(os.path.join("state", "conversations", "0001-plan.jsonl"))
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")  # ensure_ascii: Zürich
        self.start()
        for query in ("%22quoted%20words%22", "z%C3%BCrich"):
            data, _ = self.api(f"search?q={query}")
            hits = [h for h in data["results"] if h["kind"] == "call"]
            self.assertEqual([h["id"] for h in hits], ["call-backend-dev-1"], query)

    # --- following a run --------------------------------------------------------------------------

    def test_the_version_changes_with_the_workspace(self):
        self.completed()
        self.start()
        _, _, body = self.get(f"/w/{WS}/")
        version = json.loads(self.get(f"/w/{WS}/version")[2])["version"]
        self.assertIn(f' data-version="{version}"', body.decode())
        self.assertEqual(json.loads(self.get(f"/w/{WS}/version")[2])["version"], version)
        self.write("progress.md", "changed\n")
        self.assertNotEqual(json.loads(self.get(f"/w/{WS}/version")[2])["version"], version)

    def test_the_version_is_computed_once_a_second(self):
        self.completed()
        self.start()
        with mock.patch.object(serve, "VERSION_TTL", 60):
            first = json.loads(self.get(f"/w/{WS}/version")[2])["version"]
            self.write("progress.md", "changed\n")
            self.assertEqual(json.loads(self.get(f"/w/{WS}/version")[2])["version"], first)

    # --- workspaces ---------------------------------------------------------------------------------

    def test_one_server_serves_every_workspace(self):
        self.completed()
        workspace.open_workspace("other", self.t.project(), self.t.kit(), create=True)
        self.start()
        status, _, body = self.get("/w/other/")
        self.assertEqual(status, 200)
        self.assertIn(' data-workspace="other"', body.decode())
        self.assertEqual(self.get("/w/no-such/")[0], 404)
        self.assertEqual(self.get("/w/no-such/api/summary")[0], 404)
        self.assertEqual(self.get("/w/other")[0], 303)

    # --- safety -------------------------------------------------------------------------------------

    def test_only_listed_files_are_sent(self):
        self.completed()
        outside = os.path.join(self.t.base, "outside.txt")
        with open(outside, "w") as f:
            f.write("not for the dashboard\n")
        os.symlink(outside, self.path(os.path.join("outputs", "link.txt")))
        self.write(os.path.join("outputs", "swapped.txt"), "inside\n")
        self.start()
        # A listed file replaced by a link to outside after it was listed.
        swapped = self.file_id("backend-dev/outputs/swapped.txt")
        os.remove(self.path(os.path.join("outputs", "swapped.txt")))
        os.symlink(outside, self.path(os.path.join("outputs", "swapped.txt")))
        self.assertEqual(self.get(f"/w/{WS}/api/files/{swapped}")[0], 404)
        link = self.file_id("backend-dev/outputs/link.txt")
        for path in (f"/w/{WS}/api/files/{link}", f"/w/{WS}/api/files/..%2F..%2Fetc%2Fpasswd",
                     f"/w/{WS}/api/files/f-nothing-here", f"/w/{WS}/api/files/../../../etc/passwd",
                     "/etc/passwd", f"/w/{WS}/nope", f"/w/{WS}/file/{link}"):
            status, _, body = self.get(path)
            self.assertEqual(status, 404, path)
            self.assertNotIn(b"not for the dashboard", body)
        # The recorded requirements live outside the workspace, and are listed: they are sent.
        prd = self.file_id(self.t.project().relative_or_absolute(self.prd))
        self.assertEqual(self.get(f"/w/{WS}/api/files/{prd}")[0], 200)

    def test_read_only(self):
        self.completed()
        self.start()
        for method in ("POST", "PUT", "DELETE"):
            for path in (f"/w/{WS}/", f"/w/{WS}/api/summary"):
                self.assertEqual(self.get(path, method=method)[0], 501, (method, path))
        status, _, body = self.get(f"/w/{WS}/", method="HEAD")
        self.assertEqual((status, body), (200, b""))

    def test_on_localhost_only_requests_to_a_local_name(self):
        self.completed()
        self.start()
        self.assertEqual(self.get(f"/w/{WS}/", {"Host": "evil.example:80"})[0], 403)
        self.assertEqual(self.get(f"/w/{WS}/version", {"Host": "evil.example:80"})[0], 403)
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
        self.assertEqual(self.get(f"/w/{WS}/api/files/f-x")[0], 403)
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


if __name__ == "__main__":
    unittest.main()
