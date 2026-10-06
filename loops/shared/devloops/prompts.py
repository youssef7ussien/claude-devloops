"""Prompt overrides (002 FR-030 to FR-032, research P-8, contracts/project-layout.md).

A prompt is composed from three parts: `common.md`, `<loop>/Loop-instructions.md`, and
`steps/<step>.md`. A file with the part's name in `<project>/.devloops/prompts/` replaces the
packaged one. Each part used is recorded as a prompt source: `{part, source: "packaged" |
"override", path, sha256}`, `path` being kit-relative or project-relative.
"""
import hashlib
import json
import os

from . import project as project_mod

OVERRIDES_DIR = os.path.join(project_mod.DIRNAME, "prompts")
LOOPS = ("backend-dev", "frontend-dev")
COMMON_STEPS = ("plan", "replan", "implement", "fix")
VALIDATOR_STEPS = {"curl": ("author-checks",), "playwright": ("validate-ui",)}
STEP_NAMES = COMMON_STEPS + tuple(s for steps in VALIDATOR_STEPS.values() for s in steps)
README = "README.md"
NEW_SUFFIX = ".devloops-new"  # beside a changed installed file, written by `init --upgrade`


def common_part():
    return "common.md"


def loop_part(loop):
    return f"{loop}/Loop-instructions.md"


def step_part(step):
    return f"steps/{step}.md"


KNOWN_PARTS = ([common_part()] + [step_part(s) for s in STEP_NAMES]
               + [loop_part(loop) for loop in LOOPS])


def kit_path(part):
    """The kit-relative file a part replaces."""
    if part == common_part() or part.startswith("steps/"):
        return f"shared/prompts/{part}"
    return part


def loop_parts(kit, loop):
    """Every part `loop` can use: the shared rules, its instructions, and its steps."""
    with open(kit.path(loop, "loop.json"), encoding="utf-8") as f:
        validator = json.load(f).get("validator")
    steps = COMMON_STEPS + VALIDATOR_STEPS.get(validator, STEP_NAMES[len(COMMON_STEPS):])
    return [common_part(), loop_part(loop)] + [step_part(s) for s in steps]


def resolve(kit, project_root, part):
    """`(source, text)` of one part: the override in the project when there is one."""
    rel = f"{OVERRIDES_DIR}/{part}".replace(os.sep, "/")
    override = os.path.join(project_root, *rel.split("/")) if project_root else None
    if override and os.path.isfile(override):
        source, path, file = "override", rel, override
    else:
        source, path, file = "packaged", kit_path(part), kit.path(*kit_path(part).split("/"))
    with open(file, "rb") as f:
        data = f.read()
    return ({"part": part, "source": source, "path": path,
             "sha256": hashlib.sha256(data).hexdigest()},
            data.decode("utf-8", errors="replace"))


def sources(kit, project_root, parts):
    """The prompt source of each part, in order."""
    return [resolve(kit, project_root, part)[0] for part in parts]


def drift(frozen, current):
    """The parts whose source or content differ between two lists of prompt sources (FR-032)."""
    before = {s["part"]: (s["source"], s["sha256"]) for s in frozen or []}
    now = {s["part"]: (s["source"], s["sha256"]) for s in current or []}
    order = [s["part"] for s in frozen or []] + [s["part"] for s in current or []]
    return list(dict.fromkeys(p for p in order if before.get(p) != now.get(p)))


def ignored(project_root):
    """Project-relative paths in the overrides folder that replace nothing (a typo, say).
    The folder's README, and the new version `init --upgrade` writes beside a changed one, are
    expected and not listed."""
    base = os.path.join(project_root, OVERRIDES_DIR)
    found = []
    for directory, dirs, names in os.walk(base):
        dirs.sort()
        for name in sorted(names):
            rel = os.path.relpath(os.path.join(directory, name), base).replace(os.sep, "/")
            if rel != README + NEW_SUFFIX and rel != README and rel not in KNOWN_PARTS:
                found.append(f"{OVERRIDES_DIR}/{rel}".replace(os.sep, "/"))
    return found


def ignored_warnings(project_root):
    files = ignored(project_root)
    if not files:
        return []
    return [f"ignored in {OVERRIDES_DIR}/ (not a prompt part; see its README.md): "
            + ", ".join(files)]
