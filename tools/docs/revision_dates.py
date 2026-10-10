#!/usr/bin/env python3
"""Stamp each page with the date its file last changed, for the site's "last updated" line.

    python3 tools/docs/revision_dates.py   # in CI, before `zensical build` (needs the git history)

The theme shows a page's `revision_date` front matter at the foot of the page. This script sets
it, in every page under `docs/`, to the date of the last commit that changed that page's file
(`git log`), as "Last updated: 11 October 2026". A page git does not know yet gets today's date.

It edits the pages in place, so it runs on the CI checkout before the build (after the tests),
never on a working copy: the dates are not committed (they would change with every commit). CI
checks out the whole history (`fetch-depth: 0`); a shallow clone would give every page the last
commit's date.
"""
import datetime
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOCS = os.path.join(ROOT, "docs")
FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def human(date):
    return f"{date.day} {date:%B %Y}"


def last_changed(path):
    """The date of the last commit that changed `path`, or None if git does not know it."""
    out = subprocess.run(["git", "log", "-1", "--format=%cs", "--", path], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout.strip()
    return datetime.date.fromisoformat(out) if out else None


def stamp(text, date):
    """`text` with `revision_date: <date>` in its front matter (replacing an earlier one)."""
    match = FRONT_MATTER.match(text)
    if not match:
        return text
    lines = [line for line in match.group(1).split("\n") if not line.startswith("revision_date:")]
    lines.insert(0, f"revision_date: 'Last updated: {human(date)}'")
    return "---\n" + "\n".join(lines) + "\n---\n" + text[match.end():]


def main():
    today = datetime.date.today()
    count = 0
    for directory, _, names in os.walk(DOCS):
        for name in sorted(names):
            if not name.endswith(".md"):
                continue
            path = os.path.join(directory, name)
            with open(path, encoding="utf-8") as f:
                text = f.read()
            new = stamp(text, last_changed(path) or today)
            if new != text:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(new)
                count += 1
    print(f"stamped {count} page(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
