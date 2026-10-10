"""`devloops dashboard`: the dashboard app, served live from the workspaces with its data
(specs/005-dashboard-redesign contracts/api.md; 002 FR-042a).

A local HTTP server (the standard library's). `/w/<name>/` is a small page (assets/app/index.html)
that loads one script and one stylesheet; the app then asks `/w/<name>/api/...` for the data of
the view it shows, as JSON built by dashboard.py, and each file's content when it is opened. Every
answer is kept until the workspace changes: the page asks for the workspace's `version` every few
seconds and, when it changed, loads the open view's data again (assets/app/api.js).

Safe by default:
- it listens on 127.0.0.1 unless `--host` says otherwise; on a loopback address it answers only
  requests addressed to a loopback name, so a web page cannot reach it through DNS rebinding;
- on any other address it requires a token (in the printed URL, then kept in a cookie), unless
  `--no-token`;
- it is read-only: GET and HEAD only, and it never writes to the project;
- it sends only the files the workspace's listing holds (artifacts.file_index), named by their id,
  never a path from the request, and a listed file must lie inside the workspace (or be a
  recorded input);
- every text it sends goes through the workspace's redactor;
- the page runs only the server's own script and style (its Content-Security-Policy).

One server covers the project's workspaces, and the page switches between them. While it runs,
`serve-<project>.json` in the user's runtime folder records its URL and pid, so other commands
print the URL instead of the command (`running`).
"""
import hashlib
import hmac
import inspect
import ipaddress
import json
import os
import re
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import appbundle, artifacts, claude, dashboard, state, workspace
from .state import DevloopsError

DEFAULT_PORT = 8765
PORT_TRIES = 20          # without --port, the next free port up to this many after the default
POLL_SECONDS = 3         # how often a page asks whether its workspace changed
SEARCH_LIMIT = 40        # results of one search
SEARCH_MIN = 3           # a shorter query finds nothing (the palette matches names until then)
SEARCH_MAX_BYTES = 20 * 1024 * 1024  # larger files are not searched (they still open)
SEARCH_KEEP_BYTES = 256 * 1024 * 1024  # UTF-8 bytes of text the search keeps; more are read per search
SEARCH_WORKSPACES = 2    # workspaces whose search texts are kept (the most recently searched)
STREAM_BYTES = 16 * 1024 * 1024      # larger text files are streamed, not read whole
STREAM_BLOCK = 1024 * 1024
VERSION_TTL = 1.0                    # seconds a computed version serves every page
ANCHOR = re.compile(r"^f-[a-z0-9-]+$")
PAGE_CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
FILE_CSP = "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox"
ASSETS = {"app.js": ("text/javascript; charset=utf-8", appbundle.script),
          "app.css": ("text/css; charset=utf-8", appbundle.stylesheet)}

# The data API: `(pattern of the path after /w/<ws>/api/, builder)`. A builder is the name of a
# function of dashboard.py (or a function), called as `builder(ctx, **named groups)` with the
# workspace version's `dashboard.Context`; it returns plain data, or raises `dashboard.NotFound`.
# `files/<id>` (a file's content) and `search` are answered by the server itself. An answer is
# kept for the version, unless its builder says `cached = False`.
API = [(re.compile(pattern), builder) for pattern, builder in (
    (r"^summary$", "summary"),
    (r"^now$", "now"),
    (r"^loops/(?P<loop>[^/]+)$", "loop"),
    (r"^loops/(?P<loop>[^/]+)/milestones/(?P<milestone>[^/]+)/trials/(?P<key>[^/]+)$", "trial"),
    (r"^calls$", "calls"),
    (r"^calls/(?P<loop>[^/]+)/(?P<seq>[^/]+)$", "call"),
    (r"^files$", "files"),
    (r"^events$", "events"),
    (r"^questions$", "questions"),
    (r"^index$", "index"),
)]


# --- the record of a running server -----------------------------------------------------------------

def record_path(project, env=None):
    """`<runtime folder>/devloops/serve-<project hash>.json`: outside the project, so a server
    started during a run never shows in its git status (the boundary audit)."""
    env = os.environ if env is None else env
    base = (env.get("XDG_RUNTIME_DIR") or env.get("XDG_CACHE_HOME")
            or os.path.join(env.get("HOME") or os.path.expanduser("~"), ".cache"))
    digest = hashlib.sha1(os.path.realpath(project.root).encode("utf-8")).hexdigest()[:12]
    return os.path.join(base, "devloops", f"serve-{digest}.json")


def _alive(pid):
    try:
        os.kill(int(pid), 0)
    except PermissionError:
        return True
    except (OSError, TypeError, ValueError):
        return False
    return True


def running(project, env=None):
    """The record of the server running for `project` on this host, or None."""
    rec = state.read_json(record_path(project, env))
    if not isinstance(rec, dict) or rec.get("hostname") != socket.gethostname() \
            or not _alive(rec.get("pid")):
        return None
    return rec


def url_for(rec, name):
    """The local URL of workspace `name` on a running server (without its token)."""
    return f"{rec['local_url']}/w/{urllib.parse.quote(name)}/"


