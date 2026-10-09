"""The workspace's files and conversations, as the dashboard reads them (specs/005-dashboard-redesign
research R-14): no HTML here, only data.

- Which files the dashboard lists, in which folders, and under which ids (`file_index`); each
  file's kind (`kind_of`, `sniff`) and its content as the viewer shows it (`file_content`).
- The redactor built from the loops' frozen configurations (`workspace_redactor`): every text
  the dashboard sends passes through it.
- A call's Claude Code conversation: where it is read from (`read_conversation`), and its
  records parsed and redacted, with the failed tool results and the files it changed
  (`parse_conversation`).

The server (serve.py) and the export build their responses from these; the old full dashboard
(fulldash.py) imports them too until it is removed.
"""
import base64
import json
import os
import re

from . import claude, state
from .redact import Redactor


def _dashboard():
    # Imported when used: dashboard.py imports ui.py, which imports the file kinds from here.
    from . import dashboard
    return dashboard


# A file larger than this is listed with its size and path but not embedded in an export, so one
# big log or recording cannot swell the page. Conversations are always embedded whole.
MAX_EMBED_BYTES = 5 * 1024 * 1024
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
CALL_FILE = re.compile(r"^(\d{4,})-([a-z-]+?)(\.settings\.json|\.md|\.jsonl)$")
PLAN_OUTPUTS = re.compile(r"^(plan-summary\.md|open-questions\.md|milestone-.*\.md)$")


# --- file kinds: which viewer opens a file. Add a type here, and a viewer in the app -------------

KINDS = {  # extension: (kind, language, icon)
    ".md": ("markdown", "", "md"), ".json": ("json", "", "json"), ".jsonl": ("jsonl", "", "json"),
    ".py": ("code", "python", "code"), ".js": ("code", "js", "code"), ".mjs": ("code", "js", "code"),
    ".ts": ("code", "ts", "code"), ".sh": ("code", "shell", "code"),
    ".command": ("code", "shell", "code"), ".yml": ("code", "yaml", "code"),
    ".yaml": ("code", "yaml", "code"), ".html": ("code", "html", "code"),
    ".css": ("code", "css", "code"), ".diff": ("code", "diff", "code"),
    ".headers": ("code", "http", "log"), ".log": ("log", "", "log"), ".txt": ("text", "", "log"),
}
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
               ".webp": "image/webp"}
FILTERS = (("markdown", "Markdown"), ("json", "JSON"), ("code", "Code"), ("log", "Logs"),
           ("text", "Text"), ("image", "Images"))


def looks_like_json(text):
    stripped = (text or "").lstrip()
    if stripped[:1] not in ("{", "["):
        return False
    try:
        json.loads(text)
        return True
    except ValueError:
        return False


def kind_of(path, text):
    """`(kind, language, icon)` for a file: by extension, else JSON when it parses, else text.
    `text` is None for a file that is not UTF-8 text."""
    ext = os.path.splitext(path)[1].lower()
    if ext in IMAGE_TYPES:
        return "image", "", "image"
    if text is None:
        return "binary", "", "file"
    if ext in KINDS:
        return KINDS[ext]
    if looks_like_json(text):
        return "json", "", "json"
    return "text", "", "log"


# --- collecting -------------------------------------------------------------------------------------

def workspace_redactor(ws, env=None):
    """A `Redactor` for the secrets of every loop's frozen configuration.

    Each loop's own secrets are a subset, so every string still passes through each loop's
    redactor (FR-041); the union also covers workspace-level files shared by both loops.
    """
    names, literals = set(), set()
    for loop in _dashboard().LOOPS:
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


