"""`devloops dashboard --export [<path>]`: the dashboard app in one file, with its data
(specs/005-dashboard-redesign contracts/export.md, FR-011–FR-015).

The page is the served app (appbundle.shell, inline, without the vendor files: no syntax
highlighting, FR-033) with every API answer it can ask for embedded as a
`<script type="application/json" id="d:<path>">` element, built by the same builders and
redacted by the same redactor as the server (serve.route_api, serve.build_answer), so the export
shows what the server shows (SC-007, SC-008). The app reads an element the first time its data is
asked for (assets/app/api.js); nothing is fetched and nothing polls.
"""
import json
import os
import tempfile
from datetime import datetime, timezone

from . import __version__, appbundle, artifacts, dashboard, serve
from .artifacts import MAX_EMBED_BYTES

CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; "
       "base-uri 'none'; form-action 'none'")
LARGEST = 5  # items the report lists


def exports_dir(ws):
    return os.path.join(ws.path, artifacts.EXPORTS)


def _q(value):
    return dashboard._quote(value)  # as the app's encodeURIComponent


def api_paths(ctx):
    """Every API path the app can ask for in this workspace, in the page's order: the views, then
    per loop the loop, its trials, and its calls, then the file listing (each file's content is
    added by `write`). The paths are written as the views write them (assets/app/views/)."""
    paths = ["summary", "now", "index", "calls", "files", "events", "questions"]
    for loop, d in ctx.data["loops"].items():
        paths.append(f"loops/{loop}")
        for m in d["milestones"]:
            for t in m["trials"]:
                paths.append(f"loops/{loop}/milestones/{_q(m['id'])}/trials/{_q(t['key'])}")
        for r in sorted(d["invocations"], key=lambda r: r.get("seq") or 0):
            paths.append(f"calls/{loop}/{_q(r.get('seq'))}")
    return list(dict.fromkeys(paths))


def _answer(ctx, path):
    """The server's answer for API path `path`: `(status, data)`."""
    found = serve.route_api(path)
    if found is None:
        return 404, {"error": "not found"}
    build, args, _ = found
    return serve.build_answer(ctx, build, args)


def _files(ctx, max_bytes):
    """`{file id: (workspace-relative path, content)}` of every file the server may send
    (serve._sendable), each `artifacts.file_content`; a file over `max_bytes` is
    `{not_embedded: true, size, path}`. A file that cannot be read is left out."""
    out, root = {}, os.path.realpath(ctx.ws.path)
    rel = {ref["id"]: ref["path"] for ref in ctx.refs.values() if ref.get("id")}
    for file_id in ctx.index["by_id"]:
        path = serve._sendable(ctx.index, root, file_id)
        if path is None:
            continue
        content = artifacts.file_content(path, ctx.redactor, max_bytes)
        if content is None:
            continue
        shown = rel.get(file_id) or artifacts.relative(path, ctx.ws.path)
        if content.get("not_embedded"):
            content = {"not_embedded": True, "size": content["size"], "path": shown}
        out[file_id] = (shown, content)
    return out


def _corpus(ctx, files):
    """The search corpus, in the server's order (serve.SearchIndex): each file embedded as text,
    naming its element (`file`) instead of copying the text it holds, then the calls and the
    events, read as the server reads them."""
    out = [{"kind": "file", "id": file_id, "label": shown,
            "route": dashboard.route("file", id=file_id), "file": file_id}
           for file_id, (shown, content) in files.items() if "text" in content]
    for item, _, path, read in serve.SearchIndex(keep=0).sources(ctx):
        if item["kind"] == "file":
            continue
        try:
            text = read(path, os.stat(path), ctx.redactor)
        except OSError:
            continue
        out.append(dict(item, text=text))
    return out


def _element(key, data):
    """One data element. `<` is written `\\u003c` inside it (JSON reads it the same), so no
    `</script` or `<!--` in a file or a conversation can end or change the element."""
    text = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    return f'<script type="application/json" id="d:{key}">{text}</script>\n'


def render(ws, env=None, now=None, max_bytes=MAX_EMBED_BYTES):
    """`(page, report)`: the export's HTML and `{largest, unavailable, not_embedded}`."""
    now = now or datetime.now(timezone.utc)
    ctx = dashboard.Context(ws, env)
    items, sizes, unavailable = [], [], 0
    summary = None
    for path in api_paths(ctx):
        status, data = _answer(ctx, path)
        if status != 200:
            continue
        if path == "summary":
            summary = data
        if path.startswith("calls/") and data.get("conversation") == "unavailable":
            unavailable += 1
        items.append((path, data))
    not_embedded = []
    files = _files(ctx, max_bytes)
    for file_id, (shown, content) in files.items():
        if content.get("not_embedded"):
            not_embedded.append({"path": shown, "bytes": content["size"]})
        items.append((f"files/{file_id}", content))
    items.append(("search-corpus", {"items": ctx.redactor.redact_obj(_corpus(ctx, files))[0]}))
    parts = []
    for key, data in items:
        part = _element(key, data)
        parts.append(part)
        sizes.append({"path": key, "bytes": len(part.encode("utf-8"))})
    attrs = {"source": "embedded", "workspace": ws.name,
             "exported-at": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "devloops-version": __version__,
             "running": "true" if (summary or {}).get("running") else "false"}
    head = f'<meta http-equiv="Content-Security-Policy" content="{CSP}">\n'
    page = appbundle.shell(f"devloops · {ws.name} · snapshot", attrs, inline=True,
                           data="".join(parts), head=head)
    largest = sorted(sizes, key=lambda i: (-i["bytes"], i["path"]))[:LARGEST]
    return page, {"largest": largest, "unavailable": unavailable,
                  "not_embedded": sorted(not_embedded, key=lambda i: (-i["bytes"], i["path"]))}


def _target(ws, path, now):
    """`(directory, name or None)` of the export: the given path's, or `<workspace>/exports/`
    (the name is chosen when writing). The folder is created and must be writable, so a bad path
    fails before the page is built."""
    directory = os.path.dirname(os.path.abspath(path)) if path else exports_dir(ws)
    os.makedirs(directory, exist_ok=True)
    if not os.access(directory, os.W_OK):
        raise PermissionError(f"cannot write to {directory}")
    return directory, os.path.basename(path) if path else None


def _publish(tmp, directory, name, now):
    """Move the written temp file into place: over `name` (replaced atomically), or, without
    one, to a new `<UTC timestamp>[-n].html` that never replaces an earlier export."""
    if name:
        path = os.path.join(directory, name)
        os.replace(tmp, path)
        return path
    stamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    n = 1
    while True:
        path = os.path.join(directory, f"{stamp}.html" if n == 1 else f"{stamp}-{n}.html")
        try:
            os.link(tmp, path)  # fails when the name is taken: exclusive, and whole once seen
        except FileExistsError:
            n += 1
            continue
        os.remove(tmp)
        return path


def write(ws, path=None, env=None, now=None, max_bytes=MAX_EMBED_BYTES):
    """Write the export of `ws`; return `{path, bytes, largest, unavailable, not_embedded}`
    (contracts/export.md "Output report"). Without `path` it is a new file in
    `<workspace>/exports/`, never replacing an earlier one; a given `path` is replaced. The page
    is written to a temp file beside it and moved into place, so a failed write leaves what was
    there."""
    now = now or datetime.now(timezone.utc)
    directory, name = _target(ws, path, now)
    page, report = render(ws, env, now, max_bytes)
    data = page.encode("utf-8")
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".export-", suffix=".tmp")
    try:
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        path = _publish(tmp, directory, name, now)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return dict(report, path=path, bytes=len(data))
