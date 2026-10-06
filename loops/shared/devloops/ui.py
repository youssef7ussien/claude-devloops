"""The dashboards' shared page shell and components (dashboard.py, fulldash.py).

A page is a sidebar and a set of views (one shown at a time), plus a viewer dialog and a "go to"
palette. The styles and the one script are real files in `assets/`, inlined when a page is written,
so every page stays a single file that works offline. Every component works without the script:
the views are then shown one after another, and file contents open in place.
"""
import html
import os

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
PROJECT_URL = "https://github.com/youssef7ussien/claude-devloops"
OWNER = "youssef7ussien"


def e(value):
    return html.escape("" if value is None else str(value), quote=True)


def asset(name):
    with open(os.path.join(ASSETS, name), encoding="utf-8") as f:
        return f.read()


# --- icons: one inline sprite; each icon is a <use> of it ------------------------------------------

ICONS = {
    "grid": '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" '
            'rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" '
            'height="7" rx="1.5"/>',
    "flow": '<circle cx="6" cy="6" r="3"/><circle cx="18" cy="18" r="3"/><path d="M9 6h4a3 3 0 0 1 3 3v6"/>',
    "loop": '<path d="M17 2l4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14"/><path d="M7 22l-4-4 4-4"/>'
            '<path d="M21 13v1a4 4 0 0 1-4 4H3"/>',
    "chat": '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "file": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
    "md": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>'
          '<path d="M9 13h6M9 17h4"/>',
    "json": '<path d="M8 3H7a2 2 0 0 0-2 2v5a2 2 0 0 1-2 2 2 2 0 0 1 2 2v5a2 2 0 0 0 2 2h1"/>'
            '<path d="M16 21h1a2 2 0 0 0 2-2v-5a2 2 0 0 1 2-2 2 2 0 0 1-2-2V5a2 2 0 0 0-2-2h-1"/>',
    "image": '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/>'
             '<path d="M21 15l-5-5L5 21"/>',
    "code": '<path d="M16 18l6-6-6-6M8 6l-6 6 6 6"/>',
    "log": '<path d="M4 6h16M4 10h16M4 14h10M4 18h7"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4'
           'M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    "menu": '<path d="M4 6h16M4 12h16M4 18h16"/>',
    "x": '<path d="M18 6L6 18M6 6l12 12"/>',
    "max": '<path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/>',
    "prev": '<path d="M15 18l-6-6 6-6"/>',
    "next": '<path d="M9 18l6-6-6-6"/>',
    "chev": '<path d="M9 18l6-6-6-6"/>',
    "copy": '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 '
            '2-2h9a2 2 0 0 1 2 2v1"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>',
    "wrap": '<path d="M3 6h18M3 12h15a3 3 0 0 1 0 6h-4M16 16l-2 2 2 2M3 18h7"/>',
    "hash": '<path d="M4 9h16M4 15h16M10 3L8 21M16 3l-2 18"/>',
    "help": '<circle cx="12" cy="12" r="9"/><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3M12 17h.01"/>',
    "list": '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    "alert": '<path d="M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>'
             '<path d="M12 9v4M12 17h.01"/>',
    "github": '<path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.9a3.4 3.4 0 0 0-.9-2.6c3.1-.4 6.4-1.5 6.4-6.9a5.4 '
              '5.4 0 0 0-1.5-3.7 5 5 0 0 0-.1-3.8s-1.2-.4-3.9 1.5a13.4 13.4 0 0 0-7 0C6.3.7 5.1 1.1 5.1 '
              '1.1a5 5 0 0 0-.1 3.8A5.4 5.4 0 0 0 3.5 8.6c0 5.4 3.3 6.5 6.4 6.9a3.4 3.4 0 0 0-.9 2.6V22"/>',
    "history": '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/>',
}


def sprite():
    return ('<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>'
            + "".join(f'<symbol id="i-{k}" viewBox="0 0 24 24">{v}</symbol>' for k, v in ICONS.items())
            + "</defs></svg>")


def icon(name, cls=""):
    return f'<svg class="ic{" " + cls if cls else ""}" aria-hidden="true"><use href="#i-{name}"/></svg>'