def _claim_record(path, rec, err):
    """Create the record, unless a live server holds it: return that server's record, else None.
    Created exclusively, so of two servers started together only one records itself."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        for _ in range(3):
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                held = state.read_json(path)
                if isinstance(held, dict) and held.get("hostname") == socket.gethostname() \
                        and _alive(held.get("pid")):
                    return held
                try:  # a record left by a server that is gone
                    os.remove(path)
                except FileNotFoundError:
                    pass
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(rec, f, indent=2)
            return None
    except OSError as e:
        print(f"devloops: warning: could not record the server ({e}); other commands will not "
              f"show its URL", file=err)
    return None


def _remove_record(path):
    rec = state.read_json(path)
    if isinstance(rec, dict) and rec.get("pid") == os.getpid():
        try:
            os.remove(path)
        except OSError:
            pass


# --- what is served ---------------------------------------------------------------------------------

class Site:
    """The project's workspaces, and what the server knows of each version of one: its answers."""

    def __init__(self, project, kit, env=None, extra=None):
        self.project, self.kit = project, kit
        self.env = os.environ if env is None else env
        self.extra = dict(extra or {})  # workspaces outside the workspaces folder: name -> path
        self._lock = threading.Lock()
        # workspace name -> {version, ctx (dashboard.Context), answers: {path: (status, body)}}
        self._cache = {}
        self._versions = {}  # workspace name -> (when, version): one walk serves every tab
        self._search = {}    # workspace name -> SearchIndex

    def workspaces(self):
        """`{name: path}` of every workspace, sorted by name."""
        found = {}
        top = self.project.workspaces_dir
        try:
            names = os.listdir(top)
        except OSError:
            names = []
        for name in names:
            path = os.path.join(top, name)
            if workspace.NAME_RE.match(name) and os.path.isfile(os.path.join(path, "workspace.json")):
                found[name] = path
        found.update(self.extra)
        return dict(sorted(found.items()))

    def open(self, name):
        path = self.workspaces().get(name)
        if path is None:
            return None
        try:
            return workspace.open_workspace(path if name in self.extra else name, self.project,
                                            self.kit, create=False)
        except DevloopsError:
            return None

    def version(self, ws):
        """A digest of everything the dashboard shows: each file's size and time, the full
        dashboards written, and the workspaces to switch to. Computed at most once a second per
        workspace, however many pages ask."""
        now = time.monotonic()
        with self._lock:
            when, version = self._versions.get(ws.name, (None, None))
        if when is not None and now - when < VERSION_TTL:
            return version
        h = hashlib.sha1()
        for path in artifacts._walk(ws.path):
            rel = artifacts.relative(path, ws.path)
            if rel == dashboard.FILENAME or rel.split(os.sep)[0] == artifacts.EXPORTS:
                continue
            try:
                st = os.stat(path)
            except OSError:
                continue
            h.update(f"{rel}\0{st.st_size}\0{st.st_mtime_ns}\n".encode("utf-8", "replace"))
        for item in dashboard.list_full_dashboards(ws):
            h.update(item["name"].encode("utf-8"))
        h.update("\0".join(self.workspaces()).encode("utf-8"))
        version = h.hexdigest()[:16]
        with self._lock:
            # Of two walks at once, the one that started last saw the newer workspace: an older
            # one finishing later must not bring its version back.
            when, latest = self._versions.get(ws.name, (None, None))
            if when is None or now >= when:
                self._versions[ws.name] = (now, version)
            else:
                version = latest
        return version

    def current(self, ws):
        """`(version, entry)`: the workspace's cache entry for its current version, emptied when
        the version changed (FR-007)."""
        self.version(ws)
        with self._lock:
            version = self._versions[ws.name][1]  # the newest, whatever this thread computed
            entry = self._cache.get(ws.name)
            if entry is None or entry["version"] != version:
                entry = {"version": version, "answers": {},
                         "ctx": dashboard.Context(ws, self.env, list(self.workspaces()),
                                                version)}
                self._cache[ws.name] = entry
        return version, entry

    def answer(self, ws, path, query=""):
        """`(status, JSON text, version)` of API path `path` with query string `query`: built by
        its builder once per version, redacted. A builder that takes `query` gets the query's
        values (`{name: value}`); for one that does not, the query does not change the answer.
        An unknown path, or a builder's `NotFound`, is a 404."""
        version, entry = self.current(ws)
        found = route_api(path, query)
        if found is None:
            return 404, json.dumps({"error": "not found"}), version
        build, args, key = found
        cached = getattr(build, "cached", True)  # False: worked out on every request (api/now)
        with self._lock:
            hit = entry["answers"].get(key) if cached else None
        if hit:
            return hit + (version,)
        status, data = build_answer(entry["ctx"], build, args)
        body = json.dumps(data, ensure_ascii=False)
        if cached:
            with self._lock:
                entry["answers"][key] = (status, body)
        return status, body, version

    def redactor(self, ws):
        return self.current(ws)[1]["ctx"].redactor

    def file(self, ws, file_id):
        """The real path of a file the workspace's listing holds, or None. A file written since
        the last listing is found once the version shows the change. The real path is what is
        opened, so a link swapped in after this check is not followed."""
        if not ANCHOR.match(file_id):
            return None
        return _sendable(self.current(ws)[1]["ctx"].index, os.path.realpath(ws.path), file_id)

    def search(self, ws, query):
        """Where `query` appears in the workspace's files, conversations, and events: SearchHits
        (`search_corpus`). The texts are kept between searches (SearchIndex) for the
        SEARCH_WORKSPACES workspaces searched last, sharing SEARCH_KEEP_BYTES."""
        ctx = self.current(ws)[1]["ctx"]  # one listing for the whole search
        with self._lock:
            index = self._search.pop(ws.name, None) or SearchIndex(
                SEARCH_KEEP_BYTES // SEARCH_WORKSPACES)
            self._search[ws.name] = index  # the most recently searched last
            while len(self._search) > SEARCH_WORKSPACES:
                self._search.pop(next(iter(self._search)))
        hits = []
        for hit in search_corpus(index.corpus(ctx), query):
            # the texts are redacted already; a secret spanning the snippet's parts is caught
            # here too, where the parts are seen together
            if ctx.redactor.redact(hit["before"] + hit["match"] + hit["after"])[1]:
                continue
            hits.append(ctx.redactor.redact_obj(hit)[0])
        return hits


def route_api(path, query=""):
    """`(builder function, its arguments, cache key)` of API path `path` with query string
    `query`, or None for an unknown path. A builder that takes `query` gets the query's values
    (`{name: value}`); for one that does not, the query does not change the answer."""
    for pattern, builder in API:
        match = pattern.match(path)
        if match:
            break
    else:
        return None
    build = getattr(dashboard, builder) if isinstance(builder, str) else builder
    args = match.groupdict()
    params = {}
    if _takes_query(build):
        params = {k: v[-1] for k, v in sorted(urllib.parse.parse_qs(query).items())}
        args["query"] = params
    return build, args, (path, tuple(params.items()))


def build_answer(ctx, build, args):
    """`(status, data)`: the builder's answer, redacted with the workspace's redactor; a
    `NotFound` is a 404. The server and the export (dashboard_export.py) answer alike."""
    try:
        status, data = 200, build(ctx, **args)
    except dashboard.NotFound as e:
        status, data = 404, {"error": str(e)}
    return status, ctx.redactor.redact_obj(data)[0]


def _sendable(index, root, file_id):
    """The real path of a listed file that may be sent: inside the workspace `root`, or a
    recorded input; else None."""
    path = index["by_id"].get(file_id)
    if path is None:
        return None
    real = os.path.realpath(path)
    inside = real == root or real.startswith(root.rstrip(os.sep) + os.sep)
    return real if inside or file_id in index["inputs"] else None


def _takes_query(fn):
    try:
        return "query" in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False


# --- search (research R-10) -------------------------------------------------------------------------

def fold_case(text):
    """`text` in lower case, character for character: a character whose lower case is longer
    (`İ`) is kept, so an offset in the result is the same offset in `text`. assets/app/palette.js
    `fold` is the same."""
    low = text.lower()
    if len(low) == len(text):
        return low
    return "".join(c if len(c.lower()) != 1 else c.lower() for c in text)


def _hit(text, needle):
    """The first match of `needle` (folded, `fold_case`) in `text`: its line number and the text
    around it. assets/app/palette.js `hitOf` is the same."""
    at = fold_case(text).find(needle)
    if at < 0:
        return None
    start = text.rfind("\n", 0, at) + 1
    end = text.find("\n", at)
    end = len(text) if end < 0 else end
    line = text[start:end]
    col = at - start
    return {"line": text.count("\n", 0, at) + 1, "before": line[max(0, col - 40):col],
            "match": line[col:col + len(needle)], "after": line[col + len(needle):col + len(needle) + 80]}


def search_corpus(items, query, limit=SEARCH_LIMIT):
    """SearchHits of `query` in `items` (`{kind, id, label, route, text}`, in search order: files,
    calls, events), case-insensitive: the first match in each item, at most `limit`, each with the
    route that opens it at the match: a file at its line, a call at its record, an event at its
    place in its loop's events (each call and events text has one line per record or event).
    Nothing below SEARCH_MIN characters. The export's search (assets/app/palette.js
    `DL.search.content`) returns the same hits for the same corpus."""
    needle = fold_case(query)
    if len(needle) < SEARCH_MIN:
        return []
    found = []
    for item in items:
        if len(found) >= limit:
            break
        hit = _hit(item["text"], needle) if item.get("text") else None
        if hit is None:
            continue
        at = {"file": ("line", hit["line"])}.get(item["kind"], ("at", hit["line"] - 1))
        joiner = "&" if "?" in item["route"] else "?"
        found.append(dict({"kind": item["kind"], "id": item["id"], "label": item["label"],
                           "route": f"{item['route']}{joiner}{at[0]}={at[1]}"}, **hit))
    return found


def _file_text(path, st, redactor):
    """A listed file as the viewer shows it, or None: an image, a binary file, or one over
    SEARCH_MAX_BYTES is not searched. A text file over STREAM_BYTES is sent as it is (JSON not
    indented), so it is searched as it is too, keeping its line numbers."""
    if st.st_size > SEARCH_MAX_BYTES:
        return None
    kind, _, _ = artifacts.sniff(path, st.st_size, st.st_mtime_ns)
    if kind in ("image", "binary"):
        return None
    with open(path, "rb") as f:
        text = f.read().decode("utf-8", errors="replace")
    if st.st_size > STREAM_BYTES:
        return redactor.redact(text)[0]
    return artifacts.viewer_text(kind, text, redactor)


def _conversation_text(path, st, redactor):
    """A transcript as one line per record of `artifacts.parse_conversation` (the conversation
    view's records), each what the view shows of it (`artifacts.record_text`)."""
    with open(path, "rb") as f:
        text = f.read().decode("utf-8", errors="replace")
    return "\n".join(artifacts.record_text(r)
                     for r in artifacts.parse_conversation(text, redactor)["records"])


def _events_text(path, st, redactor):
    """events.jsonl as one line per event (as state.read_jsonl reads it, so a line is the event's
    `n` in api/events): the event's values, redacted."""
    with open(path, "rb") as f:
        text = f.read().decode("utf-8", errors="replace")
    lines = []
    for line in text.split("\n"):
        if line.strip():
            try:
                value = redactor.redact_obj(json.loads(line))[0]
            except ValueError:
                value = redactor.redact(line)[0]
            lines.append(" ".join(str(v) for v in (value.values() if isinstance(value, dict)
                                                   else [value])).replace("\n", " "))
    return "\n".join(lines)


class SearchIndex:
    """One workspace's searchable texts, redacted, kept between searches (research R-10):
    `{(kind, path): ((size, mtime_ns), text, bytes)}`. Each search checks an item's size and time
    and reads it again only when they changed; at most `keep` UTF-8 bytes of text are kept, and
    items beyond that are read on each search. A change of the secrets to hide empties it, and a
    text redacted with other secrets than the index's is never kept."""

    def __init__(self, keep=SEARCH_KEEP_BYTES):
        self.keep = keep
        self._lock = threading.Lock()
        self._texts = {}
        self._size = 0
        self._secrets = None
        self._sources = (None, None)  # (the workspace version they were listed for, sources)

    def _text(self, key, path, read, redactor, secrets):
        try:
            st = os.stat(path)
        except OSError:
            return None
        stamp = (st.st_size, st.st_mtime_ns)
        with self._lock:
            hit = self._texts.get(key)
        if hit and hit[0] == stamp:
            return hit[1]
        try:
            text = read(path, st, redactor)
        except OSError:
            text = None
        size = len(text.encode("utf-8")) if text is not None else 0
        with self._lock:
            if secrets != self._secrets:
                return text  # a search begun before the secrets changed: used, never kept
            old = self._texts.pop(key, None)
            if old:
                self._size -= old[2]
            if text is not None and self._size + size <= self.keep:
                self._texts[key] = (stamp, text, size)
                self._size += size
        return text

    def sources(self, ctx):
        """`[(item without its text, key, path, reader)]` of the workspace version `ctx`, in
        search order: the listed files, each loop's calls, then each loop's events. Listed once
        per version."""
        with self._lock:
            version, sources = self._sources
        if ctx.version is not None and version == ctx.version:
            return sources
        sources = self._list(ctx)
        with self._lock:
            self._sources = (ctx.version, sources)
        return sources
    def _list(self, ctx):
        out, refs = [], {ref["id"]: ref["path"] for ref in ctx.refs.values() if ref.get("id")}
        root = os.path.realpath(ctx.ws.path)
        folders = {}  # each folder's real path, found once per search

        def real(path):
            folder, name = os.path.split(path)
            if folder not in folders:
                folders[folder] = os.path.realpath(folder)
            joined = os.path.join(folders[folder], name)
            return os.path.realpath(joined) if os.path.islink(joined) else joined
        for file_id, listed in ctx.index["by_id"].items():
            path = real(listed)  # as _sendable, without a realpath per file
            inside = path == root or path.startswith(root.rstrip(os.sep) + os.sep)
            if inside or file_id in ctx.index["inputs"]:
                out.append(({"kind": "file", "id": file_id, "label": refs.get(file_id, file_id),
                             "route": dashboard.route("file", id=file_id)},
                            ("file", path), path, _file_text))
        for loop, d in ctx.data["loops"].items():
            for r in sorted(d["invocations"], key=lambda r: r.get("seq") or 0):
                if r.get("conversation_path"):
                    path = os.path.join(ctx.ws.loop_dir(loop), r["conversation_path"])
                elif r.get("conversation") == "unavailable":
                    continue
                else:
                    path = claude.find_transcript(r.get("session_id"), d["target_dir"], ctx.env)
                    if path is None:
                        continue
                out.append(({"kind": "call", "id": artifacts.call_id(loop, r.get("seq")),
                             "label": f"{loop} · call #{r.get('seq')} {r.get('step')}",
                             "route": dashboard.route("call", loop=loop, seq=r.get("seq"))},
                            ("call", path), path, _conversation_text))
        for loop in ctx.data["loops"]:
            path = os.path.join(ctx.ws.loop_dir(loop), "state", "events.jsonl")
            out.append(({"kind": "event", "id": f"events-{loop}", "label": f"{loop} · events",
                         "route": dashboard.route("events", {"loop": loop})},
                        ("event", path), path, _events_text))
        return out

    def corpus(self, ctx):
        """The searchable items `{kind, id, label, route, text}` of the workspace version `ctx`,
        read as they are asked for (a search that has its results stops reading)."""
        sources, redactor = self.sources(ctx), ctx.redactor
        with self._lock:
            secrets = tuple(redactor.values)
            if secrets != self._secrets:
                self._texts, self._size, self._secrets = {}, 0, secrets
            keys = {key for _, key, _, _ in sources}
            for key in [k for k in self._texts if k not in keys]:
                self._size -= self._texts.pop(key)[2]
        for item, key, path, read in sources:
            text = self._text(key, path, read, redactor, secrets)
            if text is not None:
                yield dict(item, text=text)


# --- HTTP -------------------------------------------------------------------------------------------

def _is_loopback(host):
    if host in ("localhost", ""):
        return host == "localhost"
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


class Handler(BaseHTTPRequestHandler):
    server_version = "devloops"
    sys_version = ""

    def log_message(self, format, *args):  # noqa: A002 - the base class's name
        pass  # quiet: the terminal shows the URL, not every request

    def do_HEAD(self):  # noqa: N802 - the base class's naming
        self._handle(head=True)

    def do_GET(self):  # noqa: N802
        self._handle()

    # --- responses ---

    def _send(self, code, body, ctype="text/plain; charset=utf-8", headers=None, head=False,
              cache="no-store"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy",
                         PAGE_CSP if ctype.startswith("text/html") else FILE_CSP)
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def _redirect(self, location, headers=None, head=False):
        self._send(303, "", headers=dict(headers or {}, Location=location), head=head)

    def _json(self, obj, head=False, code=200, version=None):
        body = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
        headers = {"X-Devloops-Version": version} if version else None
        self._send(code, body, "application/json; charset=utf-8", headers=headers, head=head)

    # --- checks ---

    def _host_allowed(self):
        """On a loopback address, only requests addressed to a loopback name (DNS rebinding)."""
        if not self.server.loopback:
            return True
        host = (self.headers.get("Host") or "").strip()
        if host.startswith("["):
            host = host[1:host.find("]")] if "]" in host else host
        else:
            host = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
        return _is_loopback(host)

    def _token_ok(self, url, head):
        """True when the request may go on; otherwise the response is sent."""
        token = self.server.token
        if not token:
            return True
        query = urllib.parse.parse_qs(url.query)
        given = (query.pop("token", None) or [None])[0]
        if given is not None:
            if not hmac.compare_digest(given.encode(), token.encode()):
                self._send(403, "devloops: wrong token\n", head=head)
                return False
            rest = urllib.parse.urlencode(query, doseq=True)
            cookie = (f"{self.server.cookie}={token}; Path=/; HttpOnly; SameSite=Strict; "
                      f"Max-Age=2592000")
            self._redirect(url.path + (f"?{rest}" if rest else ""), {"Set-Cookie": cookie}, head)
            return False
        jar = cookies.SimpleCookie()
        try:
            jar.load(self.headers.get("Cookie") or "")
        except cookies.CookieError:
            pass
        morsel = jar.get(self.server.cookie)
        if morsel and hmac.compare_digest(morsel.value.encode(), token.encode()):
            return True
        self._send(403, "devloops: open the URL with the token that `devloops dashboard` "
                        "printed\n", head=head)
        return False

    # --- routes ---

    def _handle(self, head=False):
        try:
            url = urllib.parse.urlsplit(self.path)
            if not self._host_allowed():
                self._send(403, "devloops: this server answers only requests to localhost\n",
                           head=head)
                return
            if not self._token_ok(url, head):
                return
            self._route(url, head)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:  # noqa: BLE001 - one failed request never stops the server
            print(f"devloops: dashboard server: {type(e).__name__}: {e}", file=sys.stderr)
            try:
                self._send(500, f"devloops: {type(e).__name__}: {e}\n", head=head)
            except OSError:
                pass

    def _route(self, url, head):
        site = self.server.site
        parts = [urllib.parse.unquote(p) for p in url.path.split("/")[1:]]
        if url.path == "/":
            self._redirect(f"/w/{urllib.parse.quote(self.server.default)}/", head=head)
            return
        if url.path == "/favicon.ico":
            self._send(204, "", head=head)
            return
        if len(parts) == 2 and parts[0] == "assets":
            self._asset(parts[1], url, head)
            return
        if len(parts) < 2 or parts[0] != "w":
            self._send(404, "devloops: not found\n", head=head)
            return
        ws = site.open(parts[1])
        if ws is None:
            self._send(404, f"devloops: no workspace {parts[1]!r}\n", head=head)
            return
        rest = parts[2:]
        if not rest:
            self._redirect(f"/w/{urllib.parse.quote(ws.name)}/", head=head)
        elif rest == [""]:
            attrs = {"source": "api", "poll": POLL_SECONDS, "workspace": ws.name,
                     "version": site.version(ws)}
            self._send(200, appbundle.shell(f"devloops · {ws.name}", attrs),
                       "text/html; charset=utf-8", head=head)
        elif rest == ["version"]:
            self._json({"version": site.version(ws)}, head)
        elif rest[0] == "api" and len(rest) > 1:
            self._api(ws, rest[1:], url, head)
        else:
            self._send(404, "devloops: not found\n", head=head)

    def _asset(self, name, url, head):
        """The app's script or stylesheet. Its URL carries the assets' version, so a browser
        keeps it until devloops changes."""
        if name not in ASSETS:
            self._send(404, "devloops: not found\n", head=head)
            return
        ctype, read = ASSETS[name]
        given = (urllib.parse.parse_qs(url.query).get("v") or [None])[0]
        cache = ("max-age=31536000, immutable" if given == appbundle.assets_version()
                 else "no-store")
        self._send(200, read(), ctype, head=head, cache=cache)

    def _api(self, ws, rest, url, head):
        site = self.server.site
        if len(rest) == 2 and rest[0] == "files":
            self._file(ws, rest[1], head)
        elif rest == ["search"]:
            query = (urllib.parse.parse_qs(url.query).get("q") or [""])[0]
            self._json({"results": site.search(ws, query)}, head, version=site.version(ws))
        else:
            code, body, version = site.answer(ws, "/".join(rest), url.query)
            self._json(body, head, code, version)

    def _file(self, ws, file_id, head):
        site = self.server.site
        path = site.file(ws, file_id)
        if path is None:
            self._json({"error": "not a file of this workspace"}, head, 404)
            return
        try:
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except OSError:
            self._json({"error": "missing"}, head, 404)
            return
        with os.fdopen(fd, "rb") as f:
            st = os.fstat(fd)
            kind, _, _ = artifacts.sniff(path, st.st_size, st.st_mtime_ns)
            if kind not in ("image", "binary") and st.st_size > STREAM_BYTES:
                self._stream_text(f, site.redactor(ws), head)
                return
            data = f.read()
        name = os.path.basename(path)
        if kind == "image":
            ctype = artifacts.IMAGE_TYPES[os.path.splitext(path)[1].lower()]
            self._send(200, data, ctype, head=head)
        elif kind == "binary":
            self._send(200, data, "application/octet-stream", head=head, headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(name)}"})
        else:
            text = artifacts.viewer_text(kind, data.decode("utf-8", errors="replace"),
                                         site.redactor(ws))
            self._send(200, text, head=head)

    def _stream_text(self, f, redactor, head):
        """A large text file, sent as it is read, a block of whole lines at a time with secrets
        hidden, so memory stays bounded (JSON is not indented)."""
        self.send_response(200)
        for name, value in (("Content-Type", "text/plain; charset=utf-8"),
                            ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"),
                            ("Referrer-Policy", "no-referrer"), ("X-Frame-Options", "DENY"),
                            ("Content-Security-Policy", FILE_CSP), ("Connection", "close")):
            self.send_header(name, value)
        self.end_headers()
        if head:
            return
        while True:
            block = f.read(STREAM_BLOCK)
            if not block:
                break
            block += f.readline(STREAM_BLOCK)  # end on a line, so a secret is not cut in two
            text = block.decode("utf-8", errors="replace")
            self.wfile.write(redactor.redact(text)[0].encode("utf-8"))


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, host, port, site, default, token):
        self.address_family = socket.AF_INET6 if ":" in host else socket.AF_INET
        self.site, self.default, self.token = site, default, token
        self.loopback = _is_loopback(host)
        super().__init__((host, port), Handler)
        self.cookie = f"devloops-{self.server_address[1]}"

    def server_bind(self):
        if self.address_family == socket.AF_INET6:  # `::` also takes IPv4 where it can
            try:
                self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
            except (AttributeError, OSError):
                pass
        super().server_bind()