def relative(path, start):
    """`os.path.relpath(path, start)` for a path `_walk(start)` (or a folder in it) gave: cut, not
    worked out, since listing a large workspace asks for thousands."""
    prefix = start.rstrip(os.sep) + os.sep
    return path[len(prefix):] if path.startswith(prefix) else os.path.relpath(path, start)


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
        parts = relative(path, loop_dir).split(os.sep)
        if parts == ["state", "lock"]:
            continue
        section, details = _classify(parts)
        items.append(dict(details, rel=relative(path, ws.path), abs=path, section=section))
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


# --- text as the viewer shows it -------------------------------------------------------------------

def human_bytes(size):
    if size is None:
        return "–"
    for limit, unit in ((1 << 30, "GB"), (1 << 20, "MB"), (1 << 10, "KB")):
        if size >= limit:
            return f"{size / limit:.1f} {unit}"
    return f"{size} bytes"


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


def viewer_text(kind, text, redactor):
    """A text file as the viewer shows it: JSON indented, and every secret replaced."""
    if kind in ("json", "jsonl"):
        text = _json_text(text, redactor) or text
    return redactor.redact(text)[0]


SNIFF_BYTES = 64 * 1024
WHOLE_BYTES = 1024 * 1024  # a file this small is read whole to tell its kind


_SNIFFED = {}  # (path, size, mtime_ns) -> (kind, lang, icon): a served page lists files often
_SNIFFED_MAX = 50000


def sniff(path, size, mtime_ns=None):
    """`(kind, lang, icon)` of a file from its first bytes (the whole file when small), so a large
    file is not read just to be listed. With `mtime_ns`, remembered until the file changes."""
    key = (path, size, mtime_ns)
    if mtime_ns is not None and key in _SNIFFED:
        return _SNIFFED[key]
    found = _sniff(path, size)
    if mtime_ns is not None:
        if len(_SNIFFED) >= _SNIFFED_MAX:
            _SNIFFED.clear()
        _SNIFFED[key] = found
    return found


def _sniff(path, size):
    with open(path, "rb") as f:
        data = f.read(size if size <= WHOLE_BYTES else SNIFF_BYTES)
    text = None
    if os.path.splitext(path)[1].lower() not in IMAGE_TYPES:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as err:
            if len(data) < size and err.start >= len(data) - 3:  # cut inside a character
                text = data[:err.start].decode("utf-8", errors="replace")
        if text is not None and "\x00" in text:
            text = None
    return kind_of(path, text)


def call_id(loop, seq):
    return f"call-{loop}-{seq}"


# --- file contents ----------------------------------------------------------------------------------

def file_content(path, redactor, max_bytes=MAX_EMBED_BYTES):
    """One file as the viewer shows it, or None when it cannot be read:
    `{kind, lang, size, text}` for text (redacted; JSON indented), `{kind, size, type, base64}`
    for images and other binary files, `{kind: "large", size, not_embedded: true}` over
    `max_bytes` (None: no limit)."""
    try:
        size = os.path.getsize(path)
        if max_bytes is not None and size > max_bytes:
            return {"kind": "large", "size": size, "not_embedded": True}
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None
    ext = os.path.splitext(path)[1].lower()
    text = None
    if ext not in IMAGE_TYPES:
        try:
            text = data.decode("utf-8")
            if "\x00" in text:
                text = None
        except UnicodeDecodeError:
            text = None
    kind, lang, _ = kind_of(path, text)
    if kind in ("image", "binary"):
        return {"kind": kind, "size": len(data),
                "type": IMAGE_TYPES.get(ext) if kind == "image" else "application/octet-stream",
                "base64": base64.b64encode(data).decode("ascii")}
    return {"kind": kind, "lang": lang, "size": len(data),
            "text": viewer_text(kind, text, redactor)}


# --- the file listing -------------------------------------------------------------------------------