# --- file kinds: which viewer opens a file. Add a type here, and a viewer in dashboard.js ----------

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
        import json
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


# --- the file tree ---------------------------------------------------------------------------------

class Dir:
    """A folder of the explorer: sub-folders in insertion order, then its files (HTML strings)."""

    def __init__(self, name, badge="", open_=False):
        self.name, self.badge, self.open = name, badge, open_
        self.dirs, self.files = {}, []

    def dir(self, name, badge="", open_=False):
        if name not in self.dirs:
            self.dirs[name] = Dir(name, badge, open_)
        return self.dirs[name]

    def order(self, names):
        self.dirs = {**{n: self.dirs[n] for n in names if n in self.dirs}, **self.dirs}

    def count(self):
        return len(self.files) + sum(d.count() for d in self.dirs.values())

    def html(self):
        kids = "".join(d.html() for d in self.dirs.values())
        kids += "".join(f'<li class="f">{f}</li>' for f in self.files)
        return (f'<li class="d"><details class="dir"{" open" if self.open else ""}><summary>'
                f'<span class="node">{icon("chev", "chev")}{icon("folder", "k")}<span class="nm">'
                f'{e(self.name)}</span><span class="meta">{self.badge}<span>{self.count()}</span></span>'
                f'</span></summary><ul>{kids}</ul></details></li>')


def file_node(anchor, path, kind, lang, ic, size, meta, content):
    """One file of the explorer. Without the script it opens in place, labelled with its full path;
    with it, it opens in the viewer."""
    label = f'<code>{e(path)}</code> <span class="muted small">{e(" · ".join(x for x in (size, meta) if x))}</span>'
    return (f'<details class="file" id="{e(anchor)}" data-kind="{e(kind)}" data-lang="{e(lang)}" '
            f'data-icon="{e(ic)}" data-path="{e(path)}" data-size="{e(size)}" data-meta="{e(meta)}">'
            f'<summary><span class="node">{icon(ic, "k " + kind)}<span class="nm">'
            f'{e(path.rsplit("/", 1)[-1])}</span><span class="meta">{e(size)}</span></span></summary>'
            f'<div class="fpath">{label}</div>{content}</details>')


def missing_node(anchor, path):
    return (f'<div class="file missing" id="{e(anchor)}" data-kind="missing" data-path="{e(path)}">'
            f'<span class="node">{icon("alert", "k")}<span class="nm">missing: <code>{e(path)}</code>'
            f'</span></span></div>')


def explorer(trees, count):
    chips = "".join(f'<button type="button" class="chip" data-kind-chip="{k}" aria-pressed="false">'
                    f'{label}</button>' for k, label in FILTERS)
    return (f'<div class="toolbar"><input class="input" type="search" placeholder="Filter by path…" '
            f'aria-label="Filter files by path"><div class="chips" role="group" aria-label="File types">'
            f'{chips}</div><span class="spacer"></span><span class="small muted" data-count>{count} '
            f'files</span><button class="btn ghost" type="button" data-action="expand">Expand all</button>'
            f'<button class="btn ghost" type="button" data-action="collapse">Collapse all</button></div>'
            f'<div class="explorer"><ul>{"".join(t.html() for t in trees)}</ul></div>')


# --- the shell -------------------------------------------------------------------------------------

def view(vid, title, body, sub="", badge=""):
    """One page of the dashboard; the sidebar shows one at a time."""
    return (f'<section class="view" id="{e(vid)}" data-title="{e(title)}" aria-labelledby="h-{e(vid)}">'
            f'<div class="view-head"><div class="title"><h2 id="h-{e(vid)}">{e(title)} {badge}</h2>'
            + (f'<div class="sub">{sub}</div>' if sub else "") + f'</div></div>{body}</section>')


def nav_link(vid, label, ic, extra=""):
    return f'<a href="#{e(vid)}" data-view="{e(vid)}">{icon(ic)}{e(label)}{extra}</a>'


def nav_count(n):
    return f'<span class="count">{e(n)}</span>'


def nav_dot(tone, title):
    return f'<span class="dot tone-{e(tone)}" title="{e(title)}"></span>'