def _bind(host, port, site, default, token):
    """A server on `port`; without one (None), the first free port from DEFAULT_PORT."""
    ports = [port] if port is not None else range(DEFAULT_PORT, DEFAULT_PORT + PORT_TRIES)
    error = None
    for candidate in ports:
        try:
            return Server(host, candidate, site, default, token)
        except OSError as e:
            error = e
    raise state.UsageError(f"cannot listen on {host} port "
                           f"{port if port is not None else f'{DEFAULT_PORT}-{DEFAULT_PORT + PORT_TRIES - 1}'}"
                           f": {error.strerror or error}")


def _addresses(host):
    """The addresses to print for `host`: this machine's for a wildcard, else `host` itself."""
    if host not in ("0.0.0.0", "::"):
        return [host]
    found = []
    try:  # the address of the default route: a UDP "connect" sends nothing
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))
            found.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        found += socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        pass
    found = [a for a in dict.fromkeys(found) if not a.startswith("127.")]
    return found + ["127.0.0.1"]


def _base(host, port):
    return f"http://{f'[{host}]' if ':' in host else host}:{port}"


TOKEN_ENV = "DEVLOOPS_DASHBOARD_TOKEN"  # how --daemon hands its child the token (not in argv)


def choose_token(host, token=None, use_token=None):
    """The token a server requires, or None. Required when `use_token` is true, and by default
    when `token` is given or `host` is not a loopback address; `token` sets it (else a random
    one)."""
    if use_token is None:
        use_token = bool(token) or not _is_loopback(host)
    return (token or secrets.token_urlsafe(18)) if use_token else None


