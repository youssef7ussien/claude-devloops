"""`devloops dashboard --serve`: the full dashboard, served live from the workspaces (002 FR-042a).

A local HTTP server (the standard library's) that renders the same page as the full dashboard
(fulldash.py), but loads each file and conversation when it is opened: nothing is embedded up
front, so there is no size limit. While a run goes on, the page asks for its workspace's version
every few seconds and, when it changed, replaces only the views that did, keeping the reader's
place (assets/dashboard.js).

Safe by default:
- it listens on 127.0.0.1 unless `--host` says otherwise; on a loopback address it answers only
  requests addressed to a loopback name, so a web page cannot reach it through DNS rebinding;
- on any other address it requires a token (in the printed URL, then kept in a cookie), unless
  `--no-token`;
- it is read-only: GET and HEAD only, and it never writes to the project;
- it sends only the files the page lists, named by their anchor, never a path from the request,
  and a listed file must lie inside the workspace (or be a recorded input);
- every text it sends goes through the workspace's redactor, as the full dashboard's does.

One server covers the project's workspaces: `/w/<name>/` is one workspace's page, and its sidebar
switches between them. While it runs, `serve-<project>.json` in the user's runtime folder records
its URL and pid, so other commands print the URL instead of the command (`running`).
"""
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import signal
import socket
import sys
import threading
import time
import urllib.parse
import webbrowser
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import dashboard, fulldash, state, workspace
from .state import DevloopsError

DEFAULT_PORT = 8765
PORT_TRIES = 20          # without --port, the next free port up to this many after the default
POLL_SECONDS = 3         # how often a page asks whether its workspace changed
SEARCH_LIMIT = 40        # results of one search
SEARCH_MAX_BYTES = 20 * 1024 * 1024  # larger files are not searched (they still open)
STREAM_BYTES = 16 * 1024 * 1024      # larger text files are streamed, not read whole
STREAM_BLOCK = 1024 * 1024
VERSION_TTL = 1.0                    # seconds a computed version serves every page
ANCHOR = re.compile(r"^f-[a-z0-9-]+$")
PAGE_CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'none'; "
            "frame-ancestors 'none'")
