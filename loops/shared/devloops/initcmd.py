"""`devloops init`: set up a directory as a devloops project (002 FR-003 to FR-007b).

It writes the installed files (the skills and `.devloops/prompts/README.md`), `devloops.json`,
`manifest.json`, and a marked `.gitignore` block (research P-12), and can ask for the targets and
the requirements on a terminal (research P-13). Nothing is ever overwritten: any conflicting file
stops `init` before the first write.

A project counts as initialized once `.devloops/manifest.json` exists. A `devloops.json` without
a manifest is kept as it is (it belongs to the developer, FR-028) and the rest is installed
(research P-17).
"""
import copy
import hashlib
import json
import os
import stat
from dataclasses import dataclass

from . import project as project_mod
from . import prompts, state, workspace
from .state import DevloopsError

SKILLS_DIR = (".claude", "skills")
PROMPTS_README = os.path.join(project_mod.DIRNAME, "prompts", "README.md")
IGNORE_BEGIN = '# >>> devloops (added by "devloops init")'
IGNORE_END = "# <<< devloops"
DEFAULT_TARGETS = {"backend-dev": "backend", "frontend-dev": "frontend"}
NO_TARGET = "none"  # the target answer for a loop the project does not use (003 FR-013)
NEEDS_A_LOOP = "a project needs at least one loop"


class InitError(DevloopsError):
    """`init` refused (exit 30): `code` is e.g. `init-conflict`; nothing was written."""

    exit_code = state.EXIT_CODES["stopped-on-input-error"]

    def __init__(self, code, message, conflicts=()):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.conflicts = list(conflicts)


@dataclass
class InitOptions:
    """What `devloops init` passes. Paths given as flags are relative to the current directory."""

    backend_target: str = None
    frontend_target: str = None
    no_backend: bool = False  # --no-backend: targets.backend-dev is null (003 FR-014)
    no_frontend: bool = False
    requirements: str = None
    speckit_feature: str = None
    no_prompt: bool = False
    track_workspaces: bool = False
    allow_skills: bool = False
    models: bool = True  # write RECOMMENDED_MODELS into devloops.json; `--no-models` turns it off


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


# --- what init installs ----------------------------------------------------------------------------

def render_skills(kit, project_root):
    """`{project-relative path: text}` of every skill, with `{{DEVLOOPS}}` replaced (FR-022)."""
    command = kit.command_for(project_root)
    templates = kit.path("shared", "skills")
    out = {}
    for name in sorted(os.listdir(templates)):
        source = os.path.join(templates, name, "SKILL.md")
        if not os.path.isfile(source):
            continue
        with open(source, encoding="utf-8") as f:
            out[os.path.join(*SKILLS_DIR, name, "SKILL.md")] = f.read().replace("{{DEVLOOPS}}",
                                                                                 command)
    return out


def installed_files(kit, project_root):
    """`{project-relative path: bytes}` of every file the manifest tracks."""
    files = {path: text.encode("utf-8") for path, text in render_skills(kit, project_root).items()}
    with open(kit.path("shared", "project", "prompts", "README.md"), "rb") as f:
        files[PROMPTS_README] = f.read()
    return dict(sorted(files.items()))


def permission_rule(command):
    """The Claude Code rule that pre-approves the skills' command (FR-022a)."""
    return f"Bash({command} *)"


SETTINGS_PATH = os.path.join(".claude", "settings.json")


def write_project_file(path, text):
    """Atomically write a file of the project (not devloops' run state).

    It is written through a symlink to its target and keeps its mode; a new file is 0644, readable
    by everyone, like the rest of the project's files.
    """
    target = os.path.realpath(path)
    mode = stat.S_IMODE(os.stat(target).st_mode) if os.path.exists(target) else 0o644
    state.write_text_atomic(target, text, mode=mode)


