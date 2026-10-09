"""The dashboard app's files (assets/app/), as the server sends them and the export inlines them.

The app is plain JavaScript with no build step (specs/005-dashboard-redesign research R-1): each
file listed in `assets/app/scripts.txt` adds itself to one global (`DL`), and the files are joined
in the listed order into one script. The shell (`index.html`) holds the page's frame; `shell()`
fills its `{{…}}` placeholders, linking the script and the stylesheet (served) or inlining them
(the export).
"""
import functools
import hashlib
import html
import os
import re

from . import __version__

APP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "app")
SEPARATOR = "\n;\n"  # a file that ends without a semicolon cannot run into the next one
PROJECT_URL = "https://github.com/youssef7ussien/claude-devloops"
OWNER = "youssef7ussien"
PLACEHOLDER = re.compile(r"\{\{(title|attrs|styles|scripts|icons|version|project_url|owner)\}\}")


def _read(name):
    with open(os.path.join(APP, name), encoding="utf-8") as f:
        return f.read()


def script_names():
    """The listed scripts, in join order."""
    names = []
    for line in _read("scripts.txt").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            names.append(line)
    return names


@functools.lru_cache(maxsize=None)
def script():
    """The listed files joined into one script (read once)."""
    return SEPARATOR.join(_read(name) for name in script_names()) + "\n"


@functools.lru_cache(maxsize=None)
def stylesheet():
    return _read("app.css")


@functools.lru_cache(maxsize=None)
def icons():
    return _read("icons.svg").strip()


@functools.lru_cache(maxsize=None)
def assets_version():
    """The devloops version and a digest of the script and stylesheet: the assets' URLs carry it,
    so a browser keeps them until they change."""
    digest = hashlib.sha1((script() + stylesheet()).encode("utf-8")).hexdigest()[:10]
    return f"{__version__}-{digest}"


def _attrs(attrs):
    return "".join(f' data-{k}="{html.escape(str(v), quote=True)}"'
                   for k, v in (attrs or {}).items() if v is not None)


def shell(title, attrs=None, inline=False, data=""):
    """The app's page.

    `attrs` are the root element's `data-*` attributes (HTML-escaped). Served, the page links
    `/assets/app.css` and `/assets/app.js`; `inline` (the export) puts both in the page, with
    `data` (the embedded `<script type="application/json">` elements) before the script."""
    if inline:
        styles = f"<style>{stylesheet()}</style>"
        # Inside a script element, `</script` would end it; `<\/` reads the same in JavaScript.
        scripts = f"{data}<script>{script().replace('</', '<' + chr(92) + '/')}</script>"
    else:
        v = html.escape(assets_version(), quote=True)
        styles = f'<link rel="stylesheet" href="/assets/app.css?v={v}">'
        scripts = f'{data}<script src="/assets/app.js?v={v}" defer></script>'
    values = {"title": html.escape(title), "attrs": _attrs(attrs), "styles": styles,
              "scripts": scripts, "icons": icons(), "version": html.escape(__version__),
              "project_url": html.escape(PROJECT_URL, quote=True), "owner": html.escape(OWNER)}
    # One pass, so a placeholder-like text inside the script or the styles is left alone.
    return PLACEHOLDER.sub(lambda m: values[m.group(1)], _read("index.html"))
