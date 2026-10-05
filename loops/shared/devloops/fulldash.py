"""The full dashboard: one self-contained, shareable page per generation (002 FR-035 to FR-042).

It holds everything the lightweight dashboard shows, and also embeds every artifact of the workspace
and the Claude Code conversation of every recorded call (contracts/full-dashboard.md):
- images are `data:` URIs, other binary files `data:` download links;
- text and JSON are HTML-escaped inside collapsed `<details>`;
- a missing file stays in place, shown as `missing: <path>`.

Every embedded string goes through a `Redactor` built from the loops' frozen configurations. The
page refers to nothing outside itself: links point to anchors in the page, and the only script is
the lightweight page's theme toggle and tooltips.

Files are written to `<dashboards_dir>/<workspace>/<YYYYMMDDTHHMMSSZ>[-n].html`, created
exclusively, so a generation never replaces an earlier one.
"""
import base64
import json
import os
import re
from datetime import datetime, timezone

from . import __version__, claude, dashboard, state
from .dashboard import e, money, number, duration
from .redact import Redactor

LOOPS = dashboard.LOOPS
NOTICE = "Contains full Claude Code conversations — review before sharing"
FINAL_STATUSES = ("completed", "stopped-on-failure", "stopped-on-input-error",
                  "stopped-on-service-error")
COLLAPSE_LINES = 40
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".gif": "image/gif", ".webp": "image/webp"}
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
CALL_FILE = re.compile(r"^(\d{4,})-([a-z-]+?)(\.settings\.json|\.md|\.jsonl)$")
PLAN_OUTPUTS = re.compile(r"^(plan-summary\.md|open-questions\.md|milestone-.*\.md)$")
# Files that are not artifacts: the lightweight page itself, and a run's lock.
SKIPPED = {dashboard.FILENAME}


# --- collecting -------------------------------------------------------------------------------------

def workspace_redactor(ws, env=None):
    """A `Redactor` for the secrets of every loop's frozen configuration.

    Each loop's own secrets are a subset, so every string still passes through each loop's
    redactor (FR-041); the union also covers workspace-level files shared by both loops.
    """
    names, literals = set(), set()
    for loop in LOOPS:
        rs = state.read_json(os.path.join(ws.loop_dir(loop), "state", "run.json")) or {}
        secrets = (rs.get("effective_config") or {}).get("secrets") or {}
        names.update(secrets.get("env") or [])
        literals.update(secrets.get("literals") or [])
    return Redactor({"secrets": {"env": sorted(names), "literals": sorted(literals)}},
                    environ=os.environ if env is None else env)


def _classify(parts):
    """`(section, details)` for a file at loop-relative path `parts` (contracts/full-dashboard.md)."""
    path = "/".join(parts)
    if parts[:2] in (["state", "prompts"], ["state", "conversations"]) and len(parts) == 3:
        match = CALL_FILE.match(parts[2])
        if match:
            return "calls", {"seq": int(match.group(1)), "step": match.group(2)}
    if parts[:2] == ["state", "milestones"] and len(parts) >= 4:
        details = {"milestone": parts[2]}
        if parts[3] == "trials" and len(parts) >= 6 and parts[4].isdigit():
            details["trial"] = int(parts[4])
        return "milestones", details
    if path in ("state/plan.json",) or (parts[0] == "outputs" and len(parts) == 2
                                        and PLAN_OUTPUTS.match(parts[1])):
        return "plan", {}
    if path in ("task.md", "state/api-spec.json"):
        return "inputs", {}
    if parts[0] == "outputs":
        return "outputs", {}
    if path == "progress.md":
        return "progress", {}
    return "state", {}


def _walk(top):
    for dirpath, dirnames, names in os.walk(top):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(names):
            if not name.startswith("."):
                yield os.path.join(dirpath, name)