def browser_allowed(env=None):
    """False when the environment sets DEVLOOPS_NO_BROWSER=1 (the tests do): no browser opens."""
    return (os.environ if env is None else env).get("DEVLOOPS_NO_BROWSER") != "1"


def _open(url, env):
    if browser_allowed(env):
        threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()


def _report(rec, ws, as_json, out, url=None):
    """Print where the server is: `serving: <url>` (and its log for a daemon), or one JSON object
    (contracts/cli.md)."""
    url = url or url_for(rec, ws.name)
    if as_json:
        obj = {"serving": url, "workspace": ws.name, "token": bool(rec.get("token")),
               "pid": rec["pid"], "daemon": bool(rec.get("daemon"))}
        if rec.get("log"):
            obj["log"] = rec["log"]
        print(json.dumps(obj), file=out, flush=True)
    else:
        print(f"serving: {url}", file=out)
        if rec.get("log"):
            print(f"log: {rec['log']}", file=out)
        out.flush()


def _already(rec, ws, as_json, out, open_browser, env):
    """A server already runs for the project: say where, and open it (a token it requires is
    in its own terminal or log, not here)."""
    _report(rec, ws, as_json, out)
    if not as_json:
        how = ("devloops dashboard --stop" if rec.get("daemon")
               else "Ctrl+C in its terminal, or devloops dashboard --stop")
        print(f"already running (pid {rec['pid']}); stop it with {how}", file=out)
    if open_browser:
        _open(url_for(rec, ws.name), env)
    return 0


