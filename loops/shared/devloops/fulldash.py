"""The full dashboard: one self-contained, shareable page per generation (002 FR-035 to FR-042).

It holds everything the lightweight dashboard shows, and also embeds every artifact of the workspace
and the Claude Code conversation of every recorded call (contracts/full-dashboard.md):
- each file is a node of the Files explorer, opened in the page's viewer (or in place without the
  script); images are `data:` URIs, other binary files `data:` download links, and text and JSON
  are HTML-escaped;
- a missing file stays in place, shown as `missing: <path>`;
- each call's conversation is a hidden source the viewer opens from the calls view.

Every embedded string goes through a `Redactor` built from the loops' frozen configurations. The
page loads nothing from outside itself: links point to anchors in the page (the one exception is
the project's GitHub link, which only navigates), and the only script is the shared one (ui.py).

Files are written to `<dashboards_dir>/<workspace>/<YYYYMMDDTHHMMSSZ>[-n].html`, created
exclusively, so a generation never replaces an earlier one.
"""
import base64
import json
import os
import re
from datetime import datetime, timezone

from . import __version__, claude, dashboard, state, ui
from .dashboard import e, money, number, duration
from .redact import Redactor

LOOPS = dashboard.LOOPS
NOTICE = "Contains full Claude Code conversations — review before sharing"
FINAL_STATUSES = ("completed", "stopped-on-failure", "stopped-on-input-error",
                  "stopped-on-service-error")
COLLAPSE_LINES = 40
# A file larger than this is listed with its size and path but not embedded, so one big log or
# recording cannot swell the page. Conversations are always embedded whole.
MAX_EMBED_BYTES = 5 * 1024 * 1024
IMAGE_TYPES = ui.IMAGE_TYPES
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


def _pre(text, lang=None, markdown=False):
    """Escaped preformatted text. The script highlights `lang`, or renders it as Markdown."""
    attr = ' data-md=""' if markdown else (f' data-lang="{e(lang)}"' if lang else "")
    return f"<pre{attr}>{e(text)}</pre>"


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


def embed(path, redactor, max_bytes=MAX_EMBED_BYTES):
    """`(kind, lang, icon, content html, bytes)` for one file, or None when it cannot be read.

    Images are `data:` URIs, other binary files `data:` download links, and text is escaped (JSON
    indented, with every value redacted). A file over `max_bytes` is kind `large`: not embedded."""
    try:
        size = os.path.getsize(path)
        if size > max_bytes:
            return ("large", "", "file", f'<div class="inline too-large">Not embedded: '
                    f'{e(human_bytes(size))}, over the {e(human_bytes(max_bytes))} limit. Open it on '
                    f'disk.</div>', size)
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None
    ext = os.path.splitext(path)[1].lower()
    name = os.path.basename(path)
    text = None
    if ext not in IMAGE_TYPES:
        try:
            text = data.decode("utf-8")
            if "\x00" in text:
                text = None
        except UnicodeDecodeError:
            text = None
    kind, lang, ic = ui.kind_of(path, text)
    if kind == "image":
        uri = f"data:{IMAGE_TYPES[ext]};base64,{base64.b64encode(data).decode('ascii')}"
        return kind, lang, ic, f'<div class="inline"><img src="{uri}" alt="{e(name)}"></div>', len(data)
    if kind == "binary":
        uri = f"data:application/octet-stream;base64,{base64.b64encode(data).decode('ascii')}"
        return (kind, lang, ic, f'<div class="inline"><a download="{e(name)}" href="{uri}">download '
                f'{e(name)} ({e(human_bytes(len(data)))})</a></div>', len(data))
    if kind in ("json", "jsonl"):
        text = _json_text(text, redactor) or text
    return kind, lang, ic, f'<pre class="src">{e(redactor.redact(text)[0])}</pre>', len(data)