def collect_artifacts(ws, loop):
    """Every file of one loop, plus its recorded inputs: `[{rel, abs, section, ...}]`.

    `rel` is relative to the workspace (an input outside it keeps its recorded path). Items carry
    `milestone`, `trial`, `seq`, and `step` where they apply.
    """
    loop_dir = ws.loop_dir(loop)
    items = []
    rs = state.read_json(os.path.join(loop_dir, "state", "run.json")) or {}
    for name, value in (rs.get("inputs") or {}).items():
        if isinstance(value, dict) and value.get("path"):
            path = value["path"]
            items.append({"rel": _label(ws, path), "abs": path, "section": "inputs",
                          "input": name})
    for path in _walk(loop_dir):
        parts = os.path.relpath(path, loop_dir).split(os.sep)
        if parts == ["state", "lock"]:
            continue
        section, details = _classify(parts)
        items.append(dict(details, rel=os.path.relpath(path, ws.path), abs=path, section=section))
    return items


def _label(ws, path):
    """How an input file outside the workspace is named: project-relative when inside it."""
    try:
        return ws.project.relative_or_absolute(path)
    except AttributeError:
        return path


def read_conversation(ws, loop, record, target_dir=None, env=None):
    """`(text, source, reason)` for one invocation record's conversation.

    `source` is `copied` (the workspace copy), `history` (Claude Code's history, for records made
    before conversations were copied), or None with a `reason` when it is unavailable.
    """
    rel = record.get("conversation_path")
    if rel:
        path = os.path.join(ws.loop_dir(loop), rel)
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                return f.read(), "copied", None
        except OSError:
            return None, None, f"missing: {os.path.relpath(path, ws.path)}"
    if record.get("conversation") == "unavailable":
        return None, None, record.get("conversation_reason") or "not-found"
    source = claude.find_transcript(record.get("session_id"), target_dir, env)
    if source is None:
        return None, None, "not-found"
    try:
        with open(source, encoding="utf-8", errors="replace") as f:
            return f.read(), "history", None
    except OSError:
        return None, None, "unreadable"


# --- embedding --------------------------------------------------------------------------------------

def human_bytes(size):
    if size is None:
        return "–"
    for limit, unit in ((1 << 30, "GB"), (1 << 20, "MB"), (1 << 10, "KB")):
        if size >= limit:
            return f"{size / limit:.1f} {unit}"
    return f"{size} bytes"


def _pre(text, collapse_title=None):
    """Escaped preformatted text; collapsed under `collapse_title` when it is long."""
    block = f"<pre>{e(text)}</pre>"
    lines = text.count("\n") + 1
    if collapse_title and lines > COLLAPSE_LINES:
        return f"<details><summary>{e(collapse_title)} ({lines} lines)</summary>{block}</details>"
    return block


def _json_text(text, redactor):
    """Pretty JSON (or JSON lines) with every value redacted; None if `text` is not JSON."""
    try:
        return json.dumps(redactor.redact_obj(json.loads(text))[0], indent=2, ensure_ascii=False)
    except ValueError:
        pass
    lines = []
    for line in text.split("\n"):
        if not line.strip():
            continue
        try:
            lines.append(json.dumps(redactor.redact_obj(json.loads(line))[0], ensure_ascii=False))
        except ValueError:
            return None
    return "\n".join(lines) if lines else None


