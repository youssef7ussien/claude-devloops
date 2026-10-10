#!/usr/bin/env python3
"""Write the documentation's reference pages from devloops' code (spec 006 FR-017, R-5).

    python3 tools/docs/gen_reference.py           # rewrite docs/reference/<page>.md
    python3 tools/docs/gen_reference.py --check   # write nothing; exit 1 naming each differing page

What the code holds is read from it: the commands and options (`cli.build_parser()`), the
configuration keys (the two schemas), the exit codes, the steps (`claude.STEPS`), the statuses
(the constants in `state.py` and the schema enums) and the files a run writes (the sample run's
`docs-include/examples/workspace-files.txt`). What it does not hold, the meaning of a value, is
in `tools/docs/descriptions.json`; `code_values()` is what test_docs compares it with. Standard
library only, and the same code always gives the same bytes. The anchors are explicit
(data-model.md, "Reference entry"), so pages can link to an entry whatever its wording.
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SHARED = os.path.join(ROOT, "loops", "shared")
REFERENCE = os.path.join(ROOT, "docs", "reference")
DESCRIPTIONS = os.path.join(ROOT, "tools", "docs", "descriptions.json")
WORKSPACE_FILES = os.path.join(ROOT, "docs-include", "examples", "workspace-files.txt")
sys.path.insert(0, SHARED)

from devloops import claude, cli, config, schema, state  # noqa: E402
from devloops import initcmd, project  # noqa: E402,F401  (their error classes set exit codes)

NOTE = ("!!! note \"Generated page\"\n"
        "    This page is generated from devloops' code; do not edit it. Change the code (or\n"
        "    `tools/docs/descriptions.json`), then run `python3 tools/docs/gen_reference.py`.\n")

INTERRUPTED = 130  # cli.main returns it on Ctrl+C (KeyboardInterrupt)

# The order a run meets the steps in; `claude.STEPS` is keyed by name in no particular order.
STEP_ORDER = ("plan", "replan", "author-checks", "implement", "fix", "validate-ui")

# Files with a schema: the reference also lists their fields, from the schema.
FILE_SCHEMAS = {
    "<loop>/state/run.json": "run-state.schema.json",
    "<loop>/state/plan.json": "plan.schema.json",
    "<loop>/state/invocations.jsonl": "invocation-record.schema.json",
    "<loop>/state/milestones/<id>/checks.json": "checks.schema.json",
    "<loop>/state/milestones/<id>/trials/<n>/validation.json": "validation-result.schema.json",
}

# A file the sample run wrote -> its general name, with placeholders (test_docs check 4 too).
_GENERAL = [
    (r"^(backend-dev|frontend-dev)/", "<loop>/"),
    (r"/milestones/M\d+/", "/milestones/<id>/"),
    (r"/trials/\d+/", "/trials/<n>/"),
    (r"/(conversations|prompts)/\d{4}-[a-z-]+\.", r"/\1/<seq>-<step>."),
    (r"/evidence/C\d+\.", "/evidence/<check>."),
    (r"/milestone-\d+-[a-z0-9-]+\.md$", "/milestone-<NN>-<slug>.md"),
    (r"^exports/\d{8}T\d{6}Z\.html$", "exports/<stamp>.html"),
]


def general_name(path):
    for pattern, replacement in _GENERAL:
        path = re.sub(pattern, replacement, path)
    return path


def workspace_files():
    """The general names of the files the sample run wrote, sorted, without repeats."""
    with open(WORKSPACE_FILES, encoding="utf-8") as f:
        return sorted({general_name(line.strip()) for line in f if line.strip()})


def descriptions():
    with open(DESCRIPTIONS, encoding="utf-8") as f:
        return json.load(f)


# --- the values the code holds (test_docs check 2) --------------------------------------------

def _error_codes(cls=state.DevloopsError):
    codes = {cls.exit_code} if isinstance(getattr(cls, "exit_code", None), int) else set()
    for sub in cls.__subclasses__():
        codes |= _error_codes(sub)
    return codes


def exit_codes():
    return sorted(set(state.EXIT_CODES.values()) | {state.EXIT_USAGE, state.EXIT_LOCK_HELD,
                                                     INTERRUPTED} | _error_codes())


def _run_state():
    return schema.load("run-state.schema.json")["properties"]


def code_values():
    """`{group: [values]}` for each group of descriptions.json, from the code."""
    run_state = _run_state()
    return {
        "exit_codes": [str(c) for c in exit_codes()],
        "steps": list(claude.STEPS),
        "statuses": {
            "run": list(state.RUN_STATUSES),
            # "not-started": a loop with no run yet (engine.status_object)
            "loop": ["not-started"] + run_state["status"]["enum"],
            "milestone": list(state.MILESTONE_STATUSES),
            "task": list(state.TASK_STATUSES),
            "trial": list(state.TRIAL_STATUSES),
            "approval": run_state["approval"]["properties"]["action"]["enum"],
        },
        "stop_reasons": run_state["status_reason"]["properties"]["code"]["enum"],
        "files": workspace_files(),
    }


# --- Markdown helpers ---------------------------------------------------------------------------

def cell(text):
    return " ".join(str(text).split()).replace("|", "\\|")


def sentence(text):
    """`text` as a sentence: a capital (unless it starts with a name such as `backend-dev`'s, an
    option, or a JSON value such as `true`) and a full stop."""
    text = " ".join(text.split())
    if not text:
        return ""
    first = text.split()[0]
    if first.isalpha() and first.islower() and first not in ("true", "false", "null"):
        text = text[0].upper() + text[1:]
    return text if text.endswith(".") else text + "."


def page(title, description, body):
    return (f"---\ntitle: {title}\ndescription: >-\n  {description}\ngenerated: true\n---\n\n"
            f"# {title}\n\n{NOTE}\n{body.rstrip()}\n")


def anchor(text):
    """An anchor from a name: `<loop>/state/run.json` -> `loop-state-run.json`."""
    return re.sub(r"[^a-z0-9._-]+", "-", re.sub(r"[<>]", "", text.lower())).strip("-")


# --- commands -------------------------------------------------------------------------------------

def _option_name(action):
    if action.option_strings:
        name = max(action.option_strings, key=len)
        if action.nargs == 0:
            return name
        metavar = action.metavar or action.dest.upper()
        return f"{name} [{metavar}]" if action.nargs == "?" else f"{name} {metavar}"
    return action.metavar or action.dest


def _default(action):
    if action.default in (None, False, argparse.SUPPRESS) or action.nargs == 0:
        return ""
    return f"`{action.default}`"


def _help(action):
    text = action.help or ""
    if action.choices and not action.option_strings:
        text = (text + "; " if text else "") + "one of " + ", ".join(
            f"`{c}`" for c in action.choices)
    if action.required:
        text = "required: " + text
    return sentence(text)


def _usage(name, command):
    """`devloops <name> [options]`, built here rather than by argparse, whose layout changes
    between Python versions: options in order, exclusive ones as `[a | b]`, wrapped at 100."""
    groups = {id(a): g for g in command._mutually_exclusive_groups for a in g._group_actions}
    parts, seen = [], set()
    for action in command._actions:
        if action.help == argparse.SUPPRESS or isinstance(action, argparse._HelpAction):
            continue
        group = groups.get(id(action))
        if group is not None:
            if id(group) in seen:
                continue
            seen.add(id(group))
            members = [_option_name(a) for a in group._group_actions
                       if a.help != argparse.SUPPRESS]
            parts.append("[" + " | ".join(members) + "]")
        elif action.option_strings:
            parts.append(_option_name(action) if action.required else f"[{_option_name(action)}]")
        else:
            parts.append(f"[{action.dest}]" if action.nargs == "?" else action.dest)
    prefix = f"devloops {name} "
    lines, line = [], prefix
    for part in parts:
        if len(line) + len(part) > 100 and line.strip() != prefix.strip():
            lines.append(line.rstrip())
            line = " " * len(prefix)
        line += part + " "
    return "\n".join(lines + [line.rstrip()])


def commands_page():
    parser = cli.build_parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    helps = {a.dest: a.help for a in sub._choices_actions}
    lines = ["Every command is `devloops <command> [options]`. `devloops --help` lists the "
             "commands and `devloops <command> --help` a command's options.", "",
             "## Global options {#global-options}", "",
             "| Option | Meaning |", "|---|---|"]
    for action in parser._actions:
        if action.option_strings and action.help != argparse.SUPPRESS:
            flag = max(action.option_strings, key=len).lstrip("-")
            lines.append(f"| <span id=\"devloops--{flag}\">"
                         f"</span>`{_option_name(action)}` | {cell(_help(action))} |")
    for name, command in sub.choices.items():
        lines += ["", f"## `{name}` {{#{name}}}", "", sentence(helps.get(name) or ""), "",
                  "```text", _usage(name, command), "```", ""]
        actions = [a for a in command._actions
                   if a.help != argparse.SUPPRESS and not isinstance(a, argparse._HelpAction)]
        if actions:
            lines += ["| Option | Default | Meaning |", "|---|---|---|"]
            for action in actions:
                key = max(action.option_strings, key=len) if action.option_strings \
                    else action.dest
                lines.append(f"| <span id=\"{name}--{anchor(key.lstrip('-'))}\"></span>"
                             f"`{_option_name(action)}` | {_default(action)} | "
                             f"{cell(_help(action))} |")
        groups = [g for g in command._mutually_exclusive_groups
                  if any(a.help != argparse.SUPPRESS for a in g._group_actions)]
        if groups:
            lines += ["", "Options that cannot be used together:", ""]
            for group in groups:
                names = [max(a.option_strings, key=len) for a in group._group_actions
                         if a.help != argparse.SUPPRESS]
                lines.append("- " + " or ".join(f"`{n}`" for n in names))
    removed = getattr(cli, "REMOVED_DASHBOARD_FLAGS", None)
    if removed:
        lines += ["", "## Removed options {#removed-options}", "",
                  "`devloops dashboard` stops with an error naming what replaced these options:",
                  "", "| Option | Instead |", "|---|---|"]
        for flag, instead in removed.items():
            lines.append(f"| <span id=\"dashboard--{anchor(flag.lstrip('-'))}\"></span>"
                         f"`{flag}` | {cell(sentence(instead))} |")
    return page("Commands", "Every devloops command and option, as devloops itself defines "
                "them.", "\n".join(lines))


# --- configuration --------------------------------------------------------------------------------

def _defaults():
    with open(config.DEFAULTS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _lookup(data, dotted):
    for part in dotted.split("."):
        if not isinstance(data, dict) or part not in data:
            return None, False
        data = data[part]
    return data, True


def _type(node):
    if "enum" in node:
        return "one of " + ", ".join(f"`{json.dumps(v)}`" for v in node["enum"])
    if "const" in node:
        return f"always `{json.dumps(node['const'])}`"
    if "$ref" in node:
        return "object (the run configuration keys)"
    types = node.get("type", "any")
    types = types if isinstance(types, list) else [types]
    text = " or ".join(types)
    if node.get("items", {}).get("type"):
        text = text.replace("array", f"list of {node['items']['type']}s")
    if "minimum" in node:
        text += f", at least {node['minimum']}"
    if "pattern" in node:
        text += f", matching `{node['pattern']}`"
    return text


def _keys(node, prefix=""):
    for key, child in node.get("properties", {}).items():
        yield prefix + key, child
        yield from _keys(child, prefix + key + ".")


def _key_entries(schema_name, defaults=None):
    lines = []
    for dotted, node in _keys(schema.load(schema_name)):
        if "default" in node:
            default, found = node["default"], True
        else:
            default, found = _lookup(defaults, dotted) if defaults else (None, False)
        lines += ["", f"### `{dotted}` {{#{dotted}}}", "", sentence(node.get("description", "")),
                  "", f"- **Type:** {_type(node)}"]
        if found and not (isinstance(default, dict) and "properties" in node):
            lines.append(f"- **Default:** `{json.dumps(default)}`")
    return lines


def configuration_page():
    layers = " ".join(config.__doc__.split("\n", 1)[1].split())
    lines = [
        "devloops reads its settings from several places. Each one overrides the ones before it:",
        "", f"> {layers}", "",
        "- **Packaged defaults:** the values below marked **Default**.",
        "- **Project files:** the `config` key of `.devloops/devloops.json` (shared, committed) "
        "and of `.devloops/devloops.local.json` (yours, not committed).",
        "- **Workspace file:** `config.json` in the workspace, or the file given with "
        "`--config`.",
        "- **Command-line options**, such as `--max-trials`.",
        "",
        "A run keeps the settings it started with: later edits to the files apply to new runs.",
        "", "## Run configuration {#run-configuration}", "",
        "These keys go under `config` in the project files, or at the top of a workspace's "
        "`config.json`.",
    ]
    lines += _key_entries("config.schema.json", _defaults())
    lines += ["", "## Project file {#project-file}", "",
              "These keys go at the top of `.devloops/devloops.json` and "
              "`.devloops/devloops.local.json`. The local file is merged over the shared one, "
              "and relative paths are relative to the project's folder."]
    lines += _key_entries("project-config.schema.json")
    return page("Configuration keys", "Every configuration key: where it goes, its type, its "
                "default and what it does.", "\n".join(lines))


# --- exit codes -----------------------------------------------------------------------------------

def exit_codes_page(desc):
    lines = ["Every devloops command ends with one of these exit codes, so scripts can tell "
             "what happened.", "", "| Code | Name | Meaning | What to do |", "|---|---|---|---|"]
    for code in exit_codes():
        entry = desc["exit_codes"][str(code)]
        lines.append(f"| <span id=\"exit-{code}\"></span>{code} | `{entry['name']}` | "
                     f"{cell(entry['meaning'])} | {cell(entry['next'])} |")
    return page("Exit codes", "What each devloops exit code means and what to do next.",
                "\n".join(lines))


# --- steps ----------------------------------------------------------------------------------------

def _output(spec):
    if isinstance(spec["schema"], str):
        return f"a JSON document checked against `{spec['schema']}`"
    return "a JSON object with " + ", ".join(f"`{k}`" for k in spec["schema"]["required"])


def steps_page(desc):
    if sorted(STEP_ORDER) != sorted(claude.STEPS):
        raise SystemExit(f"gen_reference: STEP_ORDER {STEP_ORDER} does not match claude.STEPS "
                         f"{list(claude.STEPS)}")
    lines = ["A step is one kind of call devloops makes to Claude Code. The steps below are in "
             "the order a run meets them. Each runs headless (`claude -p`) with the tools listed "
             "and must answer in the form shown; devloops checks the answer before using it."]
    for name in STEP_ORDER:
        spec = claude.STEPS[name]
        tools = ("the `implement_tools` setting" if spec["tools"] is None
                 else ", ".join(f"`{t}`" for t in spec["tools"]))
        lines += ["", f"## `{name}` {{#step-{name}}}", "", desc["steps"][name], "",
                  f"- **Changes files:** {'yes, only inside the target' if spec['writes'] else 'no'}",
                  f"- **Tools:** {tools}",
                  f"- **Answer:** {_output(spec)}",
                  f"- **Model setting:** `models.{name}`, else `model`"]
    return page("Steps", "Each step devloops runs, in order: what it does, what it may change "
                "and what it must answer.", "\n".join(lines))


# --- statuses -------------------------------------------------------------------------------------

KINDS = {
    "run": ("Run", "The whole run, across its loops (`run/state.json`)."),
    "loop": ("Loop", "One loop's run (`<loop>/state/run.json`)."),
    "milestone": ("Milestone", "One milestone of the plan."),
    "task": ("Task", "One task of a milestone."),
    "trial": ("Trial", "One attempt at a milestone, or at the plan."),
    "approval": ("Plan approval", "How the plan was approved, or sent back."),
}


def statuses_page(desc):
    values = code_values()
    lines = ["Each kind of thing devloops tracks has its own statuses. "
             "[How it works: statuses](../how-it-works/statuses.md) shows how one leads to the "
             "next."]
    for kind, (title, about) in KINDS.items():
        lines += ["", f"## {title} {{#{kind}}}", "", about, "", "| Status | Meaning |",
                  "|---|---|"]
        for value in values["statuses"][kind]:
            lines.append(f"| <span id=\"{kind}-{value}\"></span>`{value}` | "
                         f"{cell(desc['statuses'][kind][value])} |")
    lines += ["", "## Stop reasons {#stop-reasons}", "",
              "When a loop stops, its status says how (`stopped-on-…`) and its reason says why.",
              "", "| Reason | Meaning |", "|---|---|"]
    for code in values["stop_reasons"]:
        lines.append(f"| <span id=\"stop-{code}\"></span>`{code}` | "
                     f"{cell(desc['stop_reasons'][code])} |")
    return page("Statuses", "Every status devloops records, and every reason a loop stops.",
                "\n".join(lines))


# --- state files ----------------------------------------------------------------------------------

def _fields(schema_name):
    node = schema.load(schema_name)
    lines = ["", "| Field | Type | Meaning |", "|---|---|---|"]
    for key, child in node.get("properties", {}).items():
        lines.append(f"| `{key}` | {cell(_type(child))} | "
                     f"{cell(sentence(child.get('description', '')))} |")
    return lines


def state_files_page(desc):
    lines = ["Everything devloops knows about a run is in files in the workspace, so a run can "
             "be read, shared, and resumed. These are the files a run writes, relative to the "
             "workspace folder. In the names, `<loop>` is `backend-dev` or `frontend-dev`, `<id>` "
             "a milestone (`M01`), `<n>` a trial number, `<seq>` a call's number, `<step>` a "
             "[step](steps.md), and `<check>` a check's id.", "",
             "| File | What it records |", "|---|---|"]
    files = workspace_files()
    for name in files:
        what = cell(desc["files"][name])
        if name in FILE_SCHEMAS:
            what += f" See [its fields](#{anchor(name)}-fields)."
        lines.append(f"| <span id=\"{anchor(name)}\"></span>`{name}` | {what} |")
    for name in files:
        if name in FILE_SCHEMAS:
            lines += ["", f"## `{name}` {{#{anchor(name)}-fields}}"] + _fields(FILE_SCHEMAS[name])
    return page("State files", "Every file a run writes in its workspace, and the fields of "
                "the main ones.", "\n".join(lines))


# --- main -----------------------------------------------------------------------------------------

def pages():
    desc = descriptions()
    return {
        "commands.md": commands_page(),
        "configuration.md": configuration_page(),
        "exit-codes.md": exit_codes_page(desc),
        "steps.md": steps_page(desc),
        "statuses.md": statuses_page(desc),
        "state-files.md": state_files_page(desc),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Write the reference pages from the code.")
    parser.add_argument("--check", action="store_true",
                        help="write nothing; exit 1 naming each page that differs")
    args = parser.parse_args(argv)
    differing = []
    for name, text in pages().items():
        path = os.path.join(REFERENCE, name)
        try:
            with open(path, encoding="utf-8") as f:
                current = f.read()
        except FileNotFoundError:
            current = None
        if current == text:
            continue
        if args.check:
            differing.append(os.path.relpath(path, ROOT))
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"wrote {os.path.relpath(path, ROOT)}")
    if differing:
        print("differs from what gen_reference.py writes now (run python3 "
              "tools/docs/gen_reference.py):")
        for path in differing:
            print(f"  {path}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
