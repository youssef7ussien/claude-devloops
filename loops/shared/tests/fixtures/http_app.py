#!/usr/bin/env python3
"""Fixture API server for the curl-validator tests (T028/T029/T030).

A stdlib `http.server`, not an application of the loops: it stands in for whatever a real
`backend-dev` implementation would run, so `loops/shared/devloops/validators/curl.py` has a real
process to issue curl requests against. Port is `argv[1]`.

Resource: an in-memory `items` map.
  GET  /items        -> 200, the items in creation order
  POST /items        -> 201, the given JSON body merged with a new string `id`
  GET  /items/{id}   -> 200 the item, or 404 `{"error": "not found"}`
  GET  /health        -> 200 `{"status": "ok", "info": {"service": "items-fixture"}}`
                        (the nested `info` field exists to exercise dotted-path `json_equals`)
  HEAD /health        -> 200, headers only
  GET  /slow          -> sleeps 5s, then 200 (exercises the per-check timeout)
  GET  /binary        -> 200, bytes that are not UTF-8 (an image, say)

Like a JSON-only framework, `POST /items` answers 415 unless `Content-Type` is `application/json`.
"""
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ITEMS = {}
NEXT_ID = [1]


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, status, body):
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_HEAD(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(404)
        self.end_headers()

    def do_GET(self):
        if self.path == "/slow":
            time.sleep(5)
            return self._send_json(200, {"slow": True})
        if self.path == "/binary":
            payload = b"\x89PNG\xff\xfe\x00"
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path == "/health":
            return self._send_json(200, {"status": "ok",
                                         "info": {"service": "items-fixture"}})
        if self.path == "/items":
            return self._send_json(200, list(ITEMS.values()))
        if self.path.startswith("/items/"):
            item = ITEMS.get(self.path[len("/items/"):])
            if item is None:
                return self._send_json(404, {"error": "not found"})
            return self._send_json(200, item)
        return self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/items":
            return self._send_json(404, {"error": "not found"})
        if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
            return self._send_json(415, {"error": "expected application/json"})
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw or b"{}")
        except ValueError:
            return self._send_json(400, {"error": "invalid json"})
        if not isinstance(data, dict):
            return self._send_json(400, {"error": "invalid json"})
        item_id = str(NEXT_ID[0])
        NEXT_ID[0] += 1
        item = dict(data, id=item_id)
        ITEMS[item_id] = item
        return self._send_json(201, item)

    def log_message(self, format, *args):
        pass  # keep test output quiet


def main(argv):
    port = int(argv[1]) if len(argv) > 1 else 8765
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main(sys.argv)