def log_path(project, env=None):
    """`serve-<project hash>.log` beside the record: what a daemon prints."""
    return os.path.splitext(record_path(project, env))[0] + ".log"


def start_daemon(project, ws, argv, token=None, open_browser=True, as_json=False, env=None,
                 out=None, err=None, wait=10.0):
    """`devloops dashboard --daemon` (research R-11): start the server in the background, wait
    until it answers, and say where it is; return the exit code. `argv` are the serving options
    to pass on (`--workspace`, `--host`, `--port`, `--no-token`); `token` is the one it requires
    (None: none), handed over in the environment so other users cannot read it in the process
    list, and known here so its URL can be printed. The log is readable by this user only: the
    server prints its URL, with the token, there."""
    out, err = out or sys.stdout, err or sys.stderr
    env = dict(os.environ if env is None else env)
    current = running(project, env)
    if current:
        return _already(current, ws, as_json, out, open_browser, env)
    log = log_path(project, env)
    os.makedirs(os.path.dirname(log), exist_ok=True)
    package_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # holds devloops/
    env["PYTHONPATH"] = os.pathsep.join(p for p in (package_root, env.get("PYTHONPATH")) if p)
    env.pop(TOKEN_ENV, None)
    if token:
        env[TOKEN_ENV] = token
    command = [sys.executable, "-m", "devloops.cli", "dashboard", *argv, "--no-open",
               "--daemon-log", log]
    start = os.path.getsize(log) if os.path.exists(log) else 0
    fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    os.fchmod(fd, 0o600)  # also a log left by an earlier version
    with os.fdopen(fd, "a", encoding="utf-8") as f, open(os.devnull, "rb") as devnull:
        f.write(f"--- {state.now_iso()} devloops dashboard --daemon\n")
        f.flush()
        child = subprocess.Popen(command, stdin=devnull, stdout=f, stderr=subprocess.STDOUT,
                                 env=env, cwd=os.getcwd(), start_new_session=True)
    deadline = time.monotonic() + wait
    rec = None
    while time.monotonic() < deadline and child.poll() is None:
        rec = running(project, env)
        if rec and rec.get("pid") == child.pid and _answers(rec):
            break
        rec = None
        time.sleep(0.1)
    if rec is None:
        if child.poll() is None:
            child.kill()
        child.wait()
        try:
            with open(log, encoding="utf-8", errors="replace") as f:
                f.seek(start)
                lines = f.read().splitlines()[-20:]
        except OSError:
            lines = []
        print(f"devloops: the dashboard server did not start (log: {log})", file=err)
        for line in lines:
            print(f"  {line}", file=err)
        return 1
    url = url_for(rec, ws.name) + (f"?token={token}" if token else "")
    _report(rec, ws, as_json, out, url)
    if open_browser:
        _open(url, env)
    return 0