def embed(path, redactor):
    """`(html, bytes)` for one file: an image, a download link, escaped text, or `missing`."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None, None
    ext = os.path.splitext(path)[1].lower()
    name = os.path.basename(path)
    if ext in IMAGE_TYPES:
        uri = f"data:{IMAGE_TYPES[ext]};base64,{base64.b64encode(data).decode('ascii')}"
        return (f'<details class="shot"><summary><img src="{uri}" alt="{e(name)}"></summary>'
                f'</details>', len(data))
    try:
        text = data.decode("utf-8")
        if "\x00" in text:
            raise UnicodeDecodeError("utf-8", data, 0, 1, "NUL byte")
    except UnicodeDecodeError:
        uri = f"data:application/octet-stream;base64,{base64.b64encode(data).decode('ascii')}"
        return (f'<a download="{e(name)}" href="{uri}">download {e(name)} '
                f'({e(human_bytes(len(data)))})</a>', len(data))
    if ext in (".json", ".jsonl"):
        text = _json_text(text, redactor) or text
    return _pre(redactor.redact(text)[0]), len(data)


class Embedder:
    """Renders artifacts once each, gives each an anchor, and tracks sizes for the report."""

    def __init__(self, ws, redactor):
        self.ws = ws
        self.redactor = redactor
        self.anchors = {}
        self.sizes = []

    def anchor(self, rel):
        rel = os.path.normpath(rel)
        if rel not in self.anchors:
            slug = re.sub(r"[^A-Za-z0-9]+", "-", rel).strip("-").lower() or "file"
            used = set(self.anchors.values())
            anchor, n = "f-" + slug, 2
            while anchor in used:
                anchor, n = f"f-{slug}-{n}", n + 1
            self.anchors[rel] = anchor
        return self.anchors[rel]

    def item(self, item, open_=False):
        """One labelled artifact: path, size, and its milestone, trial, and step."""
        content, size = embed(item["abs"], self.redactor)
        rel = item["rel"]
        meta = [human_bytes(size) if size is not None else None]
        if item.get("milestone"):
            meta.append(f"milestone {item['milestone']}")
        if item.get("trial") is not None:
            meta.append(f"trial {item['trial']}")
        if item.get("step"):
            meta.append(f"call {item['seq']} · {item['step']}")
        meta = " · ".join(m for m in meta if m)
        label = (f'<code>{e(self.redactor.redact(rel)[0])}</code> '
                 f'<span class="muted small">{e(meta)}</span>')
        anchor = self.anchor(rel)
        if content is None:
            return (f'<div class="file missing" id="{anchor}">missing: '
                    f'<code>{e(self.redactor.redact(rel)[0])}</code></div>')
        self.sizes.append({"path": rel, "bytes": size})
        if content.startswith("<details class=\"shot\"") or content.startswith("<a download"):
            return f'<div class="file" id="{anchor}"><div>{label}</div>{content}</div>'
        return (f'<details class="file" id="{anchor}"{" open" if open_ else ""}><summary>{label}'
                f'</summary>{content}</details>')


class EmbeddedLinks(dashboard.FileLinks):
    """Links for the shared sections: to anchors in this page, never to files or the network."""

    def __init__(self, embedder):
        self.embedder = embedder

    def path(self, relpath, text=None):
        rel = os.path.normpath(relpath)
        if rel in self.embedder.anchors:
            return f'<a href="#{self.embedder.anchors[rel]}">{e(text or relpath)}</a>'
        return f'<span class="missing">missing: <code>{e(relpath)}</code></span>'

    def image(self, relpath, alt):
        return self.path(relpath, alt)

    def url(self, url):
        return f"<code>{e(url)}</code>"


# --- conversations ----------------------------------------------------------------------------------

def _block(kind, title, body, collapsed=False):
    if collapsed:
        return (f'<details class="msg {kind}"><summary>{e(title)}</summary>{body}</details>')
    return f'<div class="msg {kind}"><div class="who">{e(title)}</div>{body}</div>'


def _raw(obj, title):
    text = json.dumps(obj, indent=2, ensure_ascii=False)
    return _block("raw", title, f"<pre>{e(text)}</pre>", collapsed=True)


def _text_of(content):
    """The text of a tool result's content: a string, or a list of text and image blocks."""
    if isinstance(content, str):
        return content, ""
    texts, images = [], []
    for item in content if isinstance(content, list) else []:
        if not isinstance(item, dict):
            texts.append(json.dumps(item, ensure_ascii=False))
        elif item.get("type") == "text":
            texts.append(str(item.get("text", "")))
        elif item.get("type") == "image" and isinstance(item.get("source"), dict) \
                and item["source"].get("type") == "base64":
            media = str(item["source"].get("media_type") or "image/png")
            if re.fullmatch(r"image/[a-z0-9.+-]+", media):
                images.append(f'<details class="shot"><summary><img alt="tool result image" '
                              f'src="data:{media};base64,{e(item["source"].get("data", ""))}">'
                              f'</summary></details>')
        else:
            texts.append(json.dumps(item, indent=2, ensure_ascii=False))
    return "\n".join(texts), "".join(images)