class _Dir:
    """A folder of the listing: sub-folders in insertion order, then its files."""

    def __init__(self, name, badge=None, open_=False):
        self.name, self.badge, self.open = name, badge, open_
        self.dirs, self.files = {}, []

    def dir(self, name, badge=None, open_=False):
        if name not in self.dirs:
            self.dirs[name] = _Dir(name, badge, open_)
        return self.dirs[name]

    def order(self, names):
        self.dirs = {**{n: self.dirs[n] for n in names if n in self.dirs}, **self.dirs}

    def count(self):
        return len(self.files) + sum(d.count() for d in self.dirs.values())

    def tree(self):
        node = {"name": self.name,
                "children": [d.tree() for d in self.dirs.values()] + self.files}
        if self.badge:
            node["badge"] = self.badge
        if self.open:
            node["open"] = True
        return node


class _Ids:
    """Today's anchors: `f-<slug>` of a workspace-relative path, `-2`, `-3`, … on a collision.

    A file is known by `key` (its workspace-relative path unless given), so a recorded input
    outside the workspace that is labelled like a workspace file still gets its own id."""

    def __init__(self):
        self.ids = {}
        self.used = set()

    def __call__(self, rel, key=None):
        rel = os.path.normpath(rel)
        key = rel if key is None else key
        if key not in self.ids:
            slug = re.sub(r"[^A-Za-z0-9]+", "-", rel).strip("-").lower() or "file"
            anchor, n = "f-" + slug, 2
            while anchor in self.used:
                anchor, n = f"f-{slug}-{n}", n + 1
            self.ids[key] = anchor
            self.used.add(anchor)
        return self.ids[key]


def _meta(item):
    meta = []
    if item.get("milestone"):
        meta.append(f"milestone {item['milestone']}")
    if item.get("trial") is not None:
        meta.append(f"trial {item['trial']}")
    if item.get("step"):
        meta.append(f"call {item['seq']} · {item['step']}")
    return " · ".join(meta)