def _answers(rec):
    """Whether the server of `rec` answers HTTP at all (any status: a token may be required)."""
    import http.client
    parts = urllib.parse.urlsplit(rec["local_url"])
    conn = http.client.HTTPConnection(parts.hostname, parts.port, timeout=2)
    try:
        conn.request("GET", "/favicon.ico")
        conn.getresponse().read()
        return True
    except OSError:
        return False
    finally:
        conn.close()


def _command_line(pid):
    """The arguments process `pid` was started with, or None when they cannot be read."""
    try:
        with open(f"/proc/{int(pid)}/cmdline", "rb") as f:
            return [a.decode("utf-8", "replace") for a in f.read().split(b"\0") if a]
    except (OSError, ValueError):
        pass
    try:  # no /proc (macOS): ask ps
        line = subprocess.run(["ps", "-o", "command=", "-p", str(int(pid))], capture_output=True,
                              text=True, timeout=5).stdout.strip()
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return line.split() or None


def _is_dashboard(pid):
    """Whether process `pid` is a devloops dashboard server: a record left by a crash may name a
    pid the system has since given to an unrelated process, which must not be stopped."""
    args = _command_line(pid)
    return bool(args) and "dashboard" in args and any("devloops" in a for a in args)


def stop(project, env=None, as_json=False, out=None, wait=5.0):
    """`devloops dashboard --stop`: stop the project's server on this host, however it was
    started, and remove its record; return 0 (`stopped` or `not running`).

    Only a devloops dashboard is stopped: a record whose pid now belongs to another process is
    stale, and removed. A record of a server on another host (a shared home folder) is kept."""
    out = out or sys.stdout
    path = record_path(project, env)
    rec = state.read_json(path)
    stopped, elsewhere = False, None
    if isinstance(rec, dict) and rec.get("hostname") != socket.gethostname() \
            and rec.get("hostname"):
        elsewhere = rec["hostname"]
    elif isinstance(rec, dict) and _alive(rec.get("pid")) and _is_dashboard(rec.get("pid")):
        pid = int(rec["pid"])
        try:
            os.kill(pid, signal.SIGTERM)
            deadline = time.monotonic() + wait
            while time.monotonic() < deadline and _alive(pid):
                time.sleep(0.1)
            if _alive(pid):
                os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        stopped = True
    if rec is not None and elsewhere is None:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
    if as_json:
        print(json.dumps(dict({"stopped": stopped}, **({"host": elsewhere} if elsewhere else {}))),
              file=out)
    elif elsewhere:
        print(f"not running here: the server runs on {elsewhere} (pid {rec.get('pid')}); stop it "
              f"there", file=out)
    else:
        print("stopped" if stopped else "not running", file=out)
    return 0