def _tool_use(block):
    name = str(block.get("name") or "?")
    data = block.get("input") if isinstance(block.get("input"), dict) else {}
    parts = []
    if name in EDIT_TOOLS:
        path = data.get("file_path") or data.get("notebook_path")
        if path:
            parts.append(f'<div class="small">file <code>{e(path)}</code></div>')
        edits = data.get("edits") if isinstance(data.get("edits"), list) else [data]
        for edit in edits:
            if not isinstance(edit, dict):
                continue
            for key, title in (("old_string", "old"), ("new_string", "new"),
                               ("content", "content"), ("new_source", "new")):
                if isinstance(edit.get(key), str):
                    parts.append(f'<div class="small muted">{title}</div>'
                                 + _pre(edit[key], f"{title} text"))
        rest = {k: v for k, v in data.items()
                if k not in ("file_path", "notebook_path", "old_string", "new_string", "content",
                             "new_source", "edits")}
        if rest:
            parts.append(_pre(json.dumps(rest, indent=2, ensure_ascii=False)))
    else:
        parts.append(_pre(json.dumps(data, indent=2, ensure_ascii=False), "input"))
    return _block("tool", f"Tool: {name}", "".join(parts))


def _content_block(role, block):
    if not isinstance(block, dict):
        return _raw(block, "content")
    kind = block.get("type")
    if kind == "text":
        text = str(block.get("text", ""))
        title = "User" if role == "user" else "Claude"
        return _block(role, title, _pre(text, "text"),
                      collapsed=role == "user" and text.count("\n") + 1 > COLLAPSE_LINES)
    if kind == "thinking":
        return _block("thinking", "Thinking", _pre(str(block.get("thinking", ""))),
                      collapsed=True)
    if kind == "tool_use":
        return _tool_use(block)
    if kind == "tool_result":
        text, images = _text_of(block.get("content"))
        error = bool(block.get("is_error"))
        title = "Result (error)" if error else "Result"
        lines = text.count("\n") + 1
        return _block("result error" if error else "result", title + (
            f" ({lines} lines)" if lines > COLLAPSE_LINES else ""), _pre(text) + images,
            collapsed=lines > COLLAPSE_LINES)
    return _raw(block, str(kind or "content"))


def render_conversation(text, redactor):
    """The transcript's records in order (contracts/full-dashboard.md, Conversation rendering).

    Messages and their content blocks are rendered; any other record is collapsed raw JSON, and
    a line that is not JSON is shown as text. Nothing is dropped or truncated.
    """
    out = []
    for line in text.split("\n"):  # not splitlines: a string may hold U+2028
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            out.append(_block("raw", "unparsed line", _pre(redactor.redact(line)[0]),
                              collapsed=True))
            continue
        obj = redactor.redact_obj(obj)[0]
        message = obj.get("message") if isinstance(obj, dict) else None
        role = obj.get("type") if isinstance(obj, dict) else None
        if role in ("user", "assistant") and isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                content = [{"type": "text", "text": content}]
            if isinstance(content, list):
                out.extend(_content_block(role, block) for block in content)
                continue
        out.append(_raw(obj, str(role or "record")))
    return "".join(out) or '<p class="muted">The transcript is empty.</p>'


def _model(text):
    for line in (text or "").split("\n"):
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        message = obj.get("message") if isinstance(obj, dict) else None
        if isinstance(message, dict) and message.get("model"):
            return message["model"]
    return None


# --- sections ---------------------------------------------------------------------------------------

def _files(embedder, items, empty="Nothing recorded."):
    if not items:
        return f'<p class="muted">{e(empty)}</p>'
    return "".join(embedder.item(i) for i in items)


def artifacts_section(loop, items, embedder):
    by = {}
    for item in items:
        by.setdefault(item["section"], []).append(item)
    parts = [f'<section><h2 id="files-{e(loop)}">{e(loop)} · artifacts</h2>']
    for section, title in (("inputs", "Inputs"), ("plan", "Plan")):
        parts.append(f"<h3>{title}</h3>" + _files(embedder, by.get(section, [])))
    milestones = {}
    for item in by.get("milestones", []):
        milestones.setdefault(item["milestone"], []).append(item)
    parts.append("<h3>Milestones</h3>")
    for mid in sorted(milestones):
        files = milestones[mid]
        checks = [i for i in files if i.get("trial") is None]
        trials = {}
        for i in files:
            if i.get("trial") is not None:
                trials.setdefault(i["trial"], []).append(i)
        body = _files(embedder, checks, "No checks.")
        for n in sorted(trials):
            body += f"<h4>Trial {n}</h4>" + _files(embedder, trials[n])
        parts.append(f'<details class="milestone" open><summary><span class="mid">{e(mid)}</span>'
                     f'</summary>{body}</details>')
    if not milestones:
        parts.append('<p class="muted">No milestone files yet.</p>')
    for section, title in (("outputs", "Outputs"), ("progress", "Progress"),
                           ("state", "Run state")):
        parts.append(f"<h3>{title}</h3>" + _files(embedder, by.get(section, [])))
    return "".join(parts) + "</section>"


