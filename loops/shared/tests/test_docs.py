"""The documentation site stays true to the code (specs/006-docs-site contracts/docs-tests.md).

1. The generated reference pages are current (`tools/docs/gen_reference.py --check`).
2. `tools/docs/descriptions.json` describes exactly the values the code has.
3. Every hand-written page has `title`, `description` and `sources`, and each source exists.
4. Commands, options, configuration keys and workspace paths named in the pages exist.
5. Every status of each kind appears in that kind's diagram on the statuses page.
6. The example outputs are current (`tools/docs/examples.py --check`).
7. The site builds with `zensical build --strict` (broken links, anchors and snippets fail it,
   research R-2). Zensical is a writers' and CI tool, not a devloops dependency: the check is
   skipped when it is not installed, as the node tests are without node; CI always runs it.

Every failure names the page (and line) and the item.
"""
import argparse
import glob
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

import helpers

ROOT = helpers.REPO_ROOT
DOCS = os.path.join(ROOT, "docs")
TOOLS = os.path.join(ROOT, "tools", "docs")


def tool(name):
    """A script of `tools/docs/` as a module (it is not a package)."""
    spec = importlib.util.spec_from_file_location(name, os.path.join(TOOLS, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_tool(name, *args):
    return subprocess.run([sys.executable, os.path.join(TOOLS, name + ".py"), *args], cwd=ROOT,
                          capture_output=True, text=True, timeout=600)


def zensical():
    """The `zensical` command: on PATH, or in the checkout's `.venv-docs` (docs quickstart)."""
    found = shutil.which("zensical")
    local = os.path.join(ROOT, ".venv-docs", "bin", "zensical")
    return found or (local if os.access(local, os.X_OK) else None)


# --- front matter: the YAML subset the pages use (contracts/page-front-matter.md) -------------

def _scalar(text):
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    if text.startswith("[") and text.endswith("]"):
        return [_scalar(item) for item in text[1:-1].split(",") if item.strip()]
    if text in ("true", "false"):
        return text == "true"
    return text


def front_matter(text):
    """`(data, body_start_line)` from a page's leading `---` block: `key: value`, `key: >-` (or
    `>`, `|`) with indented lines, `key:` followed by `- item` lines, and `[a, b]` lists.
    `({}, 1)` when the page has none."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, 1
    try:
        end = lines.index("---", 1)
    except ValueError:
        raise ValueError("front matter is not closed with ---")
    data, key, block = {}, None, None
    for raw in lines[1:end]:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw[0] in " \t":
            if key is None:
                raise ValueError(f"indented line outside a key: {raw!r}")
            item = raw.strip()
            if block is not None:
                block.append(item)
                data[key] = " ".join(block)
            elif item.startswith("- "):
                data.setdefault(key, [])
                data[key].append(_scalar(item[2:]))
            else:
                raise ValueError(f"unexpected line under {key}: {raw!r}")
            continue
        name, sep, value = raw.partition(":")
        if not sep:
            raise ValueError(f"not a key: {raw!r}")
        key, value = name.strip(), value.strip()
        block = [] if value in (">-", ">", "|", "|-") else None
        data[key] = "" if block is not None else (_scalar(value) if value else [])
    return data, end + 2


def pages():
    """Every `docs/**/*.md` as `(path relative to docs/, front matter, text)`, sorted."""
    for path in sorted(glob.glob(os.path.join(DOCS, "**", "*.md"), recursive=True)):
        with open(path, encoding="utf-8") as f:
            text = f.read()
        yield os.path.relpath(path, DOCS).replace(os.sep, "/"), front_matter(text)[0], text


def hand_written():
    """The pages a writer wrote (not `generated: true`), as `pages()` yields them."""
    return [(rel, data, text) for rel, data, text in pages() if not data.get("generated")]


def code_spans(text):
    """`(line number, text)` for each inline code span outside fences, and each line inside a
    fenced code block."""
    found, fence = [], None
    for number, line in enumerate(text.split("\n"), 1):
        stripped = line.strip()
        marker = re.match(r"(`{3,}|~{3,})", stripped)
        if marker and (fence is None or stripped.startswith(fence)):
            fence = None if fence else marker.group(1)
            continue
        if fence:
            found.append((number, stripped))
        else:
            found += [(number, span) for span in re.findall(r"`([^`\n]+)`", line)]
    return found


class ReferencePagesTest(unittest.TestCase):
    def test_1_the_reference_pages_are_current(self):
        proc = run_tool("gen_reference", "--check")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_2_descriptions_match_the_code(self):
        values = tool("gen_reference").code_values()
        with open(os.path.join(TOOLS, "descriptions.json"), encoding="utf-8") as f:
            described = json.load(f)
        problems = []

        def compare(group, code, desc):
            problems.extend(f"{group}: add a description for {v!r}" for v in code if v not in desc)
            problems.extend(f"{group}: {k!r} no longer exists" for k in desc if k not in code)

        for group, code in values.items():
            if isinstance(code, dict):
                compare(group, code, described.get(group, {}))
                for kind, kind_values in code.items():
                    compare(f"{group}.{kind}", kind_values, described.get(group, {}).get(kind, {}))
            else:
                compare(group, code, described.get(group, {}))
        self.assertEqual(problems, [], "tools/docs/descriptions.json")


class HandWrittenPagesTest(unittest.TestCase):
    def test_3_front_matter_and_sources(self):
        problems = []
        for rel, data, _ in hand_written():
            for key in ("title", "description"):
                if not isinstance(data.get(key), str) or not data[key].strip():
                    problems.append(f"docs/{rel}: no {key}")
            sources = data.get("sources")
            if not isinstance(sources, list) or not sources:
                problems.append(f"docs/{rel}: no sources")
                continue
            for source in sources:
                problem = source_problem(source)
                if problem:
                    problems.append(f"docs/{rel}: source {source!r}: {problem}")
        self.assertEqual(problems, [])

    def test_4_commands_options_keys_and_paths_exist(self):
        commands, keys, files = known_commands(), config_keys(), workspace_patterns()
        problems = []
        for rel, _, text in hand_written():
            for number, span in code_spans(text):
                for problem in (command_problem(span, commands), key_problem(span, keys),
                                path_problem(span, files)):
                    if problem:
                        problems.append(f"docs/{rel}:{number}: {problem}")
        self.assertEqual(problems, [])

    def test_6_the_examples_are_current(self):
        proc = run_tool("examples", "--check")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


class GlossaryTest(unittest.TestCase):
    def test_every_hover_definition_has_a_glossary_entry_and_the_reverse(self):
        """FR-015: the glossary's terms show on hover everywhere (`abbreviations.md`)."""
        with open(os.path.join(ROOT, "docs-include", "abbreviations.md"), encoding="utf-8") as f:
            hover = re.findall(r"^\*\[([^\]]+)\]: \S", f.read(), re.M)
        with open(os.path.join(DOCS, "glossary.md"), encoding="utf-8") as f:
            entries = re.findall(r"^## (.+?) \{#([a-z0-9-]+)\}$", f.read(), re.M)
        self.assertEqual(sorted(hover), sorted(term for term, _ in entries))
        for term, anchor in entries:
            self.assertEqual(anchor, term.lower().replace(" ", "-"), term)


# --- check 3: sources ---------------------------------------------------------------------------

def source_problem(source):
    """Why a `sources` entry is wrong, or None: a repository path that exists, or
    `spec NNN <ID>` found in `specs/NNN-*/spec.md` (or `research.md` for `R-n`)."""
    match = re.fullmatch(r"spec (\d{3}) (\S+)", source)
    if not match:
        return None if os.path.exists(os.path.join(ROOT, source)) else "no such file or folder"
    folders = glob.glob(os.path.join(ROOT, "specs", match.group(1) + "-*"))
    if not folders:
        return "no such spec"
    name = "research.md" if match.group(2).startswith("R-") else "spec.md"
    try:
        with open(os.path.join(folders[0], name), encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return f"the spec has no {name}"
    if not re.search(rf"(?<![\w-]){re.escape(match.group(2))}(?![\w-])", text):
        return f"{match.group(2)} is not in {os.path.basename(folders[0])}/{name}"
    return None


# --- check 4: commands, keys and paths ----------------------------------------------------------

def known_commands():
    """`{command: {option, ...}}` from the parser; `""` holds the global options."""
    from devloops import cli
    parser = cli.build_parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    found = {"": {o for a in parser._actions for o in a.option_strings}}
    for name, command in sub.choices.items():
        found[name] = {o for a in command._actions for o in a.option_strings
                       if a.help != argparse.SUPPRESS}
    return found


def command_problem(span, commands):
    line = span[2:] if span.startswith("$ ") else span
    if not line.startswith("devloops "):
        return None
    try:
        words = shlex.split(line.split(" #")[0])
    except ValueError:
        words = line.split()
    rest = words[1:]
    command = next((w for w in rest if not w.startswith("-")), None)
    if command is None or command.startswith("<"):
        options = {w.split("=")[0] for w in rest if w.startswith("-")}
        unknown = sorted(o for o in options if o not in commands[""])
        return f"{line!r}: unknown option {unknown[0]}" if unknown else None
    if command not in commands:
        return f"{line!r}: unknown command {command!r}"
    for word in rest:
        if word.startswith("-") and word.split("=")[0] not in commands[command] | commands[""]:
            return f"{line!r}: {command} has no option {word.split('=')[0]}"
    return None


def config_keys():
    """Every dotted key of both configuration schemas."""
    from devloops import schema

    def walk(node, prefix):
        for key, child in node.get("properties", {}).items():
            yield prefix + key
            yield from walk(child, prefix + key + ".")

    keys = set()
    for name in ("config.schema.json", "project-config.schema.json"):
        keys |= set(walk(schema.load(name), ""))
    return keys


FILE_NAME = re.compile(r"\.(json|jsonl|md|py|txt|html|log|toml|yml|yaml|js|css|mjs)$")


def key_problem(span, keys):
    """A dotted name whose first part is a top-level key (`unit_tests.command`) must be a key."""
    match = re.fullmatch(r"([a-z_]+)((?:\.[a-z_-]+)+)", span)
    if not match or FILE_NAME.search(span) or match.group(1) not in {k.split(".")[0] for k in keys}:
        return None
    return None if span in keys else f"{span!r} is not a configuration key"


def workspace_patterns():
    """The general names of the files a run writes (`<loop>/state/run.json`, ...)."""
    return tool("gen_reference").workspace_files()


WORKSPACE_PATH = re.compile(r"(state|outputs|run|exports|<loop>|backend-dev|frontend-dev)/\S*"
                            r"|(progress|task)\.md")


def path_problem(span, files):
    """A workspace path must be a file the sample run wrote, or a folder holding one."""
    if not WORKSPACE_PATH.fullmatch(span):
        return None
    general = tool_general(span)
    if general.startswith(("state/", "outputs/")) or general in ("progress.md", "task.md"):
        general = "<loop>/" + general
    folder = general.rstrip("/") + "/"
    if general in files or any(f.startswith(folder) for f in files):
        return None
    return f"{span!r} is not a file a run writes (docs-include/examples/workspace-files.txt)"


_GENERAL = []


def tool_general(path):
    if not _GENERAL:
        _GENERAL.append(tool("gen_reference").general_name)
    return _GENERAL[0](path)


class FrontMatterReaderTest(unittest.TestCase):
    def test_reads_the_forms_pages_use(self):
        data, start = front_matter("---\ntitle: How a run works\ndescription: >-\n  From a: b\n"
                                   "  to c.\nsources:\n  - loops/x.py\n  - \"spec 001 FR-012\"\n"
                                   "tags: [a, b]\ngenerated: true\n---\n\n# Body\n")
        self.assertEqual(data, {"title": "How a run works", "description": "From a: b to c.",
                                "sources": ["loops/x.py", "spec 001 FR-012"],
                                "tags": ["a", "b"], "generated": True})
        self.assertEqual(start, 12)
        self.assertEqual(front_matter("# No front matter\n"), ({}, 1))


# --- statuses the code writes (research R-5) ---------------------------------------------------

STATUS_MODULES = ("engine.py", "orchestrator.py", "selector.py")
_LITERAL = re.compile(r'(\.get\()?"([^"]*)"(\s*[\]:])?')


def _values(text):
    """The string literals in `text` that are values: not a subscript, a key, or a `.get` key."""
    return [m.group(2) for m in _LITERAL.finditer(text) if not (m.group(1) or m.group(3))]
_STATUS_LINE = [
    re.compile(r'\[["\']status["\']\]\s*(?:=|==|!=)\s*(.*)'),          # x["status"] = / == "v"
    re.compile(r'\bstatus=("[^"]*")'),                                    # x.update(status="v")
    re.compile(r'["\']status["\']:\s*("[^"]*")'),                          # {"status": "v"}
    re.compile(r'\[["\']status["\']\]\s+(?:not\s+)?in\s+(\([^)]*\))'),     # x["status"] in (...)
    re.compile(r'\[["\']tasks["\']\](?:\[[^\]]+\]|\.get\([^)]*\))?\s*(?:=|==|!=)\s*(.*)'),
]


def written_statuses():
    """`[(module, line, value)]` for every status literal the run code writes or compares."""
    found = []
    for name in STATUS_MODULES:
        with open(os.path.join(helpers.SHARED_DIR, "devloops", name), encoding="utf-8") as f:
            for number, line in enumerate(f, 1):
                for pattern in _STATUS_LINE:
                    for match in pattern.finditer(line):
                        for value in _values(match.group(1)):
                            found.append((name, number, value))
    return found


class StatusConstantsTest(unittest.TestCase):
    """The status constants hold exactly what the code writes (T006): the reference pages and
    the status diagrams are drawn from them."""

    def test_the_code_writes_no_status_outside_the_constants(self):
        from devloops import schema, state
        loop = schema.load("run-state.schema.json")["properties"]["status"]["enum"]
        # Also written: "not-started" (a loop, or a run's step, with no run yet) and the
        # planning phase's "done"; both are shown as such, not as statuses of their own.
        known = set(state.RUN_STATUSES + state.MILESTONE_STATUSES + state.TASK_STATUSES
                    + state.TRIAL_STATUSES) | set(loop) | {"not-started", "done"}
        unknown = [f"{m}:{n}: {v!r}" for m, n, v in written_statuses() if v not in known]
        self.assertEqual(unknown, [], "a status the constants in state.py do not list")

    def test_every_constant_is_written_by_the_code(self):
        from devloops import state
        written = {v for _, _, v in written_statuses()}
        for kind in ("RUN_STATUSES", "MILESTONE_STATUSES", "TASK_STATUSES", "TRIAL_STATUSES"):
            for value in getattr(state, kind):
                self.assertIn(value, written, f"state.{kind} lists {value!r}, which no code writes")


def status_diagrams(path):
    """`{kind: text of the first mermaid block}` per `## … {#kind}` section of `path`."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    diagrams = {}
    for match in re.finditer(r"^## [^\n]*\{#([\w-]+)\}\n(.*?)(?=^## |\Z)", text, re.M | re.S):
        block = re.search(r"^```mermaid\n(.*?)^```", match.group(2), re.M | re.S)
        if block:
            diagrams[match.group(1)] = block.group(1)
    return diagrams


class StatusDiagramsTest(unittest.TestCase):
    """Check 5: each status of each kind (the constants of state.py and the schema enums, as the
    reference shows them) appears in that kind's diagram on how-it-works/statuses.md (FR-008)."""

    def test_5_every_status_is_in_its_kinds_diagram(self):
        page = os.path.join(DOCS, "how-it-works", "statuses.md")
        diagrams = status_diagrams(page)
        missing = []
        for kind, values in tool("gen_reference").code_values()["statuses"].items():
            if kind not in diagrams:
                missing.append(f"{kind}: no diagram (a `## … {{#{kind}}}` section with a "
                               "mermaid block)")
                continue
            missing.extend(f"{kind}: {value!r} is not in its diagram" for value in values
                           if not re.search(rf"(?<![\w-]){re.escape(value)}(?![\w-])",
                                            diagrams[kind]))
        self.assertEqual(missing, [], os.path.relpath(page, ROOT))

    def test_the_diagram_reader(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = os.path.join(tmp, "statuses.md")
            with open(page, "w", encoding="utf-8") as f:
                f.write("## Task {#task}\n\n```mermaid\nstateDiagram-v2\n  [*] --> pending\n"
                        "```\n\n## Other\n\n```mermaid\nfailed\n```\n")
            self.assertEqual(status_diagrams(page),
                             {"task": "stateDiagram-v2\n  [*] --> pending\n"})


class RevisionDatesTest(unittest.TestCase):
    """`tools/docs/revision_dates.py` (run in CI before the build) stamps the front matter."""

    def test_stamps_once_and_replaces_an_earlier_date(self):
        import datetime
        stamp = tool("revision_dates").stamp
        page = "---\ntitle: T\n---\n\n# T\n"
        once = stamp(page, datetime.date(2026, 10, 1))
        self.assertEqual(once, "---\nrevision_date: 'Last updated: 1 October 2026'\ntitle: T\n"
                               "---\n\n# T\n")
        self.assertEqual(front_matter(once)[0]["title"], "T")
        again = stamp(once, datetime.date(2026, 10, 11))
        self.assertEqual(again.count("revision_date"), 1)
        self.assertIn("11 October 2026", again)
        self.assertEqual(stamp("# no front matter\n", datetime.date(2026, 10, 1)),
                         "# no front matter\n")


class StopReasonsTest(unittest.TestCase):
    """Every stop reason the driver raises is one the run state's schema lists, so the reference
    describes it and a stopped `run.json` stays valid."""

    RAISED = re.compile(r'(?:StopRun\(\s*"stopped-on-[a-z-]+",\s*|input_error\(\s*)"([a-z-]+)"')

    # Raised before any loop's run state exists (choosing the loops; `init`): never recorded.
    NEVER_RECORDED = {"no-loop", "frontend-needs-backend", "settings-unreadable"}

    def test_every_raised_stop_reason_is_in_the_schema(self):
        from devloops import schema
        codes = set(schema.load("run-state.schema.json")["properties"]["status_reason"][
            "properties"]["code"]["enum"]) | self.NEVER_RECORDED
        raised = []
        for path in sorted(glob.glob(os.path.join(ROOT, "loops", "shared", "devloops", "**",
                                                  "*.py"), recursive=True)):
            with open(path, encoding="utf-8") as f:
                raised += [(os.path.relpath(path, ROOT), c) for c in self.RAISED.findall(f.read())]
        self.assertTrue(raised)
        self.assertEqual([f"{p}: {c!r}" for p, c in raised if c not in codes], [],
                         "stop reasons the run-state schema does not list")


@unittest.skipUnless(zensical(),"needs zensical (pip install -r tools/docs/requirements.txt)")
class SiteBuildTest(unittest.TestCase):
    """Check 7: Zensical has no output-folder option, so this writes the git-ignored `site/`."""

    def test_the_site_builds_strictly(self):
        proc = subprocess.run([zensical(), "build", "--strict", "--clean"], cwd=ROOT,
                              capture_output=True, text=True, timeout=300)
        output = re.sub(r"\x1b\[[0-9;]*m", "", proc.stdout + proc.stderr)
        self.assertEqual(proc.returncode, 0, "zensical build --strict failed:\n" + output)


if __name__ == "__main__":
    unittest.main()