FILE_CSP = "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox"


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
    """The project's workspaces, and what the server knows of each: the files its page lists."""

    def __init__(self, project, kit, env=None, extra=None):
        self.project, self.kit = project, kit
        self.env = os.environ if env is None else env
        self.extra = dict(extra or {})  # workspaces outside the workspaces folder: name -> path
        self._lock = threading.Lock()
        # workspace name -> the last render: {version, html, files (anchor -> path), inputs
        # (anchors allowed outside the workspace), anchors (path -> anchor)}
        self._pages = {}
        self._versions = {}  # workspace name -> (when, version): one walk serves every tab

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

    def redactor(self, ws):
        return fulldash.workspace_redactor(ws, self.env)

    def version(self, ws):
        """A digest of everything the page shows: each file's size and time, the full dashboards
        written, and the workspaces to switch to. Computed at most once a second per workspace,
        however many pages ask."""
        now = time.monotonic()
        with self._lock:
            when, version = self._versions.get(ws.name, (None, None))
        if when is not None and now - when < VERSION_TTL:
            return version
        h = hashlib.sha1()
        for path in fulldash._walk(ws.path):
            rel = os.path.relpath(path, ws.path)
            if rel == dashboard.FILENAME:
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
            self._versions[ws.name] = (now, version)
        return version

    def rendered(self, ws):
        """The workspace's page as of its current version: rendered again only when the version
        changed, so polling pages, file requests, and unknown anchors cost a walk, not a render."""
        version = self.version(ws)
        with self._lock:
            cached = self._pages.get(ws.name)
        if cached and cached["version"] == version:
            return cached
        embedder = fulldash.LazyEmbedder(ws, self.redactor(ws))
        serve = {"workspaces": list(self.workspaces()),
                 "attrs": {"serve": POLL_SECONDS, "version": version}}
        html, _ = fulldash.render_full(dashboard.collect(ws), ws, embedder, self.env, serve=serve)
        page = {"version": version, "html": html, "files": embedder.files,
                "inputs": embedder.inputs, "anchors": dict(embedder.anchors)}
        with self._lock:
            self._pages[ws.name] = page
        return page

    def page(self, ws):
        return self.rendered(ws)["html"]

    def file(self, ws, anchor):
        """The real path of a file the page lists, or None. A file listed since the page was
        rendered is found once the version shows the change. The real path is what is opened,
        so a link swapped in after this check is not followed."""
        if not ANCHOR.match(anchor):
            return None
        page = self.rendered(ws)
        path = page["files"].get(anchor)
        if path is None:
            return None
        real, root = os.path.realpath(path), os.path.realpath(ws.path)
        inside = real == root or real.startswith(root.rstrip(os.sep) + os.sep)
        return real if inside or anchor in page["inputs"] else None

    def call(self, ws, loop, seq):
        """The conversation fragment of call `seq` of `loop`, or None if there is no such call."""
        if loop not in dashboard.LOOPS:
            return None
        loop_dir = ws.loop_dir(loop)
        records = state.read_jsonl(os.path.join(loop_dir, "state", "invocations.jsonl"))
        record = next((r for r in records if str(r.get("seq")) == seq), None)
        if record is None:
            return None
        run = state.read_json(os.path.join(loop_dir, "state", "run.json")) or {}
        redactor = self.redactor(ws)
        anchors = self.rendered(ws)["anchors"]  # the page's, so the fragment's ids match it
        body, _, _ = fulldash.conversation_body(
            ws, loop, record, run.get("target_dir"), redactor,
            lambda rel: anchors.get(os.path.normpath(rel)), self.env)
        return redactor.redact(body)[0]

    def search(self, ws, query):
        """Where `query` appears in the listed text files, then in the conversations: `[{id, kind,
        line, before, match, after}]`, at most SEARCH_LIMIT."""
        needle = query.lower()
        if len(needle) < 2:
            return []
        files = self.rendered(ws)["files"]
        redactor, found = self.redactor(ws), []
        for anchor in list(files):
            if len(found) >= SEARCH_LIMIT:
                return found
            path = self.file(ws, anchor)
            try:
                st = os.stat(path) if path else None
                if st is None or st.st_size > SEARCH_MAX_BYTES:
                    continue
                kind, _, _ = fulldash.sniff(path, st.st_size, st.st_mtime_ns)
                if kind in ("image", "binary"):
                    continue
                with open(path, encoding="utf-8", errors="replace") as f:
                    text = fulldash.viewer_text(kind, f.read(), redactor)
            except OSError:
                continue
            hit = _hit(text, needle)
            if hit:
                found.append(dict(hit, id=anchor, kind="file"))
        for loop in dashboard.LOOPS:
            loop_dir = ws.loop_dir(loop)
            run = state.read_json(os.path.join(loop_dir, "state", "run.json")) or {}
            for r in state.read_jsonl(os.path.join(loop_dir, "state", "invocations.jsonl")):
                if len(found) >= SEARCH_LIMIT:
                    return found
                text, _, _ = fulldash.read_conversation(ws, loop, r, run.get("target_dir"),
                                                        self.env)
                hit = _conversation_hit(text, needle, redactor) if text else None
                if hit:
                    found.append(dict(hit, id=fulldash.call_id(loop, r.get("seq")), kind="call"))
        return found