def calls_section(ws, loop, d, items, embedder, env):
    """One block per recorded call: its header, prompt, and conversation (FR-040)."""
    redactor = embedder.redactor
    files = {}
    for item in items:
        if item["section"] == "calls":
            files.setdefault(item["seq"], []).append(item)
    target = d.get("target_dir")
    parts = [f'<section><h2 id="calls-{e(loop)}">{e(loop)} · Claude calls and conversations</h2>']
    unavailable = 0
    records = sorted(d["invocations"], key=lambda r: r.get("seq") or 0)
    for r in records:
        seq = r.get("seq")
        text, source, reason = read_conversation(ws, loop, r, target, env)
        tokens = sum((r.get("tokens") or {}).get(k) or 0
                     for k in ("input", "output", "cache_creation", "cache_read"))
        head = [f"#{seq}", r.get("step"), r.get("milestone_id") or "planning",
                f"trial {r.get('trial')}" if r.get("trial") is not None else None,
                f"session {r.get('session_id')}", _model(text),
                f"{number(tokens)} tokens", money(r.get("cost_usd")),
                duration((r.get("duration_ms") or 0) / 1000)]
        head = " · ".join(str(h) for h in head if h)
        prompt_files = [i for i in files.pop(seq, []) if not i["rel"].endswith(".jsonl")]
        body = "<h4>Prompt</h4>" + _files(embedder, prompt_files, "No prompt file.")
        body += "<h4>Conversation</h4>"
        if text is None:
            unavailable += 1
            body += (f'<p class="file missing">Conversation unavailable ({e(reason)}); session '
                     f'<code>{e(r.get("session_id"))}</code></p>')
        else:
            rel = os.path.join(loop, r["conversation_path"]) if source == "copied" else None
            note = (f'copied: <code>{e(rel)}</code>' if rel else
                    "read from Claude Code's history (recorded before conversations were copied)")
            anchor = f' id="{embedder.anchor(rel)}"' if rel else ""
            body += (f'<div class="conversation"{anchor}><p class="muted small">{note}</p>'
                     f'{render_conversation(text, redactor)}</div>')
            embedder.sizes.append({"path": rel or f"{loop} call {seq} conversation",
                                   "bytes": len(text.encode("utf-8"))})
        failure = r.get("failure_class")
        flag = (f' <span class="pill tone-critical">{e(failure)} failure</span>'
                if failure not in (None, "none") else "")
        parts.append(f'<details class="call" id="call-{e(loop)}-{e(seq)}"><summary>'
                     f'{e(redactor.redact(head)[0])}{flag}</summary>{body}</details>')
    if not records:
        parts.append('<p class="muted">No Claude call recorded.</p>')
    leftovers = [i for seq in sorted(files) for i in files[seq]]
    if leftovers:
        parts.append("<h3>Call files without a record</h3>" + _files(embedder, leftovers))
    return "".join(parts) + "</section>", unavailable


def other_files(ws, embedder):
    """The orchestrator's files and the workspace's own files (outside the loop folders)."""
    orch, own = [], []
    for path in _walk(ws.path):
        rel = os.path.relpath(path, ws.path)
        top = rel.split(os.sep)[0]
        if top in LOOPS or rel in SKIPPED:
            continue
        (orch if top == "orchestrator" else own).append({"rel": rel, "abs": path})
    parts = []
    if orch:
        parts.append('<section><h2 id="orchestrator-files">Orchestrator files</h2>'
                     + _files(embedder, orch) + "</section>")
    parts.append('<section><h2 id="workspace-files">Workspace files</h2>'
                 + _files(embedder, own) + "</section>")
    return "".join(parts)