def sidebar(workspace, kind, groups, generated, version):
    """`groups` are `(title, [nav_link html])`."""
    nav = "".join(f'<div class="group">{e(title)}</div>{"".join(links)}' for title, links in groups)
    return (f'<aside class="sidebar" aria-label="Dashboard"><div class="brand"><span class="name">'
            f'<span class="logo" aria-hidden="true">d</span>devloops</span><span class="ws">workspace '
            f'<strong>{e(workspace)}</strong> · {e(kind)}</span></div>'
            f'<button class="search" type="button" data-action="palette">{icon("search")}Go to…'
            f'<kbd>Ctrl K</kbd></button><nav class="nav" aria-label="Sections">{nav}</nav>'
            f'<div class="foot"><span>Generated {e(generated)}</span>'
            f'<a class="gh" href="{e(PROJECT_URL)}" target="_blank" rel="noopener noreferrer">'
            f'{icon("github")}<span>devloops {e(version)} · by {e(OWNER)}</span></a></div></aside>')


def topbar(workspace, status, live=False):
    """`live`: the page reloads itself while a run goes on; a button pauses it."""
    live_btn = ('<button class="btn live" type="button" data-action="live" aria-pressed="true" '
                'title="This page reloads while the run goes on. Select to pause.">'
                '<span class="pulse" aria-hidden="true"></span><span data-live-label>Live</span>'
                '</button>' if live else "")
    return (f'<header class="topbar"><button class="btn icon ghost menu-btn" type="button" '
            f'data-action="menu" aria-label="Menu">{icon("menu")}</button><div class="crumbs">'
            f'{e(workspace)} <span aria-hidden="true">/</span><strong data-crumb>Overview</strong></div>'
            f'<span class="spacer"></span>{live_btn}{status}<button class="btn icon" type="button" '
            f'data-action="palette" aria-label="Go to (Ctrl K)" title="Go to (Ctrl K)">{icon("search")}'
            f'</button><button class="btn icon" type="button" data-action="theme" aria-label="Toggle theme"'
            f' title="Toggle theme">{icon("sun")}</button></header>')


DIALOGS = (
    '<dialog class="viewer" id="viewer" aria-label="Viewer"><div class="v-head"><div class="v-title">'
    '<div class="v-path"></div><div class="v-meta"></div></div><div class="v-nav">'
    f'<button class="btn icon ghost" type="button" data-step="-1" aria-label="Previous" '
    f'title="Previous ([)">{icon("prev")}</button><span class="pos small muted"></span>'
    f'<button class="btn icon ghost" type="button" data-step="1" aria-label="Next" title="Next (])">'
    f'{icon("next")}</button></div><button class="btn icon ghost" type="button" data-action="max" '
    f'aria-label="Maximize" title="Maximize (f)" aria-pressed="false">{icon("max")}</button>'
    f'<button class="btn icon ghost" type="button" data-action="close" aria-label="Close" '
    f'title="Close (Esc)">{icon("x")}</button></div><div class="tabs" hidden></div>'
    '<div class="v-tools"></div><div class="v-body" tabindex="-1"></div>'
    '<div class="v-status" role="status" aria-live="polite"></div></dialog>'
    '<dialog class="palette" id="palette" aria-label="Go to"><input type="text" '
    'placeholder="Go to a file, call, or view…" aria-label="Go to" autocomplete="off">'
    '<ul role="listbox" aria-label="Results"></ul></dialog>')


def page(title, side, top, views, refresh=0):
    """A complete page: the inline styles, the shell, `views`, the dialogs, and the one script.
    `refresh`: seconds between reloads while a run goes on (0: never)."""
    attr = f" data-refresh='{int(refresh)}'" if refresh else ""
    return (f"<!doctype html><html lang='en' class='no-js'{attr}><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<title>{e(title)}</title><style>{asset('dashboard.css')}</style></head><body>"
            f"{sprite()}<div class='app'>{side}<main class='content'>{top}{''.join(views)}</main>"
            f"</div>{DIALOGS}<div id='tip' role='tooltip'></div>"
            f"<script>{asset('dashboard.js')}</script></body></html>\n")