def _hit(text, needle):
    """The first match of `needle` in `text`: its line number and the text around it."""
    at = text.lower().find(needle)
    if at < 0:
        return None
    start = text.rfind("\n", 0, at) + 1
    end = text.find("\n", at)
    end = len(text) if end < 0 else end
    line = text[start:end]
    col = at - start
    return {"line": text.count("\n", 0, at) + 1, "before": line[max(0, col - 40):col],
            "match": line[col:col + len(needle)], "after": line[col + len(needle):col + len(needle) + 80]}


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for value in obj.values():
            yield from _strings(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _strings(value)


def _conversation_hit(text, needle, redactor):
    """The first string of a transcript (as the viewer shows it: decoded and redacted) holding
    `needle`. Each record is decoded first: its raw JSON escapes quotes, newlines, and non-ASCII
    text, so the raw line may not hold what the viewer shows."""
    for line in text.split("\n"):
        if not line.strip():
            continue
        try:
            strings = _strings(redactor.redact_obj(json.loads(line))[0])
        except ValueError:
            strings = [redactor.redact(line)[0]]
        for value in strings:
            hit = _hit(value, needle)
            if hit:
                hit.pop("line")
                return hit
    return None


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

    def _send(self, code, body, ctype="text/plain; charset=utf-8", headers=None, head=False):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
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

    def _json(self, obj, head=False):
        self._send(200, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8",
                   head=head)

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
        self._send(403, "devloops: open the URL with the token that `devloops dashboard --serve` "
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
            self._send(200, site.page(ws), "text/html; charset=utf-8", head=head)
        elif rest == ["version"]:
            self._json({"version": site.version(ws)}, head)
        elif len(rest) == 2 and rest[0] == "file":
            self._file(ws, rest[1], head)
        elif len(rest) == 3 and rest[0] == "call":
            fragment = site.call(ws, rest[1], rest[2])
            if fragment is None:
                self._send(404, "devloops: no such call\n", head=head)
            else:
                self._send(200, fragment, "text/html; charset=utf-8", head=head)
        elif rest == ["search"]:
            query = (urllib.parse.parse_qs(url.query).get("q") or [""])[0]
            self._json({"results": site.search(ws, query)}, head)
        else:
            self._send(404, "devloops: not found\n", head=head)

    def _file(self, ws, anchor, head):
        site = self.server.site
        path = site.file(ws, anchor)
        if path is None:
            self._send(404, "devloops: not a file of this dashboard\n", head=head)
            return
        try:
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except OSError:
            self._send(404, "devloops: missing\n", head=head)
            return
        with os.fdopen(fd, "rb") as f:
            st = os.fstat(fd)
            kind, _, _ = fulldash.sniff(path, st.st_size, st.st_mtime_ns)
            if kind not in ("image", "binary") and st.st_size > STREAM_BYTES:
                self._stream_text(f, site.redactor(ws), head)
                return
            data = f.read()
        name = os.path.basename(path)
        if kind == "image":
            ctype = fulldash.IMAGE_TYPES[os.path.splitext(path)[1].lower()]
            self._send(200, data, ctype, head=head)
        elif kind == "binary":
            self._send(200, data, "application/octet-stream", head=head, headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(name)}"})
        else:
            text = fulldash.viewer_text(kind, data.decode("utf-8", errors="replace"),
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


def _already(rec, ws, as_json, out):
    url = url_for(rec, ws.name)
    if as_json:
        print(json.dumps({"already_serving": True, "url": url, "pid": rec["pid"]}), file=out)
    else:
        print(f"already serving: {url} (pid {rec['pid']}); stop it (Ctrl+C in its terminal, or "
              f"kill {rec['pid']}) to start another", file=out)
    return 0


def serve(project, kit, ws, host="127.0.0.1", port=None, token=None, use_token=None,
          open_browser=False, as_json=False, env=None, out=None, err=None, ready=None):
    """Serve until interrupted (Ctrl+C or SIGTERM); return the exit code.

    `ws` is the workspace the root URL opens. A token is required when `use_token` is true, and
    by default when `host` is not a loopback address; `token` sets it (else a random one).
    `ready(server)` is called once listening (tests)."""
    out, err = out or sys.stdout, err or sys.stderr
    env = os.environ if env is None else env
    current = running(project, env)
    if current:
        return _already(current, ws, as_json, out)
    if use_token is None:
        use_token = bool(token) or not _is_loopback(host)
    token = (token or secrets.token_urlsafe(18)) if use_token else None
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
                                    "started_at": state.now_iso()}, err)
    if held:  # another server started in the meantime
        server.server_close()
        return _already(held, ws, as_json, out)
    if as_json:
        print(json.dumps({"urls": urls, "url": urls[0], "host": host, "port": port,
                          "pid": os.getpid(), "token": token}), file=out, flush=True)
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
        threading.Thread(target=webbrowser.open, args=(urls[-1] if token else urls[0],),
                         daemon=True).start()

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