CSS = """
.notice{border-left:3px solid var(--warning);background:var(--surface);padding:10px 14px;
border-radius:8px;margin:12px 0}
pre{font:12px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;background:var(--chip);
padding:8px 10px;border-radius:6px;white-space:pre-wrap;word-break:break-word;margin:4px 0}
.file{margin:6px 0}.missing{color:var(--critical)}
details.file>summary,details.call>summary{font-weight:400;color:var(--ink)}
details.call{background:var(--surface);border:1px solid var(--border);border-radius:10px;
padding:8px 12px}
details.shot{display:inline-block;margin:2px}details.shot>summary{list-style:none;cursor:zoom-in}
details.shot>summary::-webkit-details-marker{display:none}
details.shot img{height:96px;border-radius:6px;border:1px solid var(--border)}
details.shot[open] img{height:auto;max-width:100%;cursor:zoom-out}
.msg{border-left:3px solid var(--grid);padding:2px 0 2px 10px;margin:8px 0}
.msg .who,details.msg>summary{font-size:12px;font-weight:600;color:var(--ink-2)}
.msg.user{border-left-color:var(--muted)}.msg.assistant{border-left-color:var(--series)}
.msg.tool{border-left-color:var(--warning)}.msg.result{border-left-color:var(--good)}
.msg.result.error{border-left-color:var(--critical)}
"""


def render_full(data, ws, embedder, env=None, trigger=None):
    """The full page and the number of conversations shown as unavailable."""
    redactor = embedder.redactor
    data = redactor.redact_obj(data)[0]
    artifacts = {loop: collect_artifacts(ws, loop) for loop in data["loops"]}
    for items in artifacts.values():  # anchors first, so the shared sections can link to them
        for item in items:
            embedder.anchor(item["rel"])
    for path in _walk(ws.path):
        embedder.anchor(os.path.relpath(path, ws.path))
    links = EmbeddedLinks(embedder)

    files, calls, unavailable = [], [], 0
    for loop, d in data["loops"].items():
        files.append(artifacts_section(loop, artifacts[loop], embedder))
        html_calls, n = calls_section(ws, loop, d, artifacts[loop], embedder, env)
        calls.append(html_calls)
        unavailable += n
    rest = other_files(ws, embedder)

    req = data["requirements"]
    nav = dashboard.nav_links(data) + "".join(
        f'<a href="#files-{e(loop)}">{e(loop)} files</a><a href="#calls-{e(loop)}">{e(loop)} '
        f'calls</a>' for loop in data["loops"])
    meta = (f'<p class="meta">Workspace <code>{e(data["workspace"])}</code> · requirements '
            f'<code>{e(req.get("path"))}</code> · generated {e(data["generated_at"])} by devloops '
            f'{e(__version__)}' + (f" · {e(trigger)}" if trigger else "") + "</p>")
    notice = (f'<p class="notice"><strong>{e(NOTICE)}.</strong> Configured secrets are replaced '
              f'with <code>***</code>; other sensitive text may remain.</p>')
    body = [dashboard.header(f"devloops · {data['workspace']} · full dashboard", nav), "<main>",
            notice, meta, *dashboard.summary_sections(data, ws.path, links), *files, *calls, rest,
            "</main>"]
    page = dashboard.page(f"devloops · {data['workspace']} · full dashboard", body, CSS)
    return redactor.redact(page)[0], unavailable


# --- writing ----------------------------------------------------------------------------------------

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


def write(ws, trigger=None, env=None, now=None):
    """Write a new full dashboard for `ws`; return `{path, bytes, largest, unavailable}`.

    `largest` is the five largest embedded items (`[{path, bytes}]`). It never replaces an
    earlier file (FR-036).
    """
    embedder = Embedder(ws, workspace_redactor(ws, env))
    page, unavailable = render_full(dashboard.collect(ws), ws, embedder, env, trigger)
    data = page.encode("utf-8")
    directory = dashboard.full_dashboards_dir(ws)
    os.makedirs(directory, exist_ok=True)
    fd, path = _create(directory, now or datetime.now(timezone.utc))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
    except BaseException:
        try:
            os.remove(path)
        except OSError:
            pass
        raise
    largest = sorted(embedder.sizes, key=lambda i: (-i["bytes"], i["path"]))[:5]
    return {"path": path, "bytes": len(data), "largest": largest, "unavailable": unavailable}


def is_final(status):
    return status in FINAL_STATUSES