def serve(project, kit, ws, host="127.0.0.1", port=None, token=None, use_token=None,
          open_browser=True, as_json=False, env=None, out=None, err=None, ready=None,
          daemon_log=None):
    """Serve until interrupted (Ctrl+C or SIGTERM); return the exit code.

    `ws` is the workspace the root URL opens. A token is required when `use_token` is true, and
    by default when `host` is not a loopback address; `token` sets it (else a random one).
    The browser opens unless `open_browser` is false or DEVLOOPS_NO_BROWSER=1. `daemon_log`:
    this server was started by `--daemon`, printing to that log (kept in its record).
    `ready(server)` is called once listening (tests)."""
    out, err = out or sys.stdout, err or sys.stderr
    env = os.environ if env is None else env
    current = running(project, env)
    if current:
        return _already(current, ws, as_json, out, open_browser, env)
    token = choose_token(host, token, use_token)
    workspaces_dir = os.path.realpath(project.workspaces_dir)
    extra = ({} if os.path.dirname(os.path.realpath(ws.path)) == workspaces_dir
             else {ws.name: ws.path})
    site = Site(project, kit, env, extra)
    server = _bind(host, port, site, ws.name, token)
    port = server.server_address[1]
    path = f"/w/{urllib.parse.quote(ws.name)}/"
    suffix = f"?token={token}" if token else ""
    urls = [_base(a, port) + path + suffix for a in _addresses(host)]
    local = _base(host if host not in ("0.0.0.0", "::") else
                  ("127.0.0.1" if host == "0.0.0.0" else "::1"), port)
    rec_path = record_path(project, env)
    held = _claim_record(rec_path, {"pid": os.getpid(), "hostname": socket.gethostname(),
                                    "host": host, "port": port, "local_url": local,
                                    "token": bool(token), "project": project.root,
                                    "started_at": state.now_iso(), "daemon": bool(daemon_log),
                                    **({"log": daemon_log} if daemon_log else {})}, err)
    if held:  # another server started in the meantime
        server.server_close()
        return _already(held, ws, as_json, out, open_browser, env)
    if as_json:
        print(json.dumps({"serving": urls[0], "urls": urls, "workspace": ws.name,
                          "token": bool(token), "pid": os.getpid(),
                          "daemon": bool(daemon_log)}), file=out, flush=True)
    else:
        if not _is_loopback(host):
            who = ("anyone with the token in the URL" if token else
                   "anyone who can reach this address, with no token")
            print(f"devloops: warning: the dashboard is reachable from the network ({host}:{port})"
                  f". It shows code, prompts, and Claude conversations; configured secrets are "
                  f"hidden, the rest is not, and {who} can read it. It is plain HTTP: use it on a "
                  f"trusted network only.", file=err)
        print(f"serving the dashboards of {project.root} (read-only; Ctrl+C to stop):", file=out)
        for url in urls:
            print(f"  {url}", file=out)
        out.flush()
    if open_browser:
        _open(urls[-1] if token else urls[0], env)

    def stop(signum, frame):
        raise KeyboardInterrupt
    previous = None
    if threading.current_thread() is threading.main_thread():
        previous = signal.signal(signal.SIGTERM, stop)
    try:
        if ready:
            ready(server)
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        _remove_record(rec_path)
        if previous is not None:
            signal.signal(signal.SIGTERM, previous)
    if not as_json:
        print("dashboard server stopped", file=out)
    return 0