class Embedder:
    """Renders artifacts once each, gives each an anchor, and tracks sizes for the report."""

    def __init__(self, ws, redactor, max_bytes=MAX_EMBED_BYTES):
        self.ws = ws
        self.redactor = redactor
        self.max_bytes = max_bytes
        self.anchors = {}
        self.sizes = []
        self.skipped = []  # files over the limit: [{path, bytes}]

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

    def item(self, item):
        """One file of the explorer, labelled with its path, size, and its milestone, trial, and
        step; or `missing: <path>`."""
        rel = item["rel"]
        shown = self.redactor.redact(rel)[0].replace(os.sep, "/")
        anchor = self.anchor(rel)
        embedded = embed(item["abs"], self.redactor, self.max_bytes)
        if embedded is None:
            return ui.missing_node(anchor, shown)
        kind, lang, ic, content, size = embedded
        (self.skipped if kind == "large" else self.sizes).append({"path": rel, "bytes": size})
        meta = []
        if item.get("milestone"):
            meta.append(f"milestone {item['milestone']}")
        if item.get("trial") is not None:
            meta.append(f"trial {item['trial']}")
        if item.get("step"):
            meta.append(f"call {item['seq']} · {item['step']}")
        return ui.file_node(anchor, shown, kind, lang, ic, human_bytes(size), " · ".join(meta),
                            content)


class EmbeddedLinks(dashboard.FileLinks):
    """Links for the shared views: to the files embedded in this page (they open in the viewer),
    never to files on disk or the network."""

    def __init__(self, embedder):
        self.embedder = embedder

    def _anchor(self, relpath):
        return self.embedder.anchors.get(os.path.normpath(relpath))

    def path(self, relpath, text=None):
        anchor = self._anchor(relpath)
        if anchor:
            return f'<a href="#{anchor}">{ui.icon("file")}{e(text or relpath)}</a>'
        return f'<span class="missing">missing: <code>{e(relpath)}</code></span>'

    def image(self, relpath, alt):
        anchor = self._anchor(relpath)
        if not anchor:
            return self.path(relpath, alt)
        return (f'<a href="#{anchor}" title="{e(alt)}"><img class="thumb" data-src-of="{anchor}" '
                f'alt="{e(alt)}"></a>')

    def button(self, relpath, label, ic="file"):
        anchor = self._anchor(relpath)
        if not anchor:
            return ""
        return f'<a class="btn" href="#{anchor}">{ui.icon(ic)}{e(label)}</a>'

    def url(self, url):
        return f"<code>{e(url)}</code>"


# --- the file explorer ------------------------------------------------------------------------------

def loop_tree(loop, d, items, embedder):
    """A loop's files: Inputs, Plan, Milestones (each trial, its evidence), Calls (the prompts and
    their settings), Outputs, Run state, and progress.md. Conversations are in the calls view."""
    top = ui.Dir(loop, dashboard.pill(d["status"], dashboard.RUN_STATUS), open_=True)
    trials = {(m["id"], t["n"]): t for m in d["milestones"] for t in m["trials"]}
    statuses = {m["id"]: m["status"] for m in d["milestones"]}
    for item in items:
        section, rel = item["section"], item["rel"]
        if section == "calls" and rel.endswith(".jsonl"):
            continue
        node = embedder.item(item)
        if section == "milestones":
            mid = item["milestone"]
            folder = top.dir("Milestones", open_=True).dir(
                mid, dashboard.pill(statuses.get(mid, "pending"), dashboard.MILESTONE_STATUS))
            if item.get("trial") is not None:
                trial = trials.get((mid, item["trial"])) or {}
                folder = folder.dir(f"Trial {item['trial']}",
                                    dashboard.pill(trial.get("status"), dashboard.TRIAL_STATUS))
                if f"{os.sep}evidence{os.sep}" in rel:
                    folder = folder.dir("evidence")
            folder.files.append(node)
        elif section == "progress":
            top.files.insert(0, node)
        else:
            title = {"inputs": "Inputs", "plan": "Plan", "calls": "Calls", "outputs": "Outputs",
                     "state": "Run state"}[section]
            top.dir(title, open_=section in ("inputs", "outputs")).files.append(node)
    top.order(["Inputs", "Plan", "Milestones", "Calls", "Outputs", "Run state"])
    return top


