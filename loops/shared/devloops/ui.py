"""The dashboards' shared page shell and components (dashboard.py, fulldash.py).

A page is a sidebar and a set of views (one shown at a time), plus a viewer dialog and a "go to"
palette. The styles and the one script are real files in `assets/`, inlined when a page is written,
so every page stays a single file that works offline. Every component works without the script:
the views are then shown one after another, and file contents open in place.
"""
import hashlib
import html
import os

from . import appbundle
from .artifacts import (  # noqa: F401 - the file kinds moved there; still reached as ui.<name>
    FILTERS, IMAGE_TYPES, KINDS, kind_of, looks_like_json)

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
PROJECT_URL = appbundle.PROJECT_URL
OWNER = appbundle.OWNER


def e(value):
    return html.escape("" if value is None else str(value), quote=True)


def asset(name):
    with open(os.path.join(ASSETS, name), encoding="utf-8") as f:
        return f.read()


# --- icons: the app's sprite (assets/app/icons.svg); each icon is a <use> of it ------------------

def sprite():
    # The summary page allows inline styles; the app hides the sprite with its `sprite` class.
    return appbundle.icons().replace('class="sprite"', 'style="position:absolute"', 1)


def icon(name, cls=""):
    return f'<svg class="ic{" " + cls if cls else ""}" aria-hidden="true"><use href="#i-{name}"/></svg>'


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


def file_node(anchor, path, kind, lang, ic, size, meta, content, version=None, size_bytes=None):
    """One file of the explorer. Without the script it opens in place, labelled with its full path;
    with it, it opens in the viewer. `version` (a served page) changes when the file does, and
    `size_bytes` lets the viewer ask before loading a very large file."""
    label = f'<code>{e(path)}</code> <span class="muted small">{e(" · ".join(x for x in (size, meta) if x))}</span>'
    ver = (f' data-version="{e(version)}"' if version else "") + \
        (f' data-bytes="{int(size_bytes)}"' if size_bytes is not None else "")
    return (f'<details class="file" id="{e(anchor)}" data-kind="{e(kind)}" data-lang="{e(lang)}" '
            f'data-icon="{e(ic)}" data-path="{e(path)}" data-size="{e(size)}" data-meta="{e(meta)}"'
            f'{ver}>'
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
    """One page of the dashboard; the sidebar shows one at a time. `data-hash` is a digest of the
    view's content: a served page replaces only the views whose digest changed."""
    inner = (f'<div class="view-head"><div class="title"><h2 id="h-{e(vid)}">{e(title)} {badge}</h2>'
             + (f'<div class="sub">{sub}</div>' if sub else "") + f'</div></div>{body}')
    digest = hashlib.sha1(inner.encode("utf-8")).hexdigest()[:16]
    return (f'<section class="view" id="{e(vid)}" data-title="{e(title)}" data-hash="{digest}" '
            f'aria-labelledby="h-{e(vid)}">{inner}</section>')


def nav_link(vid, label, ic, extra=""):
    return f'<a href="#{e(vid)}" data-view="{e(vid)}">{icon(ic)}{e(label)}{extra}</a>'


def nav_count(n):
    return f'<span class="count">{e(n)}</span>'


def nav_dot(tone, title):
    return f'<span class="dot tone-{e(tone)}" title="{e(title)}"></span>'


def sidebar(workspace, kind, groups, generated, version, workspaces=None):
    """`groups` are `(title, [nav_link html])`. `workspaces`: the names a served page can switch
    to (the current one among them)."""
    nav = "".join(f'<div class="group">{e(title)}</div>{"".join(links)}' for title, links in groups)
    switch = ""
    if workspaces and len(workspaces) > 1:
        options = "".join(f'<option value="{e(name)}"{" selected" if name == workspace else ""}>'
                          f'{e(name)}</option>' for name in workspaces)
        switch = (f'<label class="ws-switch"><span class="sr-only">Workspace</span><select '
                  f'class="input" data-action="workspace">{options}</select></label>')
    return (f'<aside class="sidebar" aria-label="Dashboard"><div class="brand"><span class="name">'
            f'<span class="logo" aria-hidden="true">d</span>devloops</span><span class="ws">workspace '
            f'<strong>{e(workspace)}</strong> · {e(kind)}</span>{switch}</div>'
            f'<button class="search" type="button" data-action="palette">{icon("search")}Go to…'
            f'<kbd>Ctrl K</kbd></button><nav class="nav" aria-label="Sections">{nav}</nav>'
            f'<div class="foot"><span data-generated>Generated {e(generated)}</span>'
            f'<a class="gh" href="{e(PROJECT_URL)}" target="_blank" rel="noopener noreferrer">'
            f'{icon("github")}<span>devloops {e(version)} · by {e(OWNER)}</span></a></div></aside>')


def topbar(workspace, status, live=False):
    """`live`: a served page that follows the run as it goes; a button pauses it."""
    live_btn = ('<button class="btn live" type="button" data-action="live" aria-pressed="true" '
                'title="This page follows the run as it goes. Select to pause.">'
                '<span class="pulse" aria-hidden="true"></span><span data-live-label>Live</span>'
                '</button>' if live else "")
    return (f'<header class="topbar"><button class="btn icon ghost menu-btn" type="button" '
            f'data-action="menu" aria-label="Menu">{icon("menu")}</button><div class="crumbs">'
            f'{e(workspace)} <span aria-hidden="true">/</span><strong data-crumb>Overview</strong></div>'
            f'<span class="spacer"></span>{live_btn}<span data-status>{status}</span>'
            f'<button class="btn icon" type="button" '
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


def page(title, side, top, views, attrs=None):
    """A complete page: the inline styles, the shell, `views`, the dialogs, and the one script.
    `attrs`: `data-*` attributes of the root element (a served page's, see serve.py)."""
    attr = "".join(f" data-{k}='{e(v)}'" for k, v in (attrs or {}).items())
    return (f"<!doctype html><html lang='en' class='no-js'{attr}><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<title>{e(title)}</title><style>{asset('dashboard.css')}</style></head><body>"
            f"{sprite()}<div class='app'>{side}<main class='content'>{top}{''.join(views)}</main>"
            f"</div>{DIALOGS}<div id='tip' role='tooltip'></div>"
            f"<script>{asset('dashboard.js')}</script></body></html>\n")