def file_index(ws, data):
    """The files the dashboard lists for `ws` (`data` is `dashboard.collect(ws)`).

    Returns `{"trees": [Tree], "count": n, "by_id": {id: real path}, "inputs": {id}}`:
    - a Tree node is `{name, children: [...], badge?: {status, table}, open?}` for a folder and
      `{name, file: FileRef}` for a file; one tree per loop (Inputs, Plan, Milestones → each
      trial → evidence, Calls, Outputs, Run state, and `progress.md` first), then `run/` and the
      workspace's own files;
    - a FileRef is `{id, path, kind, lang, icon, size, version, meta}`, or `{id, path, missing:
      true}` for a file that cannot be read; `id` is today's anchor, so links stay stable;
    - `by_id` holds the files that can be sent (never a missing one), `inputs` the ids of
      recorded inputs, which may lie outside the workspace.
    Conversations are not listed (the calls show them), nor the summary page and a run's lock.
    """
    dashboard = _dashboard()
    ids, by_id, inputs = _Ids(), {}, set()
    root = os.path.realpath(ws.path)

    def key(item):
        """An input outside the workspace is known by its real path, not by its label."""
        if item.get("section") == "inputs":
            real = os.path.realpath(item["abs"])
            if not (real == root or real.startswith(root.rstrip(os.sep) + os.sep)):
                return "\0" + real
        return None

    artifacts = {loop: collect_artifacts(ws, loop) for loop in data["loops"]}
    paths = list(_walk(ws.path))  # walked once: for the ids, then for the run's and own files
    for items in artifacts.values():  # ids in the order the old pages gave them
        for item in items:
            ids(item["rel"], key(item))
    for path in paths:
        ids(relative(path, ws.path))

    def ref(item):
        rel = item["rel"]
        fid = ids(rel, key(item))
        shown = rel.replace(os.sep, "/")
        try:
            st = os.stat(item["abs"])
            kind, lang, ic = sniff(item["abs"], st.st_size, st.st_mtime_ns)
        except OSError:
            return {"name": shown.rsplit("/", 1)[-1],
                    "file": {"id": fid, "path": shown, "missing": True}}
        by_id[fid] = item["abs"]
        if item.get("section") == "inputs" and item.get("input"):
            inputs.add(fid)
        return {"name": shown.rsplit("/", 1)[-1], "file": {
            "id": fid, "path": shown, "kind": kind, "lang": lang, "icon": ic, "size": st.st_size,
            "version": f"{st.st_size}-{st.st_mtime_ns}", "meta": _meta(item)}}

    trees = []
    for loop, d in data["loops"].items():
        top = _Dir(loop, {"status": d["status"], "table": "run"}, open_=True)
        trials = {(m["id"], t["n"]): t for m in d["milestones"] for t in m["trials"]}
        statuses = {m["id"]: m["status"] for m in d["milestones"]}
        for item in artifacts[loop]:
            section, rel = item["section"], item["rel"]
            if section == "calls" and rel.endswith(".jsonl"):
                continue
            node = ref(item)
            if section == "milestones":
                mid = item["milestone"]
                folder = top.dir("Milestones", open_=True).dir(
                    mid, {"status": statuses.get(mid, "pending"), "table": "milestone"})
                if item.get("trial") is not None:
                    trial = trials.get((mid, item["trial"])) or {}
                    folder = folder.dir(f"Trial {item['trial']}",
                                        {"status": trial.get("status"), "table": "trial"})
                    if f"{os.sep}evidence{os.sep}" in rel:
                        folder = folder.dir("evidence")
                folder.files.append(node)
            elif section == "progress":
                top.files.insert(0, node)
            else:
                title = {"inputs": "Inputs", "plan": "Plan", "calls": "Calls",
                         "outputs": "Outputs", "state": "Run state"}[section]
                top.dir(title, open_=section in ("inputs", "outputs")).files.append(node)
        top.order(["Inputs", "Plan", "Milestones", "Calls", "Outputs", "Run state"])
        trees.append(top)
    orch, own = _Dir("run"), _Dir("workspace")
    for path in paths:
        rel = relative(path, ws.path)
        first = rel.split(os.sep)[0]
        if first in dashboard.LOOPS or rel == dashboard.FILENAME:
            continue
        (orch if first == "run" else own).files.append(ref({"rel": rel, "abs": path}))
    trees += [t for t in (orch, own) if t.count()]
    return {"trees": [t.tree() for t in trees], "count": sum(t.count() for t in trees),
            "by_id": by_id, "inputs": inputs}


# --- conversations ----------------------------------------------------------------------------------

def _blocks(record):
    message = record.get("message") if isinstance(record, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def parse_conversation(text, redactor):
    """A transcript's records, parsed and redacted: `{records, errors, files_changed}`.

    Each non-blank line is one record (split on "\\n" only: a U+2028 inside a string is not a
    line break); a line that is not JSON is `{"raw": <redacted text>}`. `errors` are the indexes
    of records holding a failed tool result; `files_changed` is `[{path, tool, block}]`, one per
    path (its last change, in the order of last changes), from the edit tools' uses, where
    `block` is the index of the record holding the tool use.
    """
    records, errors, changed = [], [], {}
    for line in text.split("\n"):
        if not line.strip():
            continue
        try:
            record = redactor.redact_obj(json.loads(line))[0]
        except ValueError:
            record = {"raw": redactor.redact(line)[0]}
        k = len(records)
        records.append(record)
        for block in _blocks(record):
            if block.get("type") == "tool_result" and block.get("is_error"):
                if not errors or errors[-1] != k:
                    errors.append(k)
            elif block.get("type") == "tool_use" and block.get("name") in EDIT_TOOLS:
                data = block.get("input") if isinstance(block.get("input"), dict) else {}
                path = data.get("file_path") or data.get("notebook_path")
                if isinstance(path, str) and path:
                    changed.pop(path, None)
                    changed[path] = {"path": path, "tool": block["name"], "block": k}
    return {"records": records, "errors": errors, "files_changed": list(changed.values())}