def other_trees(ws, embedder):
    """The orchestrator's files and the workspace's own files (outside the loop folders)."""
    orch, own = ui.Dir("orchestrator"), ui.Dir("workspace")
    for path in _walk(ws.path):
        rel = os.path.relpath(path, ws.path)
        top = rel.split(os.sep)[0]
        if top in LOOPS or rel in SKIPPED:
            continue
        (orch if top == "orchestrator" else own).files.append(
            embedder.item({"rel": rel, "abs": path}))
    return [t for t in (orch, own) if t.count()]


# --- conversations ----------------------------------------------------------------------------------

def _lines(text):
    return text.count("\n") + 1


def _block(kind, avatar, title, body, hint="", collapsed=False, open_=False):
    """One transcript block: a header (who, and a one-line hint), and its body."""
    head = (f'<span class="av" aria-hidden="true">{e(avatar)}</span><span>{e(title)}</span>'
            + (f'<span class="hint">{e(hint)}</span>' if hint else ""))
    if collapsed:
        return (f'<details class="msg {kind}"{" open" if open_ else ""}><summary>{head}</summary>'
                f'<div class="body">{body}</div></details>')
    return f'<div class="msg {kind}"><div class="who">{head}</div><div class="body">{body}</div></div>'


def _raw(obj, title):
    return _block("raw", "·", title, _pre(json.dumps(obj, indent=2, ensure_ascii=False), "json"),
                  collapsed=True)


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
                images.append(f'<img class="result-image" alt="tool result image" '
                              f'src="data:{media};base64,{e(item["source"].get("data", ""))}">')
        else:
            texts.append(json.dumps(item, indent=2, ensure_ascii=False))
    return "\n".join(texts), "".join(images)


def _tool_hint(data):
    for key in ("command", "file_path", "notebook_path", "pattern", "url", "path", "query",
                "description"):
        if isinstance(data.get(key), str):
            return data[key].split("\n")[0][:160]
    return ""


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
            for key, title, cls in (("old_string", "old", "del"), ("new_string", "new", "add"),
                                    ("content", "content", "add"), ("new_source", "new", "add")):
                if isinstance(edit.get(key), str):
                    parts.append(f'<div class="diff"><div class="label">{title}</div>'
                                 f'<pre class="{cls}">{e(edit[key])}</pre></div>')
        rest = {k: v for k, v in data.items()
                if k not in ("file_path", "notebook_path", "old_string", "new_string", "content",
                             "new_source", "edits")}
        if rest:
            parts.append(_pre(json.dumps(rest, indent=2, ensure_ascii=False), "json"))
    elif name == "Bash" and isinstance(data.get("command"), str):
        parts.append(_pre(data["command"], "shell"))
        rest = {k: v for k, v in data.items() if k != "command"}
        if rest:
            parts.append(_pre(json.dumps(rest, indent=2, ensure_ascii=False), "json"))
    else:
        parts.append(_pre(json.dumps(data, indent=2, ensure_ascii=False), "json"))
    return _block("tool", "T", f"Tool: {name}", "".join(parts), _tool_hint(data), collapsed=True)


def _content_block(role, block):
    if not isinstance(block, dict):
        return _raw(block, "content")
    kind = block.get("type")
    if kind == "text":
        text = str(block.get("text", ""))
        if role == "user":
            lines = _lines(text)
            return _block("user", "U", "User", _pre(text, markdown=True), f"{lines} lines",
                          collapsed=True, open_=lines <= COLLAPSE_LINES)
        return _block("assistant", "C", "Claude", _pre(text, markdown=True))
    if kind == "thinking":
        return _block("thinking", "…", "Thinking", _pre(str(block.get("thinking", ""))),
                      collapsed=True)
    if kind == "tool_use":
        return _tool_use(block)
    if kind == "tool_result":
        text, images = _text_of(block.get("content"))
        error = bool(block.get("is_error"))
        lines = _lines(text)
        first = next((ln for ln in text.split("\n") if ln.strip()), "")[:140]
        hint = f"{lines} lines · {first}" if lines > 1 else first
        return _block("result error" if error else "result", "!" if error else "R",
                      "Result (error)" if error else "Result",
                      _pre(text, "json" if ui.looks_like_json(text) else None) + images, hint,
                      collapsed=True, open_=error or lines <= 12)
    return _raw(block, str(kind or "content"))


