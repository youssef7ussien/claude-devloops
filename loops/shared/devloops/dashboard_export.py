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


def _element(key, data):
    """One data element. `<` is written `\\u003c` inside it (JSON reads it the same), so no
    `</script` or `<!--` in a file or a conversation can end or change the element."""
    text = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    return f'<script type="application/json" id="d:{key}">{text}</script>\n'


def _create(directory, now):
    """Open a new `<UTC timestamp>[-n].html` exclusively; return `(fd, path)`."""
    stamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    n = 1
    while True:
        path = os.path.join(directory, f"{stamp}.html" if n == 1 else f"{stamp}-{n}.html")
        try:
            return os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644), path
        except FileExistsError:
            n += 1


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
    # A file's text is in its own element: its corpus item names it (`file`) instead of a copy.
    corpus = []
    for item in serve.SearchIndex(keep=0).corpus(ctx):
        if item["kind"] == "file":
            content = (files.get(item["id"]) or (None, {}))[1]
            if content.get("text") != item["text"]:
                continue  # not embedded as text (too large, or unreadable now)
            item = dict(item, file=item["id"])
            del item["text"]
        corpus.append(item)
    items.append(("search-corpus", {"items": ctx.redactor.redact_obj(corpus)[0]}))
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


def write(ws, path=None, env=None, now=None, max_bytes=MAX_EMBED_BYTES):
    """Write the export of `ws`; return `{path, bytes, largest, unavailable, not_embedded}`
    (contracts/export.md "Output report"). Without `path` it is a new file in
    `<workspace>/exports/`, never replacing an earlier one; a given `path` is written, replacing
    what is there."""
    now = now or datetime.now(timezone.utc)
    page, report = render(ws, env, now, max_bytes)
    data = page.encode("utf-8")
    if path:
        path = os.path.abspath(path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    else:
        directory = exports_dir(ws)
        os.makedirs(directory, exist_ok=True)
        fd, path = _create(directory, now)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
    except BaseException:
        try:
            os.remove(path)
        except OSError:
            pass
        raise
    return dict(report, path=path, bytes=len(data))