def _read_settings(path, rule):
    """The parsed settings file (`{}` when absent); `settings-unreadable` (exit 30) otherwise."""
    def unreadable(problem):
        return state.input_error("settings-unreadable",
                                 f"{path}: {problem}; add {rule} to permissions.allow by hand")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except OSError as e:
        raise unreadable(f"cannot be read: {e.strerror or e}")
    except ValueError as e:
        raise unreadable(f"not valid JSON: {e}")
    if not isinstance(data, dict):
        raise unreadable("not a JSON object")
    permissions = data.get("permissions", {})
    if not isinstance(permissions, dict) or not isinstance(permissions.get("allow", []), list):
        raise unreadable("permissions.allow is not a list")
    return data


def allow_skills(project_root, command):
    """Add the skills' rule to the project's shared Claude Code settings (FR-022b).

    Every other setting and rule is kept, in order; a rule already present is not added again.
    Returns `{path, rule, changed, created}`. Raises `settings-unreadable` before any write.
    """
    rule = permission_rule(command)
    path = os.path.join(project_root, SETTINGS_PATH)
    existed = os.path.exists(path)
    data = _read_settings(path, rule)
    allow = data.setdefault("permissions", {}).setdefault("allow", [])
    if rule in allow:
        return {"path": SETTINGS_PATH, "rule": rule, "changed": False, "created": False}
    allow.append(rule)
    write_project_file(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return {"path": SETTINGS_PATH, "rule": rule, "changed": True, "created": not existed}


# The model split `init` writes into a new devloops.json (the site's configuration guide, "Models
# per step"): a strong model where every later step is decided (the plan, the frozen checks, a milestone's last fix
# trial), a cheaper one for the code. Written into the project, not shipped as a default, so it is
# visible, editable, and never overrides the model of a setup that has no such names (Bedrock,
# Vertex, a gateway): `init --no-models` leaves it out, and Claude Code picks the model.
RECOMMENDED_MODELS = {
    "model": "sonnet",
    "models": {"plan": "opus", "replan": "opus", "author-checks": "opus",
               "fix_last_trial": "opus"},
}


def default_project_config(targets, requirements, models=True):
    """The `devloops.json` that `init` writes. `targets` are already project-relative."""
    return {
        "schema_version": 1,
        "workspace": project_mod.DEFAULT_WORKSPACE,
        "workspaces_dir": project_mod.DEFAULT_WORKSPACES_DIR,
        "targets": dict(targets),
        "requirements": requirements,
        "config": copy.deepcopy(RECOMMENDED_MODELS) if models else {},
    }


# --- inputs ----------------------------------------------------------------------------------------

def active_feature(project_root):
    """The spec-kit feature folder `.specify/feature.json` names, if it exists; else None."""
    data = state.read_json(os.path.join(project_root, ".specify", "feature.json"), default=None)
    folder = data.get("feature_directory") if isinstance(data, dict) else None
    if not isinstance(folder, str) or not folder:
        return None
    path = folder if os.path.isabs(folder) else os.path.join(project_root, folder)
    return path if os.path.isdir(path) else None


def check_targets(proj, kit, targets):
    """Validate absolute `{loop: path or None}` with the target guard (FR-007b, FR-014)."""
    checked = {}
    for loop, path in targets.items():
        if path:
            others = [(other, p) for other, p in checked.items() if p]
            # The default workspaces folder is inside .devloops/, which the guard covers.
            checked[loop] = workspace.check_target(path, proj, kit, None, others)
        else:
            checked[loop] = None
    return checked


def requirements_entry(proj, value, base):
    """Map a requirements answer or flag to its `devloops.json` form, or raise ValueError.

    `active` is the active spec-kit feature; a folder with `spec.md` is a spec-kit feature; a
    file is a requirements document. Relative values resolve against `base`.
    """
    if value == "active":
        if not active_feature(proj.root):
            raise ValueError("no active spec-kit feature: .specify/feature.json does not name an "
                             "existing folder")
        return {"speckit_feature": "active"}
    path = os.path.normpath(os.path.join(base, os.path.expanduser(value)))
    if os.path.isdir(path):
        if not os.path.isfile(os.path.join(path, "spec.md")):
            raise ValueError(f"{path} is a folder without spec.md (not a spec-kit feature)")
        return {"speckit_feature": proj.relative_or_absolute(path)}
    if os.path.isfile(path):
        return {"path": proj.relative_or_absolute(path)}
    raise ValueError(f"{path} does not exist")


def default_requirements(proj):
    return {"speckit_feature": "active"} if active_feature(proj.root) else None


def ask_missing(opts, project_root, kit, stdin, stdout):
    """Ask for each value not given as a flag; return `(targets, requirements, models)` (research
    P-13).

    Only on a terminal and without `--no-prompt`; otherwise return `None`. Answers are relative to
    the project root. An invalid answer is explained and asked again.
    """
    if opts.no_prompt or not (stdin.isatty() and stdout.isatty()):
        return None
    proj = project_mod.Project(project_root)

    ended = []

    def ask(question, default):
        """The answer, or the default at end of input (and for every later question)."""
        if ended:
            return default
        stdout.write(f"{question} [{default}]: ")
        stdout.flush()
        line = stdin.readline()
        if not line:
            stdout.write("\n")
            ended.append(True)
            return default
        return line.strip() or default

    def rejected(question, reason):
        """Explain a rejected answer; at end of input nothing new can come, so stop."""
        stdout.write(f"  {reason}\n")
        if ended:
            raise state.UsageError(f"no valid answer for {question!r} before the end of input")

    targets = {}
    unused = _unused_by_flag(opts)  # grows with each `none` answer
    for loop, label, flag in (("backend-dev", "Backend", opts.backend_target),
                              ("frontend-dev", "Frontend", opts.frontend_target)):
        if flag:
            targets[loop] = os.path.abspath(flag)
            continue
        if loop in unused:
            targets[loop] = None
            continue
        while True:
            answer = ask(f"{label} target ('{NO_TARGET}': not used)", DEFAULT_TARGETS[loop])
            if answer.lower() == NO_TARGET:  # a folder named none: ./none
                if unused | {loop} == set(DEFAULT_TARGETS):
                    rejected(f"{label} target", NEEDS_A_LOOP)
                    continue
                unused.add(loop)
                targets[loop] = None
                break
            path = proj.resolve(answer)
            try:
                check_targets(proj, kit, dict(targets, **{loop: path}))
            except state.StopRun as e:
                rejected(f"{label} target", e.message)
                continue
            targets[loop] = path
            break

    requirements = _flag_requirements(opts, proj)
    if requirements is None and not (opts.requirements or opts.speckit_feature):
        feature = active_feature(proj.root)
        default = f"active spec-kit feature ({proj.relative_or_absolute(feature)})" \
            if feature else ""
        while True:
            question = "Requirements (file, spec-kit feature dir, or 'active')"
            answer = ask(question, default)
            if not answer:
                break
            if answer == default:
                requirements = {"speckit_feature": "active"}
                break
            try:
                requirements = requirements_entry(proj, answer, proj.root)
                break
            except ValueError as e:
                rejected(question, str(e))

    models = opts.models
    if models:  # `--no-models` already answered it
        question = ("Recommended models (opus to plan and write checks, sonnet to build; "
                    "y/n)")
        while True:
            answer = ask(question, "y").lower()
            if answer in ("y", "yes", "n", "no"):
                models = answer.startswith("y")
                break
            rejected(question, "answer y or n")
    return targets, requirements, models


def _unused_by_flag(opts):
    """The loops `--no-backend` / `--no-frontend` leave out; both is a usage error, raised before
    anything is asked or written (003 FR-014)."""
    unused = {loop for loop, off in (("backend-dev", opts.no_backend),
                                     ("frontend-dev", opts.no_frontend)) if off}
    if unused == set(DEFAULT_TARGETS):
        raise state.UsageError(f"{NEEDS_A_LOOP}: --no-backend and --no-frontend cannot go "
                               "together")
    return unused


def _flag_requirements(opts, proj):
    if opts.requirements and opts.speckit_feature:
        raise state.UsageError("--requirements and --speckit-feature are mutually exclusive")
    value = opts.requirements or opts.speckit_feature
    if not value:
        return None
    try:
        entry = requirements_entry(proj, value, os.getcwd())
    except ValueError as e:
        raise InitError("missing-input", str(e))
    if opts.speckit_feature and "speckit_feature" not in entry:
        raise InitError("missing-input", f"{value} is not a spec-kit feature folder")
    if opts.requirements and "path" not in entry:
        raise InitError("missing-input", f"{value} is not a requirements file")
    return entry


# --- .gitignore ------------------------------------------------------------------------------------

def ignore_rules(proj, config, opts):
    """The block's lines: the workspaces folder (unless tracked, or outside the project), and the
    local file."""
    rules = []
    if not opts.track_workspaces:
        path = proj.resolve(config.get("workspaces_dir") or project_mod.DEFAULT_WORKSPACES_DIR)
        if proj.contains(path) and path != proj.root:
            rules.append(os.path.relpath(path, proj.root).replace(os.sep, "/") + "/")
    rules.append(f"{project_mod.DIRNAME}/{project_mod.LOCAL_NAME}")
    return rules


def _existing_block(text):
    lines = text.splitlines()
    if IGNORE_BEGIN not in lines:
        return None
    start = lines.index(IGNORE_BEGIN) + 1
    end = lines.index(IGNORE_END, start) if IGNORE_END in lines[start:] else len(lines)
    return [line for line in lines[start:end] if line.strip()]


# --- init ------------------------------------------------------------------------------------------

def _result(proj, kit, **fields):
    command = kit.command_for(proj.root)
    out = {"project": proj.root, "created": [], "changed": [], "adopted": [], "kept": [],
           "deleted": [], "removed": [], "conflicts": [], "permission_rule": permission_rule(command),
           "next": f"{command} check", "exit_code": 0, "message": ""}
    out.update(fields)
    return out


def _read_bytes(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None


def init(project_root, kit, opts, answers=None):
    """Set up `project_root`; return the result dict (contracts/cli.md, `init --json`).

    `answers` is what `ask_missing` returned, if it ran. Raises `InitError` or `StopRun`
    (`target-unwritable`) before any write.
    """
    proj = project_mod.Project(os.path.abspath(project_root))
    command = kit.command_for(proj.root)
    manifest = proj.manifest()
    if manifest is not None:
        version = manifest.get("devloops_version", "?")
        if opts.allow_skills:  # only the rule: nothing is reinstalled (FR-022b)
            allowed = allow_skills(proj.root, command)
            return _result(proj, kit, **_allowed_fields(allowed),
                           message=f"already initialized (devloops {version}); "
                                   + _allowed_note(allowed))
        return _result(proj, kit, message=f"already initialized (devloops {version}); use "
                                          f'"devloops init --upgrade" to update')
    if opts.allow_skills:  # refuse unreadable settings before anything is written
        _read_settings(os.path.join(proj.root, SETTINGS_PATH), permission_rule(command))

    existing_config = os.path.isfile(proj.config_path)
    ignored = [flag for flag, value in (("--backend-target", opts.backend_target),
                                        ("--frontend-target", opts.frontend_target),
                                        ("--no-backend", opts.no_backend),
                                        ("--no-frontend", opts.no_frontend),
                                        ("--requirements", opts.requirements),
                                        ("--speckit-feature", opts.speckit_feature)) if value]
    if existing_config:
        config = proj.shared_config  # validated (FR-016); kept as it is
    else:
        models = opts.models
        if answers is not None:
            targets, requirements, models = answers
        else:
            unused = _unused_by_flag(opts)
            targets = {loop: None if loop in unused else
                       os.path.abspath(given) if given else proj.resolve(default)
                       for (loop, default), given in zip(DEFAULT_TARGETS.items(),
                                                         (opts.backend_target,
                                                          opts.frontend_target))}
            requirements = _flag_requirements(opts, proj) or default_requirements(proj)
        if not any(targets.values()):
            raise state.UsageError(NEEDS_A_LOOP)
        checked = check_targets(proj, kit, targets)
        config = default_project_config(
            {loop: proj.relative_or_absolute(p) if p else None for loop, p in checked.items()},
            requirements, models)

    files = installed_files(kit, proj.root)
    conflicts, adopted, to_write = [], [], {}
    for rel, data in files.items():
        current = _read_bytes(os.path.join(proj.root, rel))
        if current is None:
            to_write[rel] = data
        elif current == data:
            adopted.append(rel)
        else:
            conflicts.append(rel)
    if conflicts:
        raise InitError("init-conflict",
                        "these files exist with different content; move them away and run "
                        "`devloops init` again: " + ", ".join(conflicts), conflicts=conflicts)

    created, changed = [], []
    for rel, data in to_write.items():
        write_project_file(os.path.join(proj.root, rel), data.decode("utf-8"))
        created.append(rel)
    config_rel = os.path.relpath(proj.config_path, proj.root)
    if not existing_config:
        write_project_file(proj.config_path, json.dumps(config, indent=2) + "\n")
        created.append(config_rel)

    rules = ignore_rules(proj, config, opts)
    gitignore = os.path.join(proj.root, ".gitignore")
    text = (_read_bytes(gitignore) or b"").decode("utf-8")
    block = _existing_block(text)
    if block is None:
        separator = "" if not text or text.endswith("\n\n") else ("\n" if text.endswith("\n")
                                                                   else "\n\n")
        new_text = text + separator + "\n".join([IGNORE_BEGIN, *rules, IGNORE_END]) + "\n"
        write_project_file(gitignore, new_text)
        (changed if text else created).append(".gitignore")
    else:
        rules = block

    manifest = {
        "schema_version": 1, "devloops_version": kit.version, "kit_mode": kit.mode,
        "command": command, "installed_at": state.now_iso(), "upgraded_at": None,
        "ignore_rules": rules, "files": {rel: sha256_bytes(data) for rel, data in files.items()},
    }
    write_project_file(proj.manifest_path, json.dumps(manifest, indent=2) + "\n")
    created.append(os.path.relpath(proj.manifest_path, proj.root))

    notes = [f"initialized {proj.root} (devloops {kit.version})"]
    if existing_config:
        notes.append(f"kept the existing {config_rel}"
                     + (f" ({', '.join(ignored)} ignored; edit it instead)" if ignored else ""))
    if not config.get("requirements"):
        notes.append(f"no requirements set: add \"requirements\" to {config_rel}, or pass "
                     "--requirements <file> or --speckit-feature [dir] to run")
    if not existing_config and (config.get("config") or {}).get("models"):
        notes.append(f"models: sonnet, with opus to plan, write checks, and make a milestone's "
                     f"last fix trial (edit \"config\" in {config_rel}; init --no-models leaves "
                     f"the choice to Claude Code)")
    if not os.path.isdir(os.path.join(proj.root, ".git")):
        notes.append("no git repository here; the ignore rules are in .gitignore anyway")
    extra = {}
    if opts.allow_skills:
        allowed = allow_skills(proj.root, command)
        (created if allowed["created"] else changed if allowed["changed"] else []).append(
            allowed["path"])
        extra = {"skills_allowed": True}
        notes.append(_allowed_note(allowed))
    return _result(proj, kit, created=sorted(created), changed=changed, adopted=adopted,
                   message="; ".join(notes), **extra)


# --- upgrade ---------------------------------------------------------------------------------------

NEW_SUFFIX = prompts.NEW_SUFFIX


def version_tuple(version):
    """`"0.10.1"` -> `(0, 10, 1)`, for comparing versions (research P-12)."""
    return tuple(int(part) for part in str(version).split("."))


def _manifest_path_ok(rel):
    """A manifest path devloops may touch: relative, normalized, and inside the project."""
    return (isinstance(rel, str) and rel and not os.path.isabs(rel)
            and os.path.normpath(rel) == rel and not rel.startswith(".." + os.sep) and rel != "..")


def _remove_empty_parents(path, stop):
    parent = os.path.dirname(path)
    while parent != stop and parent.startswith(stop + os.sep):
        try:
            os.rmdir(parent)
        except OSError:
            return
        parent = os.path.dirname(parent)


def upgrade(project_root, kit, restore=False):
    """`devloops init --upgrade` (FR-027 to FR-029; data-model "Install manifest").

    Each installed file is compared with its manifest fingerprint: an unchanged file is replaced,
    a changed one is kept with the new version beside it as `<path>.devloops-new`, a deleted one is
    reported (re-created with `restore`), a file new in this version is added, and a file removed
    from the kit is removed when unchanged. `devloops.json`, the `.gitignore` block, and the
    workspaces are never touched. Everything is checked before the first write.

    Returns `{updated, kept: [{path, new_version}], deleted, restored, added, adopted, removed,
    from_version, manifest}`. Raises `InitError` (`downgrade-refused`, `init-conflict`,
    `manifest-unreadable`) or `UsageError` (not initialized), with nothing written.
    """
    proj = project_mod.Project(os.path.abspath(project_root))
    if not os.path.exists(proj.manifest_path):
        raise state.UsageError(f'{proj.root} is not initialized; run "devloops init" first')
    manifest = proj.manifest()
    files_before = (manifest or {}).get("files")
    try:
        installed = version_tuple(manifest["devloops_version"])
        running = version_tuple(kit.version)
        if not isinstance(files_before, dict):
            raise ValueError
    except (TypeError, KeyError, ValueError):
        raise InitError("manifest-unreadable",
                        f"{proj.manifest_path} cannot be read; move it away and run "
                        "`devloops init` again")
    from_version = manifest["devloops_version"]
    if installed > running:
        raise InitError("downgrade-refused",
                        f"this project was set up with devloops {from_version}, newer than the "
                        f"running devloops {kit.version}; downgrades are not supported. Install "
                        f"devloops {from_version} or later")

    files = installed_files(kit, proj.root)
    out = {"updated": [], "kept": [], "deleted": [], "restored": [], "added": [], "adopted": [],
           "removed": [], "from_version": from_version}
    writes, removals, conflicts = {}, [], []
    for rel, data in files.items():
        path = os.path.join(proj.root, rel)
        current = _read_bytes(path)
        if rel not in files_before:  # new in this version: the init conflict rule
            if current is None:
                writes[rel] = data
                out["added"].append(rel)
            elif current == data:
                out["adopted"].append(rel)
            else:
                conflicts.append(rel)
        elif current is None:
            if restore:
                writes[rel] = data
                out["restored"].append(rel)
            else:
                out["deleted"].append(rel)
        elif current == data:
            continue  # already the new version
        elif sha256_bytes(current) == files_before[rel]:
            writes[rel] = data
            out["updated"].append(rel)
        elif sha256_bytes(data) == files_before[rel]:
            continue  # changed here, but this version brings nothing new for it
        else:
            writes[rel + NEW_SUFFIX] = data
            out["kept"].append({"path": rel, "new_version": rel + NEW_SUFFIX})
    if conflicts:
        raise InitError("init-conflict",
                        "these files are new in devloops " + kit.version + " but exist with "
                        "different content; move them away and run `devloops init --upgrade` "
                        "again: " + ", ".join(conflicts), conflicts=conflicts)
    for rel, sha in sorted(files_before.items()):
        if rel in files or not _manifest_path_ok(rel):
            continue
        current = _read_bytes(os.path.join(proj.root, rel))
        if current is None:
            continue  # removed from the kit and already gone
        if sha256_bytes(current) == sha:
            removals.append(rel)
            out["removed"].append(rel)
        else:
            out["kept"].append({"path": rel, "new_version": None})

    for rel, data in writes.items():
        path = os.path.join(proj.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        write_project_file(path, data.decode("utf-8"))
    for rel in removals:
        path = os.path.join(proj.root, rel)
        os.remove(path)
        _remove_empty_parents(path, proj.root)

    manifest = dict(manifest, devloops_version=kit.version, kit_mode=kit.mode,
                    command=kit.command_for(proj.root), upgraded_at=state.now_iso(),
                    files={rel: sha256_bytes(data) for rel, data in files.items()})
    write_project_file(proj.manifest_path, json.dumps(manifest, indent=2) + "\n")
    out["manifest"] = manifest
    return out


def upgrade_result(proj, kit, upgraded):
    """The `init --json` form of an `upgrade` result (contracts/cli.md)."""
    if upgraded["from_version"] == kit.version:
        note = f"upgraded {proj.root} (devloops {kit.version}, the same version)"
    else:
        note = f"upgraded {proj.root} from devloops {upgraded['from_version']} to {kit.version}"
    notes = [note]
    if upgraded["kept"]:
        notes.append(f"{len(upgraded['kept'])} changed file(s) kept; compare each with its "
                     f"{NEW_SUFFIX} file")
    if upgraded["deleted"]:
        notes.append(f"{len(upgraded['deleted'])} deleted file(s) not restored (use --upgrade "
                     "--restore)")
    if not _sets_a_model(proj):
        notes.append(f"the project files set no model, so unless a workspace or --config file "
                     f"does, every call uses Claude Code's default; to plan with opus and build "
                     f"with sonnet, add to \"config\" in "
                     f"{os.path.relpath(proj.config_path, proj.root)}: "
                     f"{json.dumps(RECOMMENDED_MODELS, separators=(', ', ': '))}")
    return _result(proj, kit, created=upgraded["added"] + upgraded["restored"],
                   changed=upgraded["updated"], adopted=upgraded["adopted"],
                   kept=upgraded["kept"], deleted=upgraded["deleted"],
                   removed=upgraded["removed"], upgraded=True, message="; ".join(notes))


def _sets_a_model(proj):
    """Whether either project configuration file names a model (`model` or `models`)."""
    try:
        layers = proj.run_config_layers()
    except Exception:  # noqa: BLE001 - an unreadable file is reported elsewhere
        return True
    return any(layer.get("model") or layer.get("models") for layer in layers)


def _allowed_fields(allowed):
    key = "created" if allowed["created"] else "changed"
    return {key: [allowed["path"]] if allowed["changed"] else [], "skills_allowed": True}


def _allowed_note(allowed):
    if allowed["changed"]:
        return f"added {allowed['rule']} to {allowed['path']} (permissions.allow)"
    return f"{allowed['rule']} is already in {allowed['path']}; nothing changed"


def print_result(result, out):
    """The text form of an `init` result (contracts/cli.md)."""
    if result["message"]:
        print(result["message"], file=out)
    upgraded = result.get("upgraded")
    labels = ((("changed", "updated"), ("created", "added")) if upgraded
              else (("created", "created"), ("changed", "changed")))
    for key, label in labels + (("adopted", "adopted"),):
        for path in result[key]:
            print(f"  {label}: {path}", file=out)
    for kept in result["kept"]:
        beside = (f"; the new version is {kept['new_version']}" if kept["new_version"]
                  else "; no longer part of devloops")
        print(f"  kept: {kept['path']} (changed here{beside})", file=out)
    for path in result["deleted"]:
        print(f"  deleted: {path} (not restored)", file=out)
    for path in result["removed"]:
        print(f"  removed: {path} (no longer part of devloops)", file=out)
    command = result["next"].rsplit(" ", 1)[0]
    if (result["created"] or result["changed"]) and not upgraded:
        if not result.get("skills_allowed"):
            print(f"\nThe devloops skills run their command without asking. To let Claude Code "
                  f"run devloops outside the skills without asking, run: {command} init "
                  f"--allow-skills\n(it adds {result['permission_rule']} to "
                  f".claude/settings.json under permissions.allow)", file=out)
        print(f"\nNext: `{result['next']}`, then `{command} run`.", file=out)