def render_conversation(text, redactor, anchor=None):
    """The transcript's records in order (contracts/full-dashboard.md, Conversation rendering).

    Messages and their content blocks are rendered; any other record is a collapsed raw JSON block
    (hidden until "System records" is shown), and a line that is not JSON is shown as text. Nothing
    is dropped or truncated.
    """
    out = []
    for line in text.split("\n"):  # not splitlines: a string may hold U+2028
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            out.append(_block("raw", "·", "unparsed line", _pre(redactor.redact(line)[0]),
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
    body = "".join(out) or '<p class="muted">The transcript is empty.</p>'
    attr = f' id="{e(anchor)}"' if anchor else ""
    return f'<div class="conv"{attr}>{body}</div>'


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


# --- calls ------------------------------------------------------------------------------------------

def call_id(loop, seq):
    return f"call-{loop}-{seq}"


def _prompt_sources(sources):
    """The parts the prompt was composed from, and where each came from (002 FR-031)."""
    if not sources:
        return ""
    items = "".join(
        f'<li><code>{e(s.get("part"))}</code>: {e(s.get("source"))} '
        f'<code>{e(s.get("path"))}</code> <span class="muted">sha256 '
        f'{e((s.get("sha256") or "")[:12])}</span></li>' for s in sources)
    return f'<div class="prompt-sources"><h4>Prompt parts</h4><ul class="small">{items}</ul></div>'


def call_sources(ws, data, embedder, env):
    """One hidden source per call (the viewer opens it): its header, prompt parts, and
    conversation (FR-040). Returns `(html, models, unavailable)`."""
    redactor, parts, models, unavailable = embedder.redactor, [], {}, 0
    for loop, d in data["loops"].items():
        for r in sorted(d["invocations"], key=lambda r: r.get("seq") or 0):
            seq = r.get("seq")
            text, source, reason = read_conversation(ws, loop, r, d.get("target_dir"), env)
            model = _model(text)
            models[(loop, seq)] = model
            prompt = r.get("prompt_path")
            prompt_id = embedder.anchors.get(os.path.normpath(os.path.join(loop, prompt))) \
                if prompt else None
            settings_id = embedder.anchors.get(os.path.normpath(os.path.join(
                loop, prompt[:-len(".md")] + ".settings.json"))) if prompt else None
            head = [loop, r.get("milestone_id") or "planning",
                    f"trial {r.get('trial')}" if r.get("trial") is not None else None, model,
                    f"{number(dashboard.tokens_of(r))} tokens", money(r.get("cost_usd")),
                    duration((r.get("duration_ms") or 0) / 1000), f"session {r.get('session_id')}"]
            head = redactor.redact(" · ".join(str(h) for h in head if h))[0]
            title = f"{loop} · #{seq} {r.get('step')}"
            failure = r.get("failure_class")
            flag = (f' <span class="pill tone-critical">{e(failure)} failure</span>'
                    if failure not in (None, "none") else "")
            if text is None:
                unavailable += 1
                body = (f'<p class="unavailable missing">Conversation unavailable ({e(reason)}); '
                        f'session <code>{e(r.get("session_id"))}</code></p>')
            else:
                rel = os.path.join(loop, r["conversation_path"]) if source == "copied" else None
                note = (f'copied: <code>{e(rel)}</code>' if rel else
                        "read from Claude Code's history (recorded before conversations were copied)")
                body = (f'<p class="muted small">{note}</p>'
                        + render_conversation(text, redactor, embedder.anchor(rel) if rel else None))
                embedder.sizes.append({"path": rel or f"{loop} call {seq} conversation",
                                       "bytes": len(text.encode("utf-8"))})
            parts.append(
                f'<section class="call-src" id="{e(call_id(loop, seq))}" data-title="{e(title)}" '
                f'data-meta="{e(head)}" data-prompt="{e(prompt_id or "")}" '
                f'data-settings="{e(settings_id or "")}"><h3>{e(title)}{flag}</h3>'
                f'<p class="muted small">{e(head)}</p>{_prompt_sources(r.get("prompt_sources"))}'
                f'{body}</section>')
    return f'<div class="calls-src">{"".join(parts)}</div>', models, unavailable


# --- the page ---------------------------------------------------------------------------------------

def render_full(data, ws, embedder, env=None, trigger=None):
    """The full page and the number of conversations shown as unavailable."""
    redactor = embedder.redactor
    data = redactor.redact_obj(data)[0]
    artifacts = {loop: collect_artifacts(ws, loop) for loop in data["loops"]}
    for items in artifacts.values():  # anchors first, so every view can link to them
        for item in items:
            embedder.anchor(item["rel"])
    for path in _walk(ws.path):
        embedder.anchor(os.path.relpath(path, ws.path))
    links = EmbeddedLinks(embedder)

    trees = [loop_tree(loop, d, artifacts[loop], embedder) for loop, d in data["loops"].items()]
    trees += other_trees(ws, embedder)
    files = sum(t.count() for t in trees)
    sources, models, unavailable = call_sources(ws, data, embedder, env)

    def call_ref(loop):
        sessions = {r.get("session_id"): call_id(loop, r.get("seq"))
                    for r in data["loops"][loop]["invocations"]}
        return sessions.get

    notice = (f'<p class="notice">{ui.icon("alert")}<span><strong>{e(NOTICE)}.</strong> Configured '
              f'secrets are replaced with <code>***</code>; other sensitive text may remain. '
              f'Generated {e(data["generated_at"])} by devloops {e(__version__)}'
              + (f" · {e(trigger)}" if trigger else "") + "</span></p>")
    views = [dashboard.overview_view(data, links, notice,
                                     lambda loop, r: call_id(loop, r.get("seq"))),
             dashboard.orchestrator_view(data)]
    views += [dashboard.loop_view(loop, d, ws.path, links, call_ref(loop), files_view=True)
              for loop, d in data["loops"].items()]
    views += [dashboard.calls_view(data, links, lambda loop, r: call_id(loop, r.get("seq")),
                                   models, sources),
              ui.view("files", "Files", ui.explorer(trees, files),
                      "Every artifact in the workspace, embedded in this page"),
              dashboard.questions_view(data), dashboard.events_view(data)]
    title = f"devloops · {data['workspace']} · full dashboard"
    page = ui.page(title, dashboard.sidebar(data, "full dashboard",
                                            dashboard.detail_links(data, files)),
                   ui.topbar(data["workspace"],
                             dashboard.pill(dashboard._overall_status(data), dashboard.RUN_STATUS)),
                   [v for v in views if v])
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


def write(ws, trigger=None, env=None, now=None, max_bytes=MAX_EMBED_BYTES):
    """Write a new full dashboard for `ws`; return `{path, bytes, largest, unavailable,
    not_embedded}`.

    `largest` is the five largest embedded items and `not_embedded` the files over `max_bytes`
    (both `[{path, bytes}]`). It never replaces an earlier file (FR-036).
    """
    embedder = Embedder(ws, workspace_redactor(ws, env), max_bytes)
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
    skipped = sorted(embedder.skipped, key=lambda i: (-i["bytes"], i["path"]))
    return {"path": path, "bytes": len(data), "largest": largest, "unavailable": unavailable,
            "not_embedded": skipped}


def is_final(status):
    return status in FINAL_STATUSES
